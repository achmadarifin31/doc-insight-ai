# ✓ SETUP CHECKLIST - Doc-Insight-AI

Ikuti langkah-langkah ini untuk menyelesaikan setup project.

---

## Phase 1: Python Environment Setup (✓ COMPLETE)

- [x] Create Python virtual environment
- [x] Install core dependencies (pydantic, requests, fastapi, etc)
- [x] Create required directories and __init__.py files
- [x] Fix Pydantic schema validation errors
- [x] All basic tests passing (6/6)

**Status:** ✓ Siap melanjutkan ke Phase 2

---

## Phase 2: Ollama Setup (⏳ PENDING - Lakukan sekarang)

### Step 1: Download Ollama
- [ ] Visit https://ollama.ai
- [ ] Download installer untuk Windows
- [ ] Run installer dan ikuti instruksi
- [ ] Verify installation: `ollama --version`

**Expected output:** `ollama version X.X.X`

---

### Step 2: Download LLM Model
Pilih SALAH SATU command di bawah:

#### Option A: Mistral 7B (REKOMENDASI - balanced size & quality)
```bash
ollama pull mistral
```
- Model size: ~4 GB
- Speed: Fast, Good quality
- Best for: General invoice extraction

#### Option B: Qwen 2.5 7B (BAGUS UNTUK BAHASA INDONESIA)
```bash
ollama pull qwen2.5
```
- Model size: ~5 GB  
- Speed: Fast, Local language support
- Best for: Mixed language documents

#### Option C: Llama 3.1 8B (GOOD GENERAL PURPOSE)
```bash
ollama pull llama3.1
```
- Model size: ~4 GB
- Speed: Medium
- Best for: High quality outputs

**Choose one and run:**
- [ ] Ollama model downloaded successfully
- [ ] Model appears in: `ollama list`

---

### Step 3: Start Ollama Server
```bash
ollama serve
```

**Expected output:**
```
pulling manifest
...
success
listening on 127.0.0.1:11434
```

**Important:** Keep this terminal open! Server harus running di background.

- [ ] Ollama server is running
- [ ] Terminal showing "listening on 127.0.0.1:11434"

---

### Step 4: Verify Connection (New Terminal)
Di terminal/PowerShell yang baru, run:

```bash
cd d:\Projects\doc-insight-ai
venv\Scripts\python -c "
from agents.extraction_agent import ExtractionAgent
agent = ExtractionAgent(model='mistral')
ok, msg = agent.check_ollama_connection()
print('OK' if ok else 'FAIL')
print(msg)
"
```

**Expected output:**
```
OK
OK. Model 'mistral' tersedia.
```

- [ ] Ollama connection test passed
- [ ] Model correctly detected

---

## Phase 3: Run Integration Tests (⏳ PENDING)

Setelah Ollama running, test full pipeline:

```bash
cd d:\Projects\doc-insight-ai
venv\Scripts\python test/test_integration.py
```

**Expected results:**
- [PASS] OCR Pipeline
- [PASS] Extraction Pipeline  
- [PASS] Full Pipeline

- [ ] All integration tests passed

---

## Phase 4: Test with Real Files (⏳ PENDING)

### Option A: Streamlit Web UI
```bash
cd d:\Projects\doc-insight-ai
streamlit run frontend/app.py
```

Then:
- Open browser: http://localhost:8501
- Upload sample PDF or image
- See extracted invoice data in JSON tab
- [ ] Successfully extracted invoice from file

---

### Option B: Python Script
```bash
cd d:\Projects\doc-insight-ai
venv\Scripts\python
```

Then in Python shell:
```python
from agents.orchestrator import InvoicePipeline

pipeline = InvoicePipeline(
    ollama_model="mistral",
    ollama_url="http://localhost:11434"
)

# Process single file
result = pipeline.process_file("path/to/invoice.pdf")
print(f"Status: {result.status}")
print(f"Confidence: {result.ocr_confidence:.2%}")

if result.extraction:
    print(f"Invoice No: {result.extraction.data.no_invoice}")
    print(f"Total: {result.extraction.data.total}")
```

- [ ] Successfully processed real invoice file

---

## Phase 5: (Optional) Batch Processing

Process multiple files dari folder:

```python
results = pipeline.process_folder("./tests/sample_docs/")
print(f"Processed: {len(results)} files")

for result in results:
    print(f"{result.file_name}: {result.status}")
```

- [ ] Batch processing works

---

## Troubleshooting

### Problem: "Tidak bisa konek ke Ollama"
**Checklist:**
- [ ] `ollama serve` running?
- [ ] Port 11434 tidak di-block firewall?
- [ ] Pastikan dalam 5 detik setelah ollama serve di-run
- [ ] Try: `curl http://localhost:11434/api/tags`

**Fix:**
1. Buka terminal baru
2. Run: `ollama serve`
3. Tunggu sampai "listening on..."muncul
4. Run test di terminal lain

---

### Problem: "Model 'mistral' tidak ditemukan"
**Checklist:**
- [ ] Run: `ollama list` (show available models?)
- [ ] Model download complete? (4GB untuk mistral)
- [ ] Check disk space available (>5GB)

**Fix:**
```bash
ollama list              # List models
ollama rm mistral        # Remove incomplete download
ollama pull mistral      # Re-download
```

---

### Problem: Timeout errors saat extraction
**Solution:**
- Model terlalu lambat untuk teks yang panjang
- Default timeout: 120 detik
- Adjust di code:
```python
agent = ExtractionAgent(request_timeout=300)  # 5 minutes
```

---

### Problem: Memory/CPU issues
**Solution:**
- GPU tidak tersedia (normal)
- Use CPU mode (slower tapi workable)
- Untuk faster processing: enable GPU
```python
agent = OCRAgent(use_gpu=True)  # If CUDA available
```

---

## Quick Reference Commands

```bash
# Setup (sudah done)
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Start Ollama (di terminal terpisah, keep running)
ollama serve

# Check model
ollama list
ollama pull mistral

# Run tests
venv\Scripts\python test/test_basic_setup.py
venv\Scripts\python test/test_integration.py

# Run UI
streamlit run frontend/app.py

# Check Ollama via HTTP
curl http://localhost:11434/api/tags

# Python REPL
venv\Scripts\python
>>> from agents.orchestrator import InvoicePipeline
>>> ...
```

---

## Final Verification Checklist

Before running production:

- [ ] Python venv created and activated
- [ ] All dependencies installed
- [ ] Database created (storage/invoices.db)
- [ ] Ollama installed and running
- [ ] LLM model downloaded (mistral or alternative)
- [ ] Basic setup tests passing (6/6)
- [ ] Integration tests passing (3/3)
- [ ] Successfully processed at least 1 real invoice
- [ ] Streamlit UI working
- [ ] No errors in terminal logs

---

## Support & Debugging

**If something doesn't work:**
1. Check terminal output for specific error message
2. Look at troubleshooting section above
3. Verify all checklist items are complete
4. Re-run relevant test:
   - `venv\Scripts\python test/test_basic_setup.py` 
   - `venv\Scripts\python test/test_integration.py`

**Key Files:**
- Setup docs: `SETUP_AND_TESTING.md`
- Agent code: `agents/`
- Schema: `schemas/invoice_schema.py`
- UI code: `frontend/app.py`

---

## Next Features (Future)

Setelah setup berhasil, dapat dikembangkan:
- [ ] Batch API endpoint (FastAPI)
- [ ] Database querying & reporting
- [ ] Custom validator rules
- [ ] Multi-language OCR support  
- [ ] Document classification
- [ ] Invoice deduplication

---

**Status:** Setup in progress  
**Last Updated:** March 24, 2026
**Next Action:** Follow Phase 2 (Install Ollama)
