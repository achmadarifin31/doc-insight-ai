"""
Invoice Pipeline — Streamlit UI (Fase 1 Testing)

Jalankan:
    cd doc-insight-ai
    streamlit run frontend/app.py
"""

import json
import sys
import logging
from pathlib import Path

# Tambahkan root project ke path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from agents.orchestrator import InvoicePipeline, PipelineResult

# ------------------------------------------------------------------
# Config & Logging
# ------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

st.set_page_config(
    page_title="Invoice AI — Fase 1",
    page_icon="📄",
    layout="wide",
)

# ------------------------------------------------------------------
# Session State
# ------------------------------------------------------------------

if "pipeline" not in st.session_state:
    st.session_state.pipeline = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "log_messages" not in st.session_state:
    st.session_state.log_messages = []


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def get_pipeline(model: str, ollama_url: str) -> InvoicePipeline:
    """Inisialisasi atau reinit pipeline jika setting berubah."""
    key = f"{model}_{ollama_url}"
    if st.session_state.get("pipeline_key") != key:
        st.session_state.pipeline = InvoicePipeline(
            ollama_model=model,
            ollama_url=ollama_url,
            db_path="storage/invoices.db",
        )
        st.session_state.pipeline_key = key
    return st.session_state.pipeline


def status_badge(status: str) -> str:
    colors = {
        "success": "🟢",
        "partial": "🟡",
        "failed": "🔴",
        "skipped": "⚫",
    }
    return f"{colors.get(status, '⚪')} {status.upper()}"


def format_currency(val, currency="IDR") -> str:
    if val is None:
        return "—"
    if currency == "IDR":
        return f"Rp {val:,.0f}"
    return f"{currency} {val:,.2f}"


# ------------------------------------------------------------------
# Sidebar — Konfigurasi
# ------------------------------------------------------------------

with st.sidebar:
    st.title("⚙️ Konfigurasi")

    st.subheader("Model LLM")
    ollama_url = st.text_input("Ollama URL", value="http://localhost:11434")
    model_options = ["mistral", "llama3.1", "llama3.1:8b", "phi3:medium", "qwen2.5"]
    ollama_model = st.selectbox("Model", options=model_options, index=0)
    custom_model = st.text_input("Custom model (opsional)", placeholder="nama:tag")
    if custom_model:
        ollama_model = custom_model

    st.divider()

    # Cek koneksi
    if st.button("🔌 Cek Koneksi Ollama", use_container_width=True):
        with st.spinner("Mengecek..."):
            pipeline = get_pipeline(ollama_model, ollama_url)
            checks = pipeline.check_dependencies()
            for name, check in checks.items():
                if check["ok"]:
                    st.success(f"✅ {name}: {check['message']}")
                else:
                    st.error(f"❌ {name}: {check['message']}")

    st.divider()
    st.caption("**Doc Insight AI — Fase 1**")
    st.caption("Invoice OCR + LLM Extraction")

# ------------------------------------------------------------------
# Main Content
# ------------------------------------------------------------------

st.title("📄 Invoice AI Pipeline — Fase 1")
st.caption("Upload invoice (PDF/gambar) → OCR → LLM Extraction → Validasi → Hasil terstruktur")

tab1, tab2, tab3 = st.tabs(["🔍 Proses Invoice", "📊 Database", "🧪 Raw Teks"])

# ══════════════════════════════════════════════════════════════
# TAB 1: Upload & Proses
# ══════════════════════════════════════════════════════════════

with tab1:
    col_upload, col_result = st.columns([1, 1], gap="large")

    with col_upload:
        st.subheader("Upload Invoice")
        uploaded_file = st.file_uploader(
            "Pilih file invoice",
            type=["pdf", "jpg", "jpeg", "png", "tiff"],
            help="Mendukung PDF (digital & scan), JPG, PNG, TIFF",
        )

        if uploaded_file:
            # Preview file
            if uploaded_file.type.startswith("image"):
                st.image(uploaded_file, caption=uploaded_file.name, use_column_width=True)
            else:
                st.info(f"📁 File: **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")

            st.divider()

            if st.button("🚀 Proses Invoice", type="primary", use_container_width=True):
                # Simpan file sementara
                import tempfile, os
                suffix = Path(uploaded_file.name).suffix
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name

                try:
                    pipeline = get_pipeline(ollama_model, ollama_url)
                    progress_container = st.empty()
                    log_lines = []

                    def on_progress(msg: str):
                        log_lines.append(msg)
                        progress_container.info(f"⏳ {msg}")

                    with st.spinner("Memproses..."):
                        result: PipelineResult = pipeline.process_file(
                            tmp_path,
                            progress_cb=on_progress,
                        )
                        # Rename untuk display yang lebih baik
                        result.file_name = uploaded_file.name

                    st.session_state.last_result = result
                    st.session_state.log_messages = log_lines
                    progress_container.empty()

                    if result.status == "success":
                        st.success("✅ Invoice berhasil diproses!")
                    elif result.status == "partial":
                        st.warning("⚠️ Diproses dengan beberapa peringatan")
                    else:
                        st.error("❌ Gagal memproses invoice")

                finally:
                    os.unlink(tmp_path)

    # ── Hasil Ekstraksi ──
    with col_result:
        result: PipelineResult = st.session_state.last_result

        if result is None:
            st.info("Upload dan proses invoice untuk melihat hasil di sini.")
        else:
            st.subheader(f"Hasil: {status_badge(result.status)}")

            if result.error_message:
                st.error(result.error_message)
            
            # Metrik ringkasan
            m1, m2, m3 = st.columns(3)
            m1.metric("OCR Source", result.ocr_source_type or "—")
            m2.metric(
                "Extraction Conf.",
                f"{result.extraction.confidence * 100:.0f}%" if result.extraction else "—"
            )
            m3.metric("Waktu Proses", f"{result.processing_time_sec}s" if result.processing_time_sec else "—")

            st.divider()

            if result.extraction and result.extraction.data:
                inv = result.extraction.data

                # ── Info Utama ──
                st.markdown("**Informasi Utama**")
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"📋 **No. Invoice:** {inv.no_invoice or '—'}")
                    st.write(f"🏢 **Vendor:** {inv.vendor_nama or '—'}")
                    st.write(f"👤 **Pembeli:** {inv.pembeli_nama or '—'}")
                with c2:
                    st.write(f"📅 **Tanggal:** {inv.tanggal_invoice or '—'}")
                    st.write(f"⏰ **Jatuh Tempo:** {inv.tanggal_jatuh_tempo or '—'}")
                    st.write(f"💳 **Metode Bayar:** {inv.metode_pembayaran or '—'}")

                # ── Finansial ──
                st.divider()
                st.markdown("**Ringkasan Finansial**")
                f1, f2, f3 = st.columns(3)
                f1.metric("Subtotal", format_currency(inv.subtotal, inv.mata_uang or "IDR"))
                f2.metric("PPN", format_currency(inv.ppn_nominal, inv.mata_uang or "IDR"))
                f3.metric("Total", format_currency(inv.total, inv.mata_uang or "IDR"))

                # ── Line Items ──
                if inv.line_items:
                    st.divider()
                    st.markdown(f"**Line Items ({len(inv.line_items)} item)**")
                    items_df = pd.DataFrame([
                        {
                            "Deskripsi": item.deskripsi,
                            "Qty": item.qty,
                            "Satuan": item.satuan,
                            "Harga Satuan": format_currency(item.harga_satuan),
                            "Total": format_currency(item.total_harga),
                        }
                        for item in inv.line_items
                    ])
                    st.dataframe(items_df, use_container_width=True, hide_index=True)

                # ── Validasi ──
                if result.validation:
                    st.divider()
                    val = result.validation
                    st.markdown("**Laporan Validasi**")

                    if val.errors:
                        for e in val.errors:
                            st.error(f"❌ {e}")
                    if val.warnings:
                        for w in val.warnings:
                            st.warning(f"⚠️ {w}")
                    if val.anomaly_flags:
                        for a in val.anomaly_flags:
                            st.error(f"🚨 {a}")
                    if val.suggestions:
                        with st.expander("💡 Saran"):
                            for s in val.suggestions:
                                st.info(s)
                    if val.is_valid and not val.anomaly_flags:
                        st.success("✅ Semua validasi lolos!")

                # ── JSON Output ──
                with st.expander("📦 JSON Output Lengkap"):
                    st.json(json.loads(inv.model_dump_json()))

            # Log proses
            if st.session_state.log_messages:
                with st.expander("📝 Log Proses"):
                    for msg in st.session_state.log_messages:
                        st.text(f"  {msg}")

# ══════════════════════════════════════════════════════════════
# TAB 2: Database
# ══════════════════════════════════════════════════════════════

with tab2:
    st.subheader("Invoice yang Sudah Diproses")

    pipeline = get_pipeline(ollama_model, ollama_url)

    col_refresh, col_filter = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    invoices = pipeline.get_processed_invoices(limit=200)

    if not invoices:
        st.info("Belum ada invoice yang diproses. Upload dan proses di tab pertama.")
    else:
        # Filter
        statuses = list({inv["status"] for inv in invoices})
        with col_filter:
            selected_status = st.multiselect(
                "Filter status:", statuses, default=statuses
            )

        filtered = [i for i in invoices if i["status"] in selected_status]

        # Ringkasan metrik
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Invoice", len(filtered))
        m2.metric("Sukses", sum(1 for i in filtered if i["status"] == "success"))
        m3.metric("Partial", sum(1 for i in filtered if i["status"] == "partial"))
        m4.metric("Gagal", sum(1 for i in filtered if i["status"] == "failed"))

        # Total value
        totals = [i["total"] for i in filtered if i.get("total")]
        if totals:
            st.metric("Total Nilai Invoice", f"Rp {sum(totals):,.0f}")

        st.divider()

        df = pd.DataFrame(filtered)
        display_cols = [
            "file_name", "status", "no_invoice", "vendor_nama",
            "tanggal_invoice", "total", "extraction_confidence",
            "validation_valid", "processed_at"
        ]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[available_cols].rename(columns={
                "file_name": "File",
                "status": "Status",
                "no_invoice": "No. Invoice",
                "vendor_nama": "Vendor",
                "tanggal_invoice": "Tanggal",
                "total": "Total (IDR)",
                "extraction_confidence": "Confidence",
                "validation_valid": "Valid",
                "processed_at": "Diproses",
            }),
            use_container_width=True,
            hide_index=True,
        )

# ══════════════════════════════════════════════════════════════
# TAB 3: Raw Teks Debug
# ══════════════════════════════════════════════════════════════

with tab3:
    st.subheader("Debug: Raw Teks OCR")
    st.caption("Lihat teks mentah hasil OCR sebelum dikirim ke LLM")

    debug_file = st.file_uploader(
        "Upload file untuk preview OCR saja",
        type=["pdf", "jpg", "jpeg", "png"],
        key="debug_uploader",
    )

    if debug_file:
        if st.button("🔍 Jalankan OCR", type="secondary"):
            import tempfile, os
            from agents.ocr_agent import OCRAgent

            suffix = Path(debug_file.name).suffix
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(debug_file.read())
                tmp_path = tmp.name

            try:
                with st.spinner("Menjalankan OCR..."):
                    ocr = OCRAgent()
                    ocr_result = ocr.process(tmp_path)

                col1, col2 = st.columns(2)
                col1.metric("Source Type", ocr_result.source_type)
                col2.metric("OCR Confidence", f"{ocr_result.confidence:.2%}")

                if ocr_result.error:
                    st.error(f"Error: {ocr_result.error}")
                else:
                    st.text_area(
                        f"Raw teks OCR ({len(ocr_result.raw_text)} chars)",
                        value=ocr_result.raw_text,
                        height=400,
                    )
            finally:
                os.unlink(tmp_path)