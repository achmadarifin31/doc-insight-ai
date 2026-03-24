# Doc Insight AI — Fase 1: Invoice Pipeline

Pipeline multi-agent lokal untuk ekstraksi data terstruktur dari invoice PDF/gambar menggunakan OCR + LLM (Ollama).

---

## Arsitektur Fase 1

```
File (PDF/Gambar)
      │
      ▼
┌─────────────┐
│  OCR Agent  │  PaddleOCR + PyMuPDF + OpenCV preprocessing
└──────┬──────┘
       │ raw_text
       ▼
┌──────────────────┐
│ Extraction Agent │  Ollama (Mistral 7B) → JSON terstruktur
└──────┬───────────┘
       │ InvoiceSchema
       ▼
┌──────────────────┐
│ Validation Agent │  Rule bisnis + anomali detection
└──────┬───────────┘
       │
       ▼
   SQLite DB + Streamlit Dashboard
```

---

## Instalasi

### 1. Clone & Setup Python Environment

```bash
git clone <repo>
cd doc-insight-ai
python -m venv venv
source venv/bin/activate        # Linux/Mac
# atau: venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 2. Install & Setup Ollama

```bash
# Install Ollama (Linux)
curl -fsSL https://ollama.ai/install.sh | sh

# Atau download dari https://ollama.ai untuk Windows/Mac

# Pull model Mistral (rekomendasi utama, ~4GB)
ollama pull mistral

# Alternatif model (pilih salah satu):
ollama pull llama3.1          # Meta Llama 3.1 8B
ollama pull qwen2.5           # Qwen 2.5 7B (bagus untuk teks campuran)
ollama pull phi3:medium       # Microsoft Phi-3 14B (lebih lambat, reasoning lebih baik)

# Jalankan Ollama server (biarkan tetap berjalan di background)
ollama serve
```

### 3. Buat Folder yang Dibutuhkan

```bash
mkdir -p storage tests/sample_docs
touch agents/__init__.py schemas/__init__.py prompts/__init__.py frontend/__init__.py
```

### 4. Jalankan Streamlit UI

```bash
cd doc-insight-ai
streamlit run frontend/app.py
```

Buka browser: `http://localhost:8501`

---

## Penggunaan via Python (tanpa UI)

```python
from agents.orchestrator import InvoicePipeline

# Init pipeline
pipeline = InvoicePipeline(
    ollama_model="mistral",
    ollama_url="http://localhost:11434",
)

# Cek dependency
checks = pipeline.check_dependencies()
print(checks)

# Proses satu file
result = pipeline.process_file("tests/sample_docs/invoice_001.pdf")
print(result.to_summary())

# Akses data terstruktur
if result.extraction and result.extraction.data:
    inv = result.extraction.data
    print(f"Vendor: {inv.vendor_nama}")
    print(f"Total:  Rp {inv.total:,.0f}")
    print(f"Items:  {len(inv.line_items)}")

# Batch processing
results = pipeline.process_folder("tests/sample_docs/")
```

---

## Struktur Project

```
doc-insight-ai/
├── agents/
│   ├── __init__.py
│   ├── ocr_agent.py          ← OCR + preprocessing
│   ├── extraction_agent.py   ← LLM extraction via Ollama
│   ├── validation_agent.py   ← Rule validation + anomali
│   └── orchestrator.py       ← Pipeline coordinator
├── schemas/
│   ├── __init__.py
│   └── invoice_schema.py     ← Pydantic schema invoice
├── prompts/
│   ├── __init__.py
│   └── invoice_prompts.py    ← Prompt templates LLM
├── frontend/
│   └── app.py                ← Streamlit dashboard
├── storage/
│   └── invoices.db           ← SQLite (auto-created)
├── tests/
│   └── sample_docs/          ← Taruh file invoice test di sini
├── requirements.txt
└── README.md
```

---

## Konfigurasi Lanjutan

### Validasi Custom
```python
from agents.validation_agent import ValidationAgent

validator = ValidationAgent(
    known_vendors={"PT. ABC", "CV. XYZ"},           # Whitelist vendor
    max_invoice_amount=500_000_000,                  # Max Rp 500 juta
    duplicate_invoice_numbers={"INV-001", "INV-002"} # Cek duplikat
)
```

### Ganti Model
Edit `ollama_model` saat init pipeline atau pilih dari dropdown di sidebar Streamlit.

---

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `ConnectionError` ke Ollama | Pastikan `ollama serve` sudah berjalan |
| Model not found | Jalankan `ollama pull mistral` |
| OCR hasilnya kosong | Cek resolusi gambar minimal 150 DPI |
| JSON parse error terus | Coba model yang lebih besar (phi3:medium) |
| PaddleOCR error import | `pip install paddlepaddle==2.6.1` |
| Out of memory | Gunakan model 7B, tutup aplikasi lain |

---

## Fase Selanjutnya

- **Fase 2** — Validation Agent diperkuat + duplikat detection dari DB
- **Fase 3** — Insight Agent: tren vendor, total bulanan, anomali spending
- **Fase 4** — Tambah dukungan nota, PO, dan kontrak
- **Fase 5** — LangGraph orchestration + REST API (FastAPI)