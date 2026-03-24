"""
Invoice Pipeline Orchestrator
------------------------------
Koordinasi seluruh alur Fase 1:
  File Input → OCR Agent → Extraction Agent → Validation Agent → Result

Mendukung:
- Single file processing
- Batch processing dari folder
- Simpan hasil ke SQLite
- Progress callback untuk UI
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from agents.ocr_agent import OCRAgent, OCRResult
from agents.extraction_agent import ExtractionAgent
from agents.validation_agent import ValidationAgent, ValidationReport
from schemas.invoice_schema import InvoiceExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    file_path: str
    file_name: str
    status: str             # "success" | "partial" | "failed" | "skipped"
    extraction: Optional[InvoiceExtractionResult] = None
    validation: Optional[ValidationReport] = None
    ocr_source_type: Optional[str] = None
    ocr_confidence: Optional[float] = None
    processing_time_sec: Optional[float] = None
    error_message: Optional[str] = None

    def to_summary(self) -> dict:
        """Ringkasan untuk logging / display."""
        d = {
            "file": self.file_name,
            "status": self.status,
            "ocr_source": self.ocr_source_type,
            "extraction_confidence": self.extraction.confidence if self.extraction else None,
            "validation_valid": self.validation.is_valid if self.validation else None,
            "errors": [],
            "warnings": [],
            "anomalies": [],
        }
        if self.validation:
            d["errors"] = self.validation.errors
            d["warnings"] = self.validation.warnings
            d["anomalies"] = self.validation.anomaly_flags
        if self.error_message:
            d["errors"].append(self.error_message)
        return d


class InvoicePipeline:
    """
    Pipeline Fase 1 untuk pemrosesan invoice.

    Contoh penggunaan:
        pipeline = InvoicePipeline()

        # Single file
        result = pipeline.process_file("invoice.pdf")
        print(result.to_summary())

        # Batch folder
        results = pipeline.process_folder("./sample_docs/")
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}

    def __init__(
        self,
        ollama_model: str = "mistral",
        ollama_url: str = "http://localhost:11434",
        db_path: str = "storage/invoices.db",
        use_gpu: bool = False,
        ocr_lang: str = "en",
    ):
        self.db_path = db_path
        self._init_db()

        self.ocr_agent = OCRAgent(lang=ocr_lang, use_gpu=use_gpu)
        self.extraction_agent = ExtractionAgent(
            model=ollama_model,
            ollama_url=ollama_url,
        )
        self.validation_agent = ValidationAgent(
            duplicate_invoice_numbers=self._load_existing_invoice_numbers(),
        )

        logger.info(f"InvoicePipeline siap. Model: {ollama_model}, DB: {db_path}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_dependencies(self) -> dict:
        """Cek semua dependency sebelum mulai proses."""
        ok, msg = self.extraction_agent.check_ollama_connection()
        return {
            "ollama": {"ok": ok, "message": msg},
            "database": {"ok": True, "message": f"SQLite: {self.db_path}"},
        }

    def process_file(
        self,
        file_path: str | Path,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> PipelineResult:
        """
        Proses satu file invoice melalui full pipeline.

        Args:
            file_path: Path ke file PDF atau gambar
            progress_cb: Callback(message) untuk update progres ke UI
        """
        import time

        path = Path(file_path)
        start_time = time.time()

        def log(msg: str):
            logger.info(f"[{path.name}] {msg}")
            if progress_cb:
                progress_cb(msg)

        # Cek file
        if not path.exists():
            return PipelineResult(
                file_path=str(path),
                file_name=path.name,
                status="failed",
                error_message="File tidak ditemukan",
            )

        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return PipelineResult(
                file_path=str(path),
                file_name=path.name,
                status="skipped",
                error_message=f"Tipe file tidak didukung: {path.suffix}",
            )

        # STEP 1: OCR
        log("Langkah 1/3: OCR — mengekstrak teks dari dokumen...")
        ocr_result: OCRResult = self.ocr_agent.process(path)

        if ocr_result.error:
            return PipelineResult(
                file_path=str(path),
                file_name=path.name,
                status="failed",
                ocr_source_type=ocr_result.source_type,
                error_message=f"OCR gagal: {ocr_result.error}",
                processing_time_sec=round(time.time() - start_time, 2),
            )

        if not ocr_result.raw_text.strip():
            return PipelineResult(
                file_path=str(path),
                file_name=path.name,
                status="failed",
                ocr_source_type=ocr_result.source_type,
                error_message="OCR tidak menghasilkan teks (dokumen mungkin kosong atau corrupt)",
                processing_time_sec=round(time.time() - start_time, 2),
            )

        log(f"OCR selesai: {ocr_result.source_type}, {len(ocr_result.raw_text)} chars, "
            f"confidence={ocr_result.confidence:.2f}")

        # STEP 2: LLM Extraction
        log("Langkah 2/3: LLM Extraction — mengekstrak field terstruktur...")
        extraction_result: InvoiceExtractionResult = self.extraction_agent.extract_invoice(
            raw_text=ocr_result.raw_text,
            file_path=str(path),
        )
        log(f"Extraction selesai: status={extraction_result.status}, "
            f"confidence={extraction_result.confidence:.2f}")

        # STEP 3: Validation
        validation_report = None
        if extraction_result.data:
            log("Langkah 3/3: Validasi — memeriksa konsistensi data...")
            validation_report = self.validation_agent.validate(extraction_result.data)
            log(f"Validasi: valid={validation_report.is_valid}, "
                f"errors={len(validation_report.errors)}, "
                f"warnings={len(validation_report.warnings)}")
        else:
            log("Langkah 3/3: Validasi dilewati — tidak ada data yang bisa divalidasi")

        # Tentukan status final pipeline
        if extraction_result.status == "failed":
            final_status = "failed"
        elif validation_report and not validation_report.is_valid:
            final_status = "partial"
        elif extraction_result.status == "partial":
            final_status = "partial"
        else:
            final_status = "success"

        pipeline_result = PipelineResult(
            file_path=str(path),
            file_name=path.name,
            status=final_status,
            extraction=extraction_result,
            validation=validation_report,
            ocr_source_type=ocr_result.source_type,
            ocr_confidence=ocr_result.confidence,
            processing_time_sec=round(time.time() - start_time, 2),
        )

        # Simpan ke database
        self._save_to_db(pipeline_result)
        log(f"Selesai dalam {pipeline_result.processing_time_sec}s — status: {final_status}")

        return pipeline_result

    def process_folder(
        self,
        folder_path: str | Path,
        progress_cb: Optional[Callable[[str, int, int], None]] = None,
        skip_existing: bool = True,
    ) -> list[PipelineResult]:
        """
        Proses semua file invoice dalam sebuah folder.

        Args:
            folder_path: Path folder yang berisi file invoice
            progress_cb: Callback(message, current, total)
            skip_existing: Lewati file yang sudah ada di DB
        """
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Folder tidak ditemukan: {folder}")

        files = [
            f for f in folder.iterdir()
            if f.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]

        if not files:
            logger.warning(f"Tidak ada file yang didukung di {folder}")
            return []

        logger.info(f"Batch processing: {len(files)} file di {folder}")
        results = []
        existing = self._load_processed_files() if skip_existing else set()

        for i, file_path in enumerate(files, 1):
            if skip_existing and str(file_path) in existing:
                logger.info(f"Skip [{i}/{len(files)}] {file_path.name} (sudah diproses)")
                if progress_cb:
                    progress_cb(f"Skip: {file_path.name}", i, len(files))
                continue

            if progress_cb:
                progress_cb(f"Memproses {file_path.name}...", i, len(files))

            result = self.process_file(
                file_path,
                progress_cb=lambda msg: (
                    progress_cb(msg, i, len(files)) if progress_cb else None
                ),
            )
            results.append(result)

        # Ringkasan batch
        success = sum(1 for r in results if r.status == "success")
        partial = sum(1 for r in results if r.status == "partial")
        failed = sum(1 for r in results if r.status == "failed")
        logger.info(f"Batch selesai: {success} sukses, {partial} partial, {failed} gagal")

        return results

    def get_processed_invoices(self, limit: int = 100) -> list[dict]:
        """Ambil daftar invoice yang sudah diproses dari DB."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM invoices ORDER BY processed_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _init_db(self):
        """Buat tabel jika belum ada."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                status TEXT NOT NULL,
                no_invoice TEXT,
                vendor_nama TEXT,
                pembeli_nama TEXT,
                tanggal_invoice TEXT,
                tanggal_jatuh_tempo TEXT,
                total REAL,
                mata_uang TEXT,
                extraction_confidence REAL,
                validation_valid INTEGER,
                validation_errors TEXT,
                validation_warnings TEXT,
                anomaly_flags TEXT,
                raw_json TEXT,
                ocr_source_type TEXT,
                processed_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _save_to_db(self, result: PipelineResult):
        """Simpan hasil pipeline ke SQLite."""
        inv = result.extraction.data if result.extraction else None
        val = result.validation

        raw_json = None
        if inv:
            try:
                raw_json = inv.model_dump_json(indent=None)
            except Exception:
                pass

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO invoices (
                file_path, file_name, status,
                no_invoice, vendor_nama, pembeli_nama,
                tanggal_invoice, tanggal_jatuh_tempo,
                total, mata_uang,
                extraction_confidence, validation_valid,
                validation_errors, validation_warnings, anomaly_flags,
                raw_json, ocr_source_type, processed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            result.file_path,
            result.file_name,
            result.status,
            inv.no_invoice if inv else None,
            inv.vendor_nama if inv else None,
            inv.pembeli_nama if inv else None,
            inv.tanggal_invoice if inv else None,
            inv.tanggal_jatuh_tempo if inv else None,
            inv.total if inv else None,
            inv.mata_uang if inv else None,
            result.extraction.confidence if result.extraction else None,
            int(val.is_valid) if val else None,
            json.dumps(val.errors) if val else None,
            json.dumps(val.warnings) if val else None,
            json.dumps(val.anomaly_flags) if val else None,
            raw_json,
            result.ocr_source_type,
            datetime.now().isoformat(),
        ))
        conn.commit()
        conn.close()

    def _load_existing_invoice_numbers(self) -> set[str]:
        """Load semua no_invoice dari DB untuk cek duplikat."""
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                "SELECT no_invoice FROM invoices WHERE no_invoice IS NOT NULL"
            ).fetchall()
            conn.close()
            return {row[0] for row in rows}
        except Exception:
            return set()

    def _load_processed_files(self) -> set[str]:
        """Load daftar file yang sudah diproses."""
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("SELECT file_path FROM invoices").fetchall()
            conn.close()
            return {row[0] for row in rows}
        except Exception:
            return set()