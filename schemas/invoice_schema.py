from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date
import re

class LineItem(BaseModel):
    deskripsi: str = Field(..., description="Nama/deskripsi barang atau jasa")
    qty: Optional[float] = Field(None, description="Jumlah/kuantitas")
    satuan: Optional[str] = Field(None, description="Satuan (pcs, kg, liter, dll)")
    harga_satuan: Optional[float] = Field(None, description="Harga per satuan")
    total_harga: Optional[float] = Field(None, description="Total harga baris ini")
 
 
class InvoiceSchema(BaseModel):
    no_invoice: Optional[str] = Field(None, description="Nomor invoice")
    tanggal_invoice: Optional[str] = Field(None, description="Tanggal invoice (YYYY-MM-DD)")
    tanggal_jatuh_tempo: Optional[str] = Field(None, description="Tanggal jatuh tempo (YYYY-MM-DD)")
    vendor_nama: Optional[str] = Field(None, description="Nama perusahaan/vendor penerbit")
    vendor_alamat: Optional[str] = Field(None, description="Alamat vendor")
    vendor_npwp: Optional[str] = Field(None, description="NPWP vendor jika ada")
    pembeli_nama: Optional[str] = Field(None, description="Nama perusahaan/pembeli")
    pembeli_alamat: Optional[str] = Field(None, description="Alamat pembeli")
    line_items: list[LineItem] = Field(default_factory=list, description="Daftar item")
    subtotal: Optional[float] = Field(None, description="Subtotal sebelum pajak")
    ppn_persen: Optional[float] = Field(None, description="Persentase PPN (misal 11.0)")
    ppn_nominal: Optional[float] = Field(None, description="Nominal PPN")
    diskon: Optional[float] = Field(None, description="Total diskon jika ada")
    total: Optional[float] = Field(None, description="Total akhir yang harus dibayar")
    metode_pembayaran: Optional[str] = Field(None, description="Transfer, tunai, dll")
    no_rekening: Optional[str] = Field(None, description="Nomor rekening tujuan jika ada")
    bank: Optional[str] = Field(None, description="Nama bank tujuan jika ada")
    mata_uang: Optional[str] = Field(default="IDR", description="Kode mata uang")
    catatan: Optional[str] = Field(None, description="Catatan atau keterangan tambahan")
    
    @field_validator('tanggal_invoice', 'tanggal_jatuh_tempo', mode="before")
    @classmethod
    def normalize_date(cls, v):
        if not v:
            return None
        v = str(v).strip()
        # Sudah format ISO
        if re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            return v
        # Format DD/MM/YYYY atau DD-MM-YYYY
        m = re.match(r'^(\d{2})[/-](\d{2})[/-](\d{4})$', v)
        if m:
            return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
        return v
    
    @field_validator("subtotal", "ppn_nominal", "diskon", "total", mode="before")
    @classmethod
    def clean_number(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        # Membersihkan format angka Indonesia: "1.500.000" atau "1,500,000"
        s = str(v).strip()
        s = re.sub(r"[Rp\s]", "", s)
        s = s.replace(".", "").replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None


class LineItemWithValidation(LineItem):
    """LineItem dengan validators untuk numeric fields."""
    
    @field_validator("qty", "harga_satuan", "total_harga", mode="before")
    @classmethod
    def clean_number_lineitem(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        # Membersihkan format angka Indonesia: "1.500.000" atau "1,500,000"
        s = str(v).strip()
        s = re.sub(r"[Rp\s]", "", s)
        s = s.replace(".", "").replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None


class InvoiceExtractionResult(BaseModel):
    """Wrapper hasil ekstraksi lengkap dengan metadata."""
    file_path: str
    status: str  # "success" | "partial" | "failed"
    confidence: float = Field(ge=0.0, le=1.0)
    data: Optional[InvoiceSchema] = None
    validation_errors: list[str] = Field(default_factory=list)
    raw_text_preview: Optional[str] = None