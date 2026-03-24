"""
OCR Agent
---------
Bertanggung jawab untuk:
1. Mendeteksi tipe file (PDF digital vs PDF scan vs gambar)
2. Preprocessing gambar (deskew, denoise, contrast)
3. Ekstrak teks menggunakan PaddleOCR atau PyMuPDF
4. Mengembalikan teks bersih beserta metadata layout
"""

import logging
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    raw_text: str
    source_type: str          # "pdf_digital" | "pdf_scan" | "image"
    page_count: int = 1
    confidence: float = 1.0   # rata-rata confidence OCR (0-1)
    layout_blocks: list[dict] = field(default_factory=list)
    error: Optional[str] = None


class OCRAgent:
    """
    Agent OCR yang mendukung PDF digital, PDF scan, dan gambar.

    Dependencies:
        pip install paddleocr paddlepaddle pymupdf opencv-python-headless Pillow
    """

    def __init__(self, lang: str = "en", use_gpu: bool = False):
        self.lang = lang
        self.use_gpu = use_gpu
        self._paddle_ocr = None   # lazy init — berat, init hanya saat dibutuhkan
        self._supported_image_ext = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, file_path: str | Path) -> OCRResult:
        """Entry point utama. Deteksi tipe file lalu pilih strategi yang tepat."""
        path = Path(file_path)
        if not path.exists():
            return OCRResult(raw_text="", source_type="unknown", error=f"File tidak ditemukan: {path}")

        suffix = path.suffix.lower()

        try:
            if suffix == ".pdf":
                return self._process_pdf(path)
            elif suffix in self._supported_image_ext:
                return self._process_image(path)
            else:
                return OCRResult(
                    raw_text="",
                    source_type="unsupported",
                    error=f"Tipe file tidak didukung: {suffix}"
                )
        except Exception as e:
            logger.error(f"OCR gagal untuk {path}: {e}", exc_info=True)
            return OCRResult(raw_text="", source_type="error", error=str(e))

    # ------------------------------------------------------------------
    # PDF Processing
    # ------------------------------------------------------------------

    def _process_pdf(self, path: Path) -> OCRResult:
        """
        PDF routing:
        - Jika PDF punya text layer cukup → ekstrak langsung (cepat, akurat)
        - Jika tidak (scan) → render ke gambar lalu OCR
        """
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        page_count = len(doc)

        # Cek apakah ada text layer yang bermakna
        total_chars = sum(len(page.get_text().strip()) for page in doc)
        is_digital = total_chars > 50 * page_count  # threshold: >50 char/halaman

        if is_digital:
            logger.info(f"PDF digital terdeteksi ({total_chars} chars). Ekstrak langsung.")
            return self._extract_pdf_text(doc, page_count)
        else:
            logger.info(f"PDF scan terdeteksi ({total_chars} chars). Gunakan OCR.")
            return self._ocr_pdf_pages(doc, path, page_count)

    def _extract_pdf_text(self, doc, page_count: int) -> OCRResult:
        """Ekstrak teks dari PDF digital menggunakan PyMuPDF."""
        import fitz

        all_blocks = []
        full_text_parts = []

        for page_num, page in enumerate(doc):
            # dict mode memberikan info layout (koordinat, ukuran font, dll)
            blocks = page.get_text("dict")["blocks"]
            page_text_lines = []

            for block in blocks:
                if block.get("type") == 0:  # type 0 = teks
                    for line in block.get("lines", []):
                        line_text = " ".join(
                            span["text"] for span in line.get("spans", [])
                        ).strip()
                        if line_text:
                            page_text_lines.append(line_text)
                            all_blocks.append({
                                "page": page_num + 1,
                                "text": line_text,
                                "bbox": line["bbox"],
                            })

            full_text_parts.append("\n".join(page_text_lines))

        raw_text = "\n\n".join(full_text_parts)
        return OCRResult(
            raw_text=self._clean_text(raw_text),
            source_type="pdf_digital",
            page_count=page_count,
            confidence=1.0,
            layout_blocks=all_blocks,
        )

    def _ocr_pdf_pages(self, doc, path: Path, page_count: int) -> OCRResult:
        """Render setiap halaman PDF ke gambar lalu OCR."""
        import tempfile, os
        import fitz

        all_text_parts = []
        all_blocks = []
        confidences = []

        with tempfile.TemporaryDirectory() as tmpdir:
            for page_num, page in enumerate(doc):
                # Render dengan resolusi tinggi (2x = 144 dpi)
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)
                img_path = os.path.join(tmpdir, f"page_{page_num + 1}.png")
                pix.save(img_path)

                result = self._run_paddleocr(img_path)
                page_text = "\n".join(result["lines"])
                all_text_parts.append(f"[Halaman {page_num + 1}]\n{page_text}")
                all_blocks.extend(result["blocks"])
                if result["confidence"] > 0:
                    confidences.append(result["confidence"])

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return OCRResult(
            raw_text=self._clean_text("\n\n".join(all_text_parts)),
            source_type="pdf_scan",
            page_count=page_count,
            confidence=round(avg_conf, 3),
            layout_blocks=all_blocks,
        )

    # ------------------------------------------------------------------
    # Image Processing
    # ------------------------------------------------------------------

    def _process_image(self, path: Path) -> OCRResult:
        """Preprocessing gambar lalu OCR."""
        preprocessed_path = self._preprocess_image(path)
        result = self._run_paddleocr(str(preprocessed_path))

        return OCRResult(
            raw_text=self._clean_text("\n".join(result["lines"])),
            source_type="image",
            page_count=1,
            confidence=round(result["confidence"], 3),
            layout_blocks=result["blocks"],
        )

    def _preprocess_image(self, path: Path) -> Path:
        """
        Preprocessing dasar:
        1. Grayscale
        2. Denoise (Gaussian)
        3. Adaptive threshold (untuk teks hitam di background tidak rata)
        4. Deskew (koreksi rotasi)

        Return path ke gambar yang sudah diproses.
        """
        import cv2
        import numpy as np
        import tempfile

        img = cv2.imread(str(path))
        if img is None:
            logger.warning(f"OpenCV tidak bisa baca {path}, skip preprocessing.")
            return path

        # Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Denoise
        denoised = cv2.GaussianBlur(gray, (3, 3), 0)

        # Adaptive threshold — lebih robust untuk dokumen scan
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            15, 8
        )

        # Deskew sederhana menggunakan Hough lines
        thresh = self._deskew(thresh)

        # Simpan ke temp file
        suffix = path.suffix
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        cv2.imwrite(tmp.name, thresh)
        return Path(tmp.name)

    def _deskew(self, img):
        """Koreksi kemiringan dokumen menggunakan minAreaRect."""
        import cv2
        import numpy as np

        coords = np.column_stack(np.where(img < 128))  # pixel gelap (teks)
        if len(coords) < 100:
            return img

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) < 0.5:  # sudah lurus, skip
            return img

        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
        logger.debug(f"Deskew: koreksi {angle:.2f} derajat")
        return rotated

    # ------------------------------------------------------------------
    # PaddleOCR
    # ------------------------------------------------------------------

    def _get_paddle_ocr(self):
        """Lazy init PaddleOCR — hanya load saat pertama kali dipakai."""
        if self._paddle_ocr is None:
            from paddleocr import PaddleOCR
            logger.info("Inisialisasi PaddleOCR (pertama kali, butuh beberapa detik)...")
            self._paddle_ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self.lang,
                use_gpu=self.use_gpu,
                show_log=False,
            )
        return self._paddle_ocr

    def _run_paddleocr(self, img_path: str) -> dict:
        """
        Jalankan PaddleOCR dan return hasil dalam format standar.
        Return: {"lines": [...], "blocks": [...], "confidence": float}
        """
        ocr = self._get_paddle_ocr()
        result = ocr.ocr(img_path, cls=True)

        lines = []
        blocks = []
        confidences = []

        if not result or not result[0]:
            return {"lines": [], "blocks": [], "confidence": 0.0}

        for line in result[0]:
            bbox, (text, conf) = line
            if text.strip():
                lines.append(text.strip())
                blocks.append({
                    "text": text.strip(),
                    "confidence": round(conf, 3),
                    "bbox": bbox,
                })
                confidences.append(conf)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return {"lines": lines, "blocks": blocks, "confidence": avg_conf}

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(text: str) -> str:
        """Bersihkan teks hasil OCR dari artefak umum."""
        # Hapus baris yang hanya berisi karakter non-alfanumerik
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if stripped and re.search(r"[a-zA-Z0-9]", stripped):
                cleaned.append(stripped)

        # Gabungkan dan normalkan whitespace
        result = "\n".join(cleaned)
        result = re.sub(r"\n{3,}", "\n\n", result)  # maks 2 baris kosong
        return result.strip()