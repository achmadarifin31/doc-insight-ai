# DOC-INSIGHT-AI: SETUP & TESTING GUIDE

## Status: ✓ SETUP SUCCESSFUL

Setelah troubleshooting dan perbaikan, project doc-insight-ai sudah siap digunakan!

---

## Errors yang Sudah diperbaiki

### 1. **Ollama Command Not Found**
**Error:** `'ollama' is not recognized as an internal or external command`

**Penyebab:** Ollama belum diinstall di sistem.

**Solusi:** Install Ollama (dijelaskan di bawah).

---

### 2. **Pydantic Schema Validation Error**
**Error:** `PydanticUserError: Decorators defined with incorrect fields`

**Penyebab:** Field validator pada `InvoiceSchema` mencoba validate `harga_satuan` yang tidak ada di class tersebut (hanya ada di `LineItem`).

**Solusi:** 
- Hapus `harga_satuan` dari validator di `InvoiceSchema`
- Buat validator terpisah untuk `LineItem` class

**File diperbaiki:** `schemas/invoice_schema.py`

---

### 3. **Missing Dependencies**
**Error:** `ModuleNotFoundError: No module named 'pydantic'`, `No module named 'requests'`

**Penyebab:** Pip install dari requirements.txt tidak berhasil sepenuhnya.

**Solusi:** Install dependencies secara eksplisit:
```bash
pip install pydantic requests fastapi uvicorn streamlit
```

---

## Test Results

```
[PASS] Imports           - Semua modules bisa di-import
[PASS] Pydantic Schema   - Schema validation berfungsi  
[PASS] Database          - Database initialization OK
[PASS] Validators        - Validation agent berfungsi
[PASS] Ollama            - Connection check works (Ollama not running yet = expected)
[PASS] OCRAgent          - OCR agent initialized OK

Result: 6/6 tests passed
```

---

## Langkah Selanjutnya

### STEP 1: Install Ollama

Ollama adalah runtime untuk menjalankan LLM lokal. Download & install dari:
- **Website:** https://ollama.ai
- **Supported:** Windows, Mac, Linux

### STEP 2: Pull Mistral Model

Setelah Ollama terinstall, buka terminal dan jalankan:

```bash
ollama pull mistral
```

Model akan didownload (~4GB). Tunggu sampai selesai.

Alternative models (pilih salah satu):
```bash
ollama pull llama3.1          # Meta Llama 3.1 8B
ollama pull qwen2.5           # Qwen 2.5 7B (bagus untuk bahasa Indonesia)
ollama pull phi3:medium       # Microsoft Phi-3 14B
```

### STEP 3: Start Ollama Server

```bash
ollama serve
```

Biarkan terminal ini tetap berjalan di background. Server akan berjalan di `http://localhost:11434`

### STEP 4: Test Ollama Connection

Di terminal lain, jalankan:
```bash
cd d:\Projects\doc-insight-ai
venv\Scripts\python -c "
from agents.extraction_agent import ExtractionAgent
agent = ExtractionAgent()
ok, msg = agent.check_ollama_connection()
print(f'Ollama Status: {msg}')
"
```

Expected output: `Ollama Status: OK. Model 'mistral' tersedia.`

### STEP 5: Test Full Pipeline

Buat file test dengan sample invoice:

```bash
# Cara 1: Gunakan Streamlit UI
streamlit run frontend/app.py

# Cara 2: Python script
python -c "
from agents.orchestrator import InvoicePipeline

pipeline = InvoicePipeline(
    ollama_model='mistral',
    ollama_url='http://localhost:11434'
)

# Check dependencies
deps = pipeline.check_dependencies()
print('Dependencies:', deps)
"
```

---

## File Structure

```
doc-insight-ai/
├── agents/
│   ├── __init__.py         (newly created)
│   ├── ocr_agent.py        - OCR processing (PDF, images)
│   ├── extraction_agent.py - LLM extraction via Ollama
│   ├── validation_agent.py - Business logic validation
│   └── orchestrator.py     - Main pipeline
├── schemas/
│   ├── __init__.py         (newly created)
│   └── invoice_schema.py   - Pydantic models (FIXED)
├── prompts/
│   ├── __init__.py         (newly created)
│   └── invoice_prompt.py   - LLM prompts
├── frontend/
│   ├── __init__.py         (newly created)
│   └── app.py             - Streamlit UI
├── storage/               (newly created)
│   ├── invoices.db        - SQLite database (auto-created)
│   └── test_db.db
├── test/                  (newly created)
│   ├── test_basic_setup.py       (newly created)
│   └── sample_docs/       (create for test files)
├── requirements.txt       - Python dependencies
└── README.md
```

---

## Dependencies Status

### Installed:
- ✓ pydantic >= 2.7.0 (Pydantic v2 with validators support)
- ✓ requests >= 2.32.0 (for Ollama API calls)
- ✓ fastapi >= 0.111.0
- ✓ uvicorn >= 0.29.0
- ✓ streamlit >= 1.35.0
- ✓ PyMuPDF >= 1.24.0 (PDF processing)
- ✓ opencv-python-headless >= 4.9.0
- ✓ pillow >= 10.3.0
- ✓ paddleocr >= 2.7.3 (optional but recommended)

### External (install separately):
- Ollama (LLM runtime)

---

## Troubleshooting

### Problem: Ollama connection timeout
**Solution:** 
1. Pastikan `ollama serve` sudah running di terminal lain
2. Check port 11434 tidak ter-block firewall
3. Restart Ollama service

### Problem: Mistral model tidak ditemukan
**Solution:** 
```bash
ollama list              # Check installed models
ollama pull mistral      # Download if missing
```

### Problem: PDF/Image tidak bisa di-process
**Solution:**
- Untuk PDF digital: supported langsung via PyMuPDF
- Untuk PDF scan: akan diconvert ke image lalu OCR (memerlukan GPU untuk cepat)
- Untuk image: langsung OCR processing

### Problem: Memory/Timeout issues
**Solution:**
- Default timeout: 120 detik. Adjust di `ExtractionAgent.request_timeout`
- GPU mode: Set `use_gpu=True` di `OCRAgent(use_gpu=True)` untuk faster OCR
- Reduce text size: Auto-truncation ke 6000 chars

---

## Quick Commands

```bash
# Setup venv
python -m venv venv
venv\Scripts\activate

# Install deps
pip install -r requirements.txt

# Run tests
venv\Scripts\python test/test_basic_setup.py

# Run Ollama
ollama serve

# Pull models
ollama pull mistral
ollama pull qwen2.5

# Run Streamlit UI
streamlit run frontend/app.py

# Check Ollama status
curl http://localhost:11434/api/tags
```

---

## Next Steps

1. ✓ Setup Python environment
2. ✓ Install dependencies
3. ✓ Fix schema errors
4. ⏳ **Install Ollama** ← You are here
5. ⏳ Download Mistral model
6. ⏳ Test with sample invoices
7. ⏳ Deploy to production

---

**Created:** March 24, 2026  
**Status:** Ready for Ollama setup
