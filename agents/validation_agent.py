"""
Validation Agent
----------------
Bertanggung jawab untuk:
1. Validasi rule bisnis (total = subtotal + pajak, field wajib, dll)
2. Deteksi anomali (duplikat, nilai ekstrem, vendor tidak dikenal)
3. Cross-check konsistensi line items vs total
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, date
from schemas.invoice_schema import InvoiceSchema
logger = logging.getLogger(__name__)

TOLERANCE = 0.02  # 2% toleransi untuk pembulatan


@dataclass
class ValidationReport:
    is_valid: bool
    errors: list[str] = field(default_factory=list)       
    warnings: list[str] = field(default_factory=list)     
    suggestions: list[str] = field(default_factory=list)  
    anomaly_flags: list[str] = field(default_factory=list)


class ValidationAgent:
    """
    Validasi rule bisnis dan anomali pada data invoice yang sudah diekstrak.

    Args:
        known_vendors: Set nama vendor yang dikenal (opsional, untuk anomali check)
        max_invoice_amount: Batas atas nilai invoice normal (untuk anomali flag)
        duplicate_invoice_numbers: Set no_invoice yang sudah ada di DB (untuk duplikat check)
    """

    def __init__(
        self,
        known_vendors: Optional[set[str]] = None,
        max_invoice_amount: float = 1_000_000_000,  # 1 milyar default
        duplicate_invoice_numbers: Optional[set[str]] = None,
    ):
        self.known_vendors = known_vendors or set()
        self.max_invoice_amount = max_invoice_amount
        self.duplicate_invoice_numbers = duplicate_invoice_numbers or set()

    def validate(self, invoice: InvoiceSchema) -> ValidationReport:
        """
        Jalankan semua validasi dan return laporan lengkap.
        """
        errors = []
        warnings = []
        suggestions = []
        anomalies = []

        # 1. Field wajib
        self._check_required_fields(invoice, errors, warnings)

        # 2. Kalkulasi finansial
        self._check_financial_consistency(invoice, errors, warnings)

        # 3. Line items
        self._check_line_items(invoice, errors, warnings)

        # 4. Format dan tanggal
        self._check_dates(invoice, errors, warnings)

        # 5. Anomali bisnis
        self._check_anomalies(invoice, anomalies, warnings)

        # 6. Saran perbaikan
        self._suggest_improvements(invoice, suggestions)

        is_valid = len(errors) == 0
        return ValidationReport(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
            anomaly_flags=anomalies,
        )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    def _check_required_fields(self, inv: InvoiceSchema, errors: list, warnings: list):
        """Pastikan field-field kritis terisi."""
        if not inv.no_invoice:
            warnings.append("Nomor invoice tidak ditemukan — tidak bisa deteksi duplikat")
        if not inv.vendor_nama:
            errors.append("Nama vendor/penerbit tidak ditemukan")
        if not inv.total:
            errors.append("Total invoice tidak ditemukan")
        if not inv.tanggal_invoice:
            warnings.append("Tanggal invoice tidak ditemukan")
        if not inv.pembeli_nama:
            warnings.append("Nama pembeli tidak ditemukan")

    def _check_financial_consistency(self, inv: InvoiceSchema, errors: list, warnings: list):
        """Validasi konsistensi kalkulasi keuangan."""
        if inv.total is None:
            return

        # Cek: subtotal + ppn - diskon ≈ total
        if inv.subtotal is not None:
            ppn = inv.ppn_nominal or 0.0
            diskon = inv.diskon or 0.0
            expected_total = inv.subtotal + ppn - diskon

            if inv.total > 0:
                diff_pct = abs(expected_total - inv.total) / inv.total
                if diff_pct > TOLERANCE:
                    errors.append(
                        f"Total tidak konsisten: subtotal({inv.subtotal:,.0f}) + "
                        f"ppn({ppn:,.0f}) - diskon({diskon:,.0f}) = {expected_total:,.0f}, "
                        f"tapi total tercantum {inv.total:,.0f} "
                        f"(selisih {diff_pct*100:.1f}%)"
                    )

        # Cek: ppn_persen vs ppn_nominal
        if inv.ppn_persen and inv.ppn_nominal and inv.subtotal:
            expected_ppn = inv.subtotal * (inv.ppn_persen / 100)
            if abs(expected_ppn - inv.ppn_nominal) / max(inv.ppn_nominal, 1) > TOLERANCE:
                warnings.append(
                    f"PPN nominal ({inv.ppn_nominal:,.0f}) tidak sesuai dengan "
                    f"{inv.ppn_persen}% dari subtotal ({expected_ppn:,.0f})"
                )

        # Cek nilai negatif
        for field_name, value in [
            ("subtotal", inv.subtotal),
            ("total", inv.total),
            ("ppn_nominal", inv.ppn_nominal),
        ]:
            if value is not None and value < 0:
                errors.append(f"Nilai {field_name} negatif: {value}")

    def _check_line_items(self, inv: InvoiceSchema, errors: list, warnings: list):
        """Validasi line items dan konsistensi dengan total."""
        if not inv.line_items:
            warnings.append("Tidak ada line item — pastikan tabel item sudah terekstrak")
            return

        # Cek setiap line item
        for i, item in enumerate(inv.line_items, 1):
            if not item.deskripsi:
                warnings.append(f"Line item #{i}: deskripsi kosong")
                continue

            # Kalkulasi: qty × harga_satuan ≈ total_harga
            if all(v is not None for v in [item.qty, item.harga_satuan, item.total_harga]):
                expected = item.qty * item.harga_satuan
                if item.total_harga > 0:
                    diff = abs(expected - item.total_harga) / item.total_harga
                    if diff > TOLERANCE:
                        warnings.append(
                            f"Line item #{i} '{item.deskripsi[:30]}': "
                            f"qty({item.qty}) × harga({item.harga_satuan:,.0f}) = "
                            f"{expected:,.0f}, tapi tercantum {item.total_harga:,.0f}"
                        )

        # Cek: sum(line_items.total_harga) ≈ subtotal
        item_totals = [item.total_harga for item in inv.line_items if item.total_harga is not None]
        if item_totals and inv.subtotal:
            sum_items = sum(item_totals)
            if inv.subtotal > 0:
                diff_pct = abs(sum_items - inv.subtotal) / inv.subtotal
                if diff_pct > TOLERANCE:
                    warnings.append(
                        f"Jumlah total line items ({sum_items:,.0f}) tidak sama "
                        f"dengan subtotal ({inv.subtotal:,.0f})"
                    )

    def _check_dates(self, inv: InvoiceSchema, errors: list, warnings: list):
        """Validasi logika tanggal."""
        today = date.today()

        def parse_date(s: Optional[str]) -> Optional[date]:
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except ValueError:
                return None

        tgl_invoice = parse_date(inv.tanggal_invoice)
        tgl_jatuh_tempo = parse_date(inv.tanggal_jatuh_tempo)

        if tgl_invoice:
            # Invoice dari masa depan = mencurigakan
            if tgl_invoice > today:
                warnings.append(f"Tanggal invoice ({tgl_invoice}) di masa depan")
            # Invoice sangat lama (> 5 tahun)
            elif (today - tgl_invoice).days > 365 * 5:
                warnings.append(f"Tanggal invoice ({tgl_invoice}) sangat lama (>5 tahun lalu)")

        if tgl_jatuh_tempo and tgl_invoice:
            # Jatuh tempo sebelum tanggal invoice
            if tgl_jatuh_tempo < tgl_invoice:
                errors.append(
                    f"Tanggal jatuh tempo ({tgl_jatuh_tempo}) "
                    f"lebih awal dari tanggal invoice ({tgl_invoice})"
                )

    def _check_anomalies(self, inv: InvoiceSchema, anomalies: list, warnings: list):
        """Deteksi anomali bisnis yang perlu perhatian."""

        # Duplikat nomor invoice
        if inv.no_invoice and inv.no_invoice in self.duplicate_invoice_numbers:
            anomalies.append(f"DUPLIKAT: Nomor invoice '{inv.no_invoice}' sudah ada di database")

        # Vendor tidak dikenal
        if self.known_vendors and inv.vendor_nama:
            vendor_lower = inv.vendor_nama.lower()
            known_lower = {v.lower() for v in self.known_vendors}
            if vendor_lower not in known_lower:
                anomalies.append(f"VENDOR BARU: '{inv.vendor_nama}' belum pernah ada sebelumnya")

        # Nilai invoice sangat besar
        if inv.total and inv.total > self.max_invoice_amount:
            anomalies.append(
                f"NILAI BESAR: Total invoice Rp {inv.total:,.0f} "
                f"melebihi batas normal Rp {self.max_invoice_amount:,.0f}"
            )

        # Total = 0
        if inv.total == 0:
            anomalies.append("NILAI NOL: Total invoice adalah 0")

        # Banyak sekali line items (mungkin OCR error)
        if len(inv.line_items) > 100:
            warnings.append(f"Line items sangat banyak ({len(inv.line_items)} items) — cek hasil OCR")

    def _suggest_improvements(self, inv: InvoiceSchema, suggestions: list):
        """Saran opsional untuk melengkapi data."""
        if not inv.vendor_npwp:
            suggestions.append("NPWP vendor tidak ditemukan — perlu untuk pelaporan pajak")
        if not inv.no_rekening and inv.metode_pembayaran and "transfer" in (inv.metode_pembayaran or "").lower():
            suggestions.append("Metode transfer tapi no rekening tidak ditemukan")
        if inv.mata_uang and inv.mata_uang != "IDR":
            suggestions.append(f"Mata uang asing ({inv.mata_uang}) — pastikan kurs sudah dicatat")