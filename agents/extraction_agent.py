"""
Extraction Agent
----------------
Bertanggung jawab untuk:
1. Mengirim teks ke LLM lokal (Ollama) dengan prompt yang tepat
2. Parsing respons JSON dari LLM
3. Auto-repair jika JSON tidak valid (maksimal 2 kali retry)
4. Validasi hasil dengan Pydantic schema
"""

import json
import logging
import re
import time
from typing import Optional
import requests
from pydantic import ValidationError
from schemas.invoice_schema import InvoiceSchema, InvoiceExtractionResult
from prompts.invoice_prompt import (
    INVOICE_SYSTEM_PROMPT,
    INVOICE_USER_PROMPT,
    INVOICE_REPAIR_PROMPT,
)

logger = logging.getLogger(__name__)


class ExtractionAgent:
    """
    Ekstrak data terstruktur dari teks invoice menggunakan LLM lokal via Ollama.

    Setup Ollama:
        1. Install: https://ollama.ai
        2. Pull model: ollama pull mistral
        3. Pastikan Ollama running: ollama serve
    """

    DEFAULT_OLLAMA_URL = "http://localhost:11434"
    MAX_REPAIR_ATTEMPTS = 2

    def __init__(
        self,
        model: str = "mistral",
        ollama_url: str = DEFAULT_OLLAMA_URL,
        temperature: float = 0.1,       # Rendah = lebih deterministik untuk ekstraksi
        max_tokens: int = 4096,
        request_timeout: int = 120,
    ):
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.request_timeout = request_timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_invoice(self, raw_text: str, file_path: str = "") -> InvoiceExtractionResult:
        """
        Ekstrak data invoice dari teks mentah.

        Args:
            raw_text: Teks hasil OCR atau PDF parsing
            file_path: Path file asal (untuk metadata result)

        Returns:
            InvoiceExtractionResult dengan data terstruktur
        """
        if not raw_text or not raw_text.strip():
            return InvoiceExtractionResult(
                file_path=file_path,
                status="failed",
                confidence=0.0,
                validation_errors=["Teks input kosong"],
            )

        # Truncate jika terlalu panjang (Mistral 7B: context ~8k token)
        truncated_text = self._truncate_text(raw_text, max_chars=6000)
        if len(truncated_text) < len(raw_text):
            logger.warning(f"Teks dipotong dari {len(raw_text)} ke {len(truncated_text)} karakter")

        # Coba ekstraksi
        raw_json_str, llm_error = self._call_llm_extraction(truncated_text)

        if llm_error:
            return InvoiceExtractionResult(
                file_path=file_path,
                status="failed",
                confidence=0.0,
                validation_errors=[f"LLM error: {llm_error}"],
                raw_text_preview=truncated_text[:300],
            )

        # Parse dan validasi JSON
        invoice_data, parse_errors = self._parse_and_validate(raw_json_str)

        # Jika gagal, coba repair
        if parse_errors and raw_json_str:
            logger.info(f"JSON tidak valid, coba repair... Error: {parse_errors}")
            invoice_data, parse_errors = self._repair_json(
                raw_text=truncated_text,
                bad_json=raw_json_str,
                errors=parse_errors,
            )

        # Tentukan status akhir
        if invoice_data is None:
            status = "failed"
            confidence = 0.0
        elif parse_errors:
            status = "partial"
            confidence = self._estimate_confidence(invoice_data)
        else:
            status = "success"
            confidence = self._estimate_confidence(invoice_data)

        return InvoiceExtractionResult(
            file_path=file_path,
            status=status,
            confidence=confidence,
            data=invoice_data,
            validation_errors=parse_errors,
            raw_text_preview=truncated_text[:300],
        )

    def check_ollama_connection(self) -> tuple[bool, str]:
        """Cek apakah Ollama running dan model tersedia."""
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            model_base = self.model.split(":")[0]
            available = any(model_base in m for m in models)
            if available:
                return True, f"OK. Model '{self.model}' tersedia."
            else:
                return False, f"Model '{self.model}' tidak ditemukan. Available: {models}. Jalankan: ollama pull {self.model}"
        except requests.ConnectionError:
            return False, f"Tidak bisa konek ke Ollama di {self.ollama_url}. Jalankan: ollama serve"
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # LLM Call
    # ------------------------------------------------------------------

    def _call_llm_extraction(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """
        Kirim request ke Ollama API.
        Return: (raw_json_string, error_message)
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": INVOICE_SYSTEM_PROMPT},
                {"role": "user", "content": INVOICE_USER_PROMPT.format(raw_text=text)},
            ],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
            "format": "json",  # Ollama JSON mode — paksa output JSON
        }

        try:
            start = time.time()
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=self.request_timeout,
            )
            resp.raise_for_status()
            elapsed = time.time() - start

            content = resp.json()["message"]["content"]
            logger.info(f"LLM selesai dalam {elapsed:.1f}s, {len(content)} chars")
            return content, None

        except requests.Timeout:
            return None, f"Timeout setelah {self.request_timeout}s. Coba model lebih kecil atau increase timeout."
        except requests.ConnectionError:
            return None, "Tidak bisa konek ke Ollama. Pastikan 'ollama serve' sudah berjalan."
        except requests.HTTPError as e:
            return None, f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"
        except Exception as e:
            return None, str(e)

    def _repair_json(
        self,
        raw_text: str,
        bad_json: str,
        errors: list[str],
        attempt: int = 0,
    ) -> tuple[Optional[InvoiceSchema], list[str]]:
        """Minta LLM memperbaiki JSON yang bermasalah (rekursif, max 2x)."""
        if attempt >= self.MAX_REPAIR_ATTEMPTS:
            logger.warning("Repair JSON gagal setelah max attempts")
            return None, errors

        repair_prompt = INVOICE_REPAIR_PROMPT.format(
            error="; ".join(errors),
            raw_text=raw_text,
            bad_json=bad_json[:2000],
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": INVOICE_SYSTEM_PROMPT},
                {"role": "user", "content": repair_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.0},  # 0 untuk repair = paling deterministik
            "format": "json",
        }

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=self.request_timeout,
            )
            resp.raise_for_status()
            repaired_json = resp.json()["message"]["content"]
            invoice_data, new_errors = self._parse_and_validate(repaired_json)

            if new_errors and invoice_data is None:
                return self._repair_json(raw_text, repaired_json, new_errors, attempt + 1)
            return invoice_data, new_errors

        except Exception as e:
            return None, [str(e)]

    # ------------------------------------------------------------------
    # JSON Parsing & Validation
    # ------------------------------------------------------------------

    def _parse_and_validate(self, raw_str: str) -> tuple[Optional[InvoiceSchema], list[str]]:
        """
        Parse string JSON dan validasi dengan Pydantic.
        Return: (invoice_schema_object, list_of_errors)
        """
        if not raw_str:
            return None, ["Response LLM kosong"]

        # Bersihkan markdown code block jika ada
        cleaned = self._strip_markdown_json(raw_str)

        # Parse JSON
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            # Coba extracting JSON dari string yang mungkin ada teks lain
            extracted = self._extract_json_object(cleaned)
            if extracted:
                try:
                    data = json.loads(extracted)
                except json.JSONDecodeError:
                    return None, [f"JSON parse error: {e}"]
            else:
                return None, [f"JSON parse error: {e}. Raw: {cleaned[:200]}"]

        # Validasi dengan Pydantic
        try:
            invoice = InvoiceSchema(**data)
            return invoice, []
        except ValidationError as e:
            errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            # Kembalikan partial object jika memungkinkan (Pydantic v2)
            try:
                invoice = InvoiceSchema.model_construct(**{
                    k: v for k, v in data.items()
                    if k in InvoiceSchema.model_fields
                })
                return invoice, errors
            except Exception:
                return None, errors

    @staticmethod
    def _strip_markdown_json(text: str) -> str:
        """Hapus ```json ... ``` wrapper jika ada."""
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    @staticmethod
    def _extract_json_object(text: str) -> Optional[str]:
        """Cari dan ekstrak { ... } JSON object dari teks mixed."""
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return text[start:end + 1]
        return None

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        """Truncate teks tapi coba pertahankan bagian akhir (sering ada total)."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + "\n...[terpotong]...\n" + text[-half:]

    @staticmethod
    def _estimate_confidence(invoice: Optional[InvoiceSchema]) -> float:
        """
        Estimasi confidence berdasarkan berapa banyak field penting terisi.
        Field penting: no_invoice, vendor_nama, total, tanggal_invoice
        """
        if invoice is None:
            return 0.0

        important_fields = [
            invoice.no_invoice,
            invoice.vendor_nama,
            invoice.total,
            invoice.tanggal_invoice,
        ]
        secondary_fields = [
            invoice.pembeli_nama,
            invoice.subtotal,
            invoice.line_items,
        ]

        important_filled = sum(1 for f in important_fields if f is not None and f != [] and f != "")
        secondary_filled = sum(1 for f in secondary_fields if f is not None and f != [] and f != "")

        score = (important_filled / len(important_fields)) * 0.7 + \
                (secondary_filled / len(secondary_fields)) * 0.3
        return round(score, 2)