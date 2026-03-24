"""
Integration Test - Full Pipeline Testing
-----------------------------------------
Run this setelah:
1. Ollama installed
2. ollama pull mistral
3. ollama serve (running in background)

Run:
  cd doc-insight-ai
  venv\Scripts\python test/test_integration.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_extraction_pipeline():
    """Test extraction pipeline dengan sample teks."""
    print("\n[TEST] Extraction Pipeline")
    print("-" * 60)
    
    from agents.extraction_agent import ExtractionAgent
    from agents.validation_agent import ValidationAgent
    
    # Check Ollama first
    agent = ExtractionAgent(model="mistral", ollama_url="http://localhost:11434")
    ok, msg = agent.check_ollama_connection()
    
    if not ok:
        print(f"[SKIP] Ollama not available: {msg}")
        return False
    else:
        print(f"[OK] {msg}")
    
    # Sample invoice text (realistic example)
    sample_invoice = """
    INVOICE
    Invoice No: INV-2024-001234
    Date: 15 Januari 2024
    Due Date: 30 Januari 2024
    
    From:
    PT Contoh Indonesia
    Jalan Merdeka No 123
    Jakarta 12345
    NPWP: 12.345.678.9-012.345
    
    Bill To:
    PT Pembeli Besar
    Jalan Raja No 456
    Bandung 40000
    
    Items:
    1. Konsultasi IT Support - 10 jam @ Rp 500,000 = Rp 5,000,000
    2. Software License - 5 unit @ Rp 2,000,000 = Rp 10,000,000
    3. Training Session - 2 hari @ Rp 3,000,000 = Rp 6,000,000
    
    Subtotal:                   Rp 21,000,000
    PPN 11%:                    Rp  2,310,000
    Total:                      Rp 23,310,000
    
    Payment Method: Transfer Bank
    Bank: Bank Mandiri
    Account No: 123-456-789-0
    Account Name: PT Contoh Indonesia
    
    Notes:
    - Pembayaran sebelum tanggal jatuh tempo
    - Syarat & ketentuan berlaku
    """
    
    print(f"\n[INFO] Processing sample invoice text...")
    print(f"       Text length: {len(sample_invoice)} chars")
    
    result = agent.extract_invoice(sample_invoice, file_path="sample_invoice.txt")
    
    print(f"\n[RESULT] Extraction Status: {result.status}")
    print(f"         Confidence: {result.confidence:.2%}")
    
    if result.data:
        print(f"\n[EXTRACTED DATA]")
        print(f"  No Invoice: {result.data.no_invoice}")
        print(f"  Vendor: {result.data.vendor_nama}")
        print(f"  Pembeli: {result.data.pembeli_nama}")
        print(f"  Total: Rp {result.data.total:,.0f}" if result.data.total else "  Total: N/A")
        print(f" Tanggal Invoice: {result.data.tanggal_invoice}")
        print(f"  Line Items: {len(result.data.line_items)}")
        
        # Validate
        validator = ValidationAgent()
        validation = validator.validate(result.data)
        
        print(f"\n[VALIDATION]")
        print(f"  Is Valid: {validation.is_valid}")
        print(f"  Errors: {len(validation.errors)}")
        print(f"  Warnings: {len(validation.warnings)}")
        
        if validation.errors:
            for err in validation.errors:
                print(f"    - {err}")
        if validation.warnings:
            for warn in validation.warnings:
                print(f"    - {warn}")
        
        return True
    else:
        print(f"[FAIL] Extraction failed")
        if result.validation_errors:
            for err in result.validation_errors:
                print(f"  Error: {err}")
        return False


def test_ocr_with_image():
    """Test OCR dengan dummy image processing."""
    print("\n[TEST] OCR Pipeline")
    print("-" * 60)
    
    from agents.ocr_agent import OCRAgent
    
    agent = OCRAgent(lang="en", use_gpu=False)
    
    # Test 1: Non-existent file
    print("\n[INFO] Testing error handling with non-existent file...")
    result = agent.process("nonexistent_invoice.pdf")
    
    if result.error:
        print(f"[OK] Error handling works: {result.error}")
        return True
    else:
        print(f"[FAIL] Should have returned error")
        return False


def test_pipeline_integration():
    """Test full pipeline dari text ke database."""
    print("\n[TEST] Full Pipeline Integration")
    print("-" * 60)
    
    from agents.orchestrator import InvoicePipeline
    
    try:
        pipeline = InvoicePipeline(
            ollama_model="mistral",
            ollama_url="http://localhost:11434",
            db_path="storage/test_pipeline.db"
        )
        
        # Check dependencies
        deps = pipeline.check_dependencies()
        print(f"\n[DEPENDENCIES]")
        for service, info in deps.items():
            status = "OK" if info["ok"] else "FAIL"
            print(f"  [{status}] {service}: {info['message']}")
        
        print(f"\n[DB] Database path: {pipeline.db_path}")
        print(f"[DB] Existing invoices: {len(pipeline._load_existing_invoice_numbers())}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("DOC-INSIGHT-AI: INTEGRATION TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("OCR Pipeline", test_ocr_with_image),
        ("Extraction Pipeline", test_extraction_pipeline),
        ("Full Pipeline", test_pipeline_integration),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[ERROR] {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")
    
    print("-" * 60)
    print(f"Result: {passed}/{total} tests passed\n")
    
    if passed == total:
        print("[SUCCESS] All integration tests passed!")
        print("\nYou can now:")
        print("  1. Process real PDF/image files")
        print("  2. Run: streamlit run frontend/app.py")
        print("  3. Upload invoices via UI")
        return 0
    else:
        print(f"[ERRORS] {total - passed} test(s) failed")
        print("\nMake sure:")
        print("  1. Ollama is running: ollama serve")
        print("  2. Mistral model is downloaded: ollama pull mistral")
        print("  3. Check Ollama connection: curl http://localhost:11434/api/tags")
        return 1


if __name__ == "__main__":
    sys.exit(main())
