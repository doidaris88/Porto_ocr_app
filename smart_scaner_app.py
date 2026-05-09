import streamlit as st
import pandas as pd
import numpy as np
import json
import base64
from io import BytesIO

# Konfigurasi Halaman
st.set_page_config(
    page_title="Smart Rebalance Scanner",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS untuk tampilan bersih
st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .stButton>button { width: 100%; border-radius: 8px; }
    .badge-buy { background-color: #d1fae5; color: #065f46; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-sell { background-color: #fee2e2; color: #991b1b; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-hold { background-color: #f3f4f6; color: #374151; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- Fungsi Helper ---
def fmt_idr(num):
    if pd.isna(num) or num == 0:
        return "Rp 0"
    return f"Rp {int(num):,.0f}".replace(",", ".")

# --- Session State ---
if 'assets_crypto' not in st.session_state:
    st.session_state.assets_crypto = pd.DataFrame(columns=["Ticker", "Nilai Saat Ini", "Target %"])
if 'assets_stock' not in st.session_state:
    st.session_state.assets_stock = pd.DataFrame(columns=["Ticker", "Nilai Saat Ini", "Target %"])
if 'total_portfolio' not in st.session_state:
    st.session_state.total_portfolio = 10000000

# --- Komponen OCR JS (Hidden Logic) ---
# Kita menyisipkan script Tesseract.js langsung di browser
ocr_component = """
<div id="ocr-container" style="display:none;"></div>
<script src="https://unpkg.com/tesseract.js@v4.0.2/dist/tesseract.min.js"></script>
<script>
window.processImageForStreamlit = function(base64Image) {
    const img = new Image();
    img.src = base64Image;
    img.onload = function() {
        Tesseract.recognize(
            img,
            'eng',
            { logger: m => console.log(m) }
        ).then(({ data: { text } }) => {
            // Kirim hasil teks kembali ke Streamlit via window.parent
            window.parent.postMessage({ type: 'OCR_RESULT', text: text }, '*');
        });
    };
}
</script>
"""

st.components.v1.html(ocr_component, height=0)

# Logika menerima data dari JS
import streamlit.components.v1 as components
import asyncio

# Catatan: Streamlit standar sulit menerima postMessage langsung tanpa framework tambahan.
# Sebagai alternatif yang lebih mudah untuk pengguna awam di Streamlit Cloud tanpa backend kompleks:
# Kita akan menggunakan input file biasa, tapi memprosesnya dengan logika sederhana di Python 
# MENGGUNAKAN library 'pytesseract' TAPI dengan syarat user menginstall Tesseract di lokal, 
# ATAU kita gunakan pendekatan manual yang dipercepat.

# KARENA KENDALA SUDO DI CLOUD, SOLUSI TERBAIK ADALAH:
# 1. User Upload Gambar.
# 2. Kita tampilkan gambar.
# 3. User INPUT MANUAL nama aset dan nilai yang terbaca (Copy-Paste cepat).
# 4. Sistem menghitung rebalancing.

# Namun, agar tetap "Otomatis" sebisa mungkin di Cloud tanpa sudo, 
# kita bisa mencoba library 'easyocr' jika didukung, tapi sering berat.
# Mari kita buat versi yang paling stabil: **Input Manual Cepat dengan Tabel Editable**.
# Saya akan menambahkan fitur "Paste from Excel/Screenshot Text" jika user menyalin teks.

st.title("⚡ Smart Rebalance Manager")
st.caption("Kelola Portofolio & Hitung Rebalancing Otomatis")

tab_crypto, tab_stock = st.tabs(["🪙 CRYPTO", "📈 STOCKS"])

def render_tab(tab_name, df_key):
    df = st.session_state[df_key]
    
    col1, col2 = st.columns(2)
    with col1:
        total_porto = st.number_input("Total Portofolio (IDR)", value=st.session_state.total_portfolio, step=100000, key=f"total_{tab_name}")
        st.session_state.total_portfolio = total_porto
    with col2:
        kurs = st.number_input("Kurs USD (Manual)", value=16000, step=100, key=f"kurs_{tab_name}")

    st.divider()

    # Input Area
    st.subheader("Tambah Aset")
    st.info("💡 *Tips: Karena batasan server cloud, silakan masukkan data aset secara manual atau copy-paste dari screenshot Anda.*")
    
    col_a, col_b, col_c, col_d = st.columns([2, 1, 2, 1])
    with col_a:
        new_ticker = st.text_input("Nama Aset", key=f"in_ticker_{tab_name}")
    with col_b:
        new_pct = st.number_input("% Target", min_value=0.0, step=0.1, key=f"in_pct_{tab_name}")
    with col_c:
        new_val = st.number_input("Nilai Saat Ini (IDR)", min_value=0.0, step=10000.0, key=f"in_val_{tab_name}")
    with col_d:
        st.write("") # Spacer
        st.write("") # Spacer
        if st.button("➕ Tambah", key=f"btn_add_{tab_name}"):
            if new_ticker and new_val > 0:
                new_row = pd.DataFrame([{
                    "Ticker": new_ticker.upper(),
                    "Nilai Saat Ini": new_val,
                    "Target %": new_pct
                }])
                st.session_state[df_key] = pd.concat([df, new_row], ignore_index=True)
                st.rerun()

    st.divider()

    # Tabel Data & Kalkulasi
    if df.empty:
        st.warning("Belum ada data aset.")
    else:
        st.subheader("Daftar Aset & Instruksi Rebalancing")
        
        # Editable Table
        edited_df = st.data_editor(
            df,
            column_config={
                "Ticker": st.column_config.TextColumn("Aset", disabled=True),
                "Nilai Saat Ini": st.column_config.NumberColumn("Nilai Saat Ini (IDR)", format="%d"),
                "Target %": st.column_config.NumberColumn("Target %", min_value=0, max_value=100, step=0.1),
            },
            hide_index=True,
            use_container_width=True,
            key=f"editor_{tab_name}"
        )
        
        # Update state
        st.session_state[df_key] = edited_df
        
        # Hitung Action
        results = []
        for index, row in edited_df.iterrows():
            target_val = total_porto * (row["Target %"] / 100)
            diff = target_val - row["Nilai Saat Ini"]
            
            action = "HOLD"
            css_class = "badge-hold"
            nominal = 0
            
            if diff > 10000:
                action = "BELI"
                css_class = "badge-buy"
                nominal = diff
            elif diff < -10000:
                action = "JUAL"
                css_class = "badge-sell"
                nominal = abs(diff)
                
            results.append({
                "Ticker": row["Ticker"],
                "Action": f"<span class='{css_class}'>{action}</span>",
                "Nominal": fmt_idr(nominal)
            })
            
        res_df = pd.DataFrame(results)
        
        # Tampilkan dengan HTML rendering untuk warna
        st.markdown(res_df.to_html(escape=False, index=False), unsafe_allow_html=True)
        
        # Tombol Hapus Semua (Opsional)
        if st.button("🗑️ Reset Data Tab Ini", key=f"reset_{tab_name}"):
            st.session_state[df_key] = pd.DataFrame(columns=["Ticker", "Nilai Saat Ini", "Target %"])
            st.rerun()

with tab_crypto:
    render_tab("CRYPTO", "assets_crypto")

with tab_stock:
    render_tab("STOCKS", "assets_stock")

st.markdown("---")
st.caption("Dibuat untuk Rebalancing Portofolio | Data disimpan sementara di sesi browser.")
