import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import pytesseract
import cv2
import os
import subprocess
import sys
import json
import base64

# --- Konfigurasi Halaman ---
st.set_page_config(
    page_title="Smart Rebalance Scanner",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Instalasi Tesseract Otomatis untuk Streamlit Cloud ---
@st.cache_resource
def check_tesseract():
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

if not check_tesseract():
    with st.spinner('Menginstall Tesseract OCR Engine... (Hanya sekali di awal)'):
        try:
            # Untuk lingkungan Linux (Streamlit Cloud)
            subprocess.check_call(['sudo', 'apt-get', 'update'])
            subprocess.check_call(['sudo', 'apt-get', 'install', '-y', 'tesseract-ocr'])
            subprocess.check_call(['sudo', 'apt-get', 'install', '-y', 'libtesseract-dev'])
            st.success("Tesseract berhasil diinstall!")
        except Exception as e:
            st.error(f"Gagal install Tesseract: {e}")
            st.info("Jika di lokal, pastikan Tesseract sudah terinstall di PC Anda.")

# Set path tesseract jika di linux (biasanya sudah default, tapi untuk jaga-jaga)
if os.name != 'nt': # Jika bukan Windows
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# --- Fungsi Helper ---
def fmt_idr(num):
    """Format angka ke format Rupiah"""
    if pd.isna(num) or num == 0:
        return "Rp 0"
    return f"Rp {int(num):,.0f}".replace(",", ".")

def parse_idr(text):
    """Parse string Rupiah ke float"""
    if not text:
        return 0.0
    # Hapus Rp, titik, dan spasi
    clean = str(text).replace("Rp", "").replace(".", "").replace(",", "").replace(" ", "")
    try:
        return float(clean)
    except:
        return 0.0

def ocr_image(image):
    """Melakukan OCR pada gambar dan mengembalikan dataframe aset"""
    # Preprocessing gambar untuk akurasi lebih baik
    open_cv_image = np.array(image)
    # Convert RGB to BGR 
    open_cv_image = open_cv_image[:, :, ::-1].copy()
    # Convert to grayscale
    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
    # Thresholding (binerisasi)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    
    # Custom config for better ticker/number recognition
    custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,$ IDR BTC ETH USD'
    
    data = pytesseract.image_to_data(thresh, config=custom_config, output_type=pytesseract.Output.DICT)
    
    assets = []
    n_boxes = len(data['text'])
    
    # Logika sederhana: Cari baris yang punya Ticker (Huruf Besar) dan Angka Besar
    # Kita akan grouping berdasarkan baris (top coordinate)
    lines = {}
    for i in range(n_boxes):
        if int(data['conf'][i]) > 30: # Hanya ambil teks dengan confidence > 30%
            text = data['text'][i].strip()
            if text:
                top = data['top'][i]
                if top not in lines:
                    lines[top] = []
                lines[top].append(text)
    
    # Proses setiap baris
    for top, words in lines.items():
        line_text = " ".join(words)
        # Regex sederhana untuk mencari pola: [TICKER] ... [ANGKA]
        # Contoh: "BTC 15.000.000" atau "NVDA $400"
        
        ticker = ""
        value = 0
        
        # Cari Ticker (2-5 huruf kapital)
        import re
        tickers_found = re.findall(r'\b[A-Z]{2,5}\b', line_text)
        
        # Cari Angka (dengan titik/koma)
        numbers_found = re.findall(r'\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\b', line_text)
        # Juga cari angka polos jika formatnya tanpa titik
        if not numbers_found:
            numbers_found = re.findall(r'\b\d+\b', line_text)

        if tickers_found:
            ticker = tickers_found[0]
            # Filter kata-kata umum yang bukan ticker
            ignore_list = ["USD", "IDR", "THE", "AND", "FOR", "BUY", "SELL", "TOTAL", "PAGE", "DATE"]
            if ticker not in ignore_list:
                if numbers_found:
                    # Ambil angka terbesar di baris tersebut sebagai nilai
                    # Bersihkan format angka
                    clean_nums = []
                    for n in numbers_found:
                        clean_n = n.replace(".", "").replace(",", "")
                        try:
                            clean_nums.append(float(clean_n))
                        except:
                            pass
                    
                    if clean_nums:
                        value = max(clean_nums)
                        # Filter nilai yang terlalu kecil (noise)
                        if value > 10000: 
                            assets.append({
                                "Ticker": ticker,
                                "Nilai Saat Ini": value,
                                "Target %": 0.0 # Default 0, user isi manual
                            })

    return pd.DataFrame(assets)

# --- Session State ---
if 'assets_crypto' not in st.session_state:
    st.session_state.assets_crypto = pd.DataFrame(columns=["Ticker", "Nilai Saat Ini", "Target %"])
if 'assets_stock' not in st.session_state:
    st.session_state.assets_stock = pd.DataFrame(columns=["Ticker", "Nilai Saat Ini", "Target %"])
if 'total_portfolio' not in st.session_state:
    st.session_state.total_portfolio = 10000000
if 'kurs_usd' not in st.session_state:
    st.session_state.kurs_usd = 16000

# --- UI Header ---
st.markdown("""
    <style>
    .big-font { font-size: 20px !important; font-weight: bold; }
    .stButton>button { width: 100%; }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Smart Rebalance Scanner")

# Tab Navigation
tab_crypto, tab_stock = st.tabs(["🪙 CRYPTO", "📈 STOCKS"])

def render_tab(tab_name, df_key):
    df = st.session_state[df_key]
    
    # Control Panel
    col1, col2 = st.columns(2)
    with col1:
        total_porto = st.number_input("Total Portofolio (IDR)", value=st.session_state.total_portfolio, step=100000, key=f"total_{tab_name}")
        st.session_state.total_portfolio = total_porto
    with col2:
        kurs = st.number_input("Kurs USD (Manual)", value=st.session_state.kurs_usd, step=100, key=f"kurs_{tab_name}")
        st.session_state.kurs_usd = kurs

    st.divider()

    # Scanner Section
    st.subheader("📸 Scan Screenshot")
    uploaded_file = st.file_uploader("Upload Screenshot Portofolio", type=['jpg', 'png', 'jpeg'], key=f"upload_{tab_name}")
    
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        with st.spinner('🔍 Memindai Aset... Mohon tunggu...'):
            new_assets = ocr_image(image)
        
        if not new_assets.empty:
            # Gabungkan dengan data existing
            st.session_state[df_key] = pd.concat([df, new_assets], ignore_index=True)
            st.success(f"✅ Berhasil scan {len(new_assets)} aset! Silakan lengkapi Target %.")
        else:
            st.warning("❌ Tidak ditemukan aset valid. Pastikan screenshot jelas.")

    st.divider()

    # Manual Input
    with st.expander("➕ Tambah Aset Manual"):
        m_col1, m_col2, m_col3 = st.columns([2, 1, 2])
        with m_col1:
            m_ticker = st.text_input("Nama Aset", key=f"m_ticker_{tab_name}")
        with m_col2:
            m_pct = st.number_input("Target %", min_value=0.0, max_value=100.0, step=0.1, key=f"m_pct_{tab_name}")
        with m_col3:
            m_val = st.number_input("Nilai Saat Ini (IDR)", min_value=0.0, step=10000.0, key=f"m_val_{tab_name}")
        
        if st.button("Simpan Aset", key=f"btn_save_{tab_name}"):
            if m_ticker and m_val > 0:
                new_row = pd.DataFrame([{
                    "Ticker": m_ticker.upper(),
                    "Nilai Saat Ini": m_val,
                    "Target %": m_pct
                }])
                st.session_state[df_key] = pd.concat([st.session_state[df_key], new_row], ignore_index=True)
                st.rerun()

    # Table Display & Calculation
    st.subheader("Daftar Aset & Instruksi Rebalancing")
    
    if df.empty:
        st.info("Belum ada aset. Upload screenshot atau tambah manual.")
    else:
        # Editable DataFrame
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
        
        # Update session state with edited data
        st.session_state[df_key] = edited_df
        
        # Calculate Action
        results = []
        for index, row in edited_df.iterrows():
            target_val = total_porto * (row["Target %"] / 100)
            diff = target_val - row["Nilai Saat Ini"]
            
            action = "HOLD"
            color = "grey"
            nominal = 0
            
            if diff > 10000: # Toleransi 10rb
                action = "BELI"
                color = "green"
                nominal = diff
            elif diff < -10000:
                action = "JUAL"
                color = "red"
                nominal = abs(diff)
                
            results.append({
                "Ticker": row["Ticker"],
                "Action": action,
                "Nominal": nominal,
                "Color": color
            })
            
        res_df = pd.DataFrame(results)
        
        # Display Result with Colors
        def color_action(val):
            if val == "BELI":
                return 'background-color: #d1fae5; color: #065f46; font-weight: bold'
            elif val == "JUAL":
                return 'background-color: #fee2e2; color: #991b1b; font-weight: bold'
            else:
                return 'background-color: #f1f5f9; color: #475569'

        def fmt_nominal(val):
            return fmt_idr(val)

        st.dataframe(
            res_df.style.applymap(color_action, subset=['Action']).format(fmt_nominal, subset=['Nominal']),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Ticker": st.column_config.TextColumn("Aset"),
                "Action": st.column_config.TextColumn("Instruksi"),
                "Nominal": st.column_config.TextColumn("Estimasi Dana"),
            }
        )

# Render Tabs
with tab_crypto:
    render_tab("CRYPTO", "assets_crypto")

with tab_stock:
    render_tab("STOCKS", "assets_stock")

# Footer
st.markdown("---")
st.caption("Dibuat untuk Rebalancing & Compounding Portofolio")
