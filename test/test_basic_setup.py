"""
Basic Setup Tests untuk doc-insight-ai

Run: python test/test_basic_setup.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    print("\n[TEST 1] Testing imports...")
    try:
        from schemas.invoice_schema import InvoiceSchema, LineItem, InvoiceExtractionResult
        from agents.ocr_agent import OCRAgent, OCRResult
        from agents.extraction_agent import ExtractionAgent
        from agents.validation_agent import ValidationAgent, ValidationReport
        from agents.orchestrator import InvoicePipeline, PipelineResult
        from prompts.invoice_prompt import INVOICE_SYSTEM_PROMPT, INVOICE_USER_PROMPT
        print("[OK] All imports successful")
        return True
    except Exception as e:
        print(f"[FAIL] Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_schema():
    print("\n[TEST 2] Testing Pydantic schemas...")
    try:
        from schemas.invoice_schema import InvoiceSchema, LineItem
        
        line = LineItem(deskripsi="Test", qty=2.0, harga_satuan=10000.0)
        invoice = InvoiceSchema(no_invoice="INV-001", vendor_nama="Test", line_items=[line])
        print("[OK] Schema validation works")
        return True
    except Exception as e:
        print(f"[FAIL] Schema error: {e}")
        return False

def test_database():
    print("\n[TEST 3] Testing database...")
    try:
        from agents.orchestrator import InvoicePipeline
        pipeline = InvoicePipeline(db_path="storage/test_db.db")
        print("[OK] Database initialized")
        return True
    except Exception as e:
        print(f"[FAIL] Database error: {e}")
        return False

def test_validators():
    print("\n[TEST 4] Testing validators...")
    try:
        from agents.validation_agent import ValidationAgent
        from schemas.invoice_schema import InvoiceSchema, LineItem
        
        validator = ValidationAgent()
        invoice = InvoiceSchema(
            no_invoice="INV-001",
            vendor_nama="Test",
            subtotal=100000.0,
            total=111000.0,
            line_items=[LineItem(deskripsi="Item", harga_satuan=100000.0)]
        )
        report = validator.validate(invoice)
        print(f"[OK] Validator works (is_valid={report.is_valid})")
        return True
    except Exception as e:
        print(f"[FAIL] Validator error: {e}")
        return False

def test_ollama():
    print("\n[TEST 5] Testing Ollama connection...")
    try:
        from agents.extraction_agent import ExtractionAgent
        agent = ExtractionAgent()
        ok, msg = agent.check_ollama_connection()
        if ok:
            print(f"[OK] Ollama: {msg}")
        else:
            print(f"[INFO] Ollama not running (expected): {msg}")
        return True
    except Exception as e:
        print(f"[INFO] Ollama test skipped: {e}")
        return True

def test_ocr():
    print("\n[TEST 6] Testing OCRAgent...")
    try:
        from agents.ocr_agent import OCRAgent
        agent = OCRAgent()
        result = agent.process("nonexistent.pdf")
        if result.error:
            print("[OK] OCRAgent error handling works")
            return True
        else:
            print("[FAIL] OCRAgent should return error")
            return False
    except Exception as e:
        print(f"[FAIL] OCRAgent error: {e}")
        return False

def main():
    print("="*60)
    print("DOC-INSIGHT-AI: SETUP TEST SUITE")
    print("="*60)
    
    tests = [
        ("Imports", test_imports),
        ("Pydantic Schema", test_schema),
        ("Database", test_database),
        ("Validators", test_validators),
        ("Ollama", test_ollama),
        ("OCRAgent", test_ocr),
    ]
    
    results = [(name, func()) for name, func in tests]
    passed = sum(1 for _, r in results if r)
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")
    
    print("-"*60)
    print(f"Result: {passed}/{len(results)} tests passed\n")
    
    if passed == len(results):
        print("[SUCCESS] All tests passed!")
        print("\nNext: Install Ollama from https://ollama.ai")
        print("  1. ollama pull mistral")
        print("  2. ollama serve")
        return 0
    else:
        print(f"[ERROR] {len(results)-passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
