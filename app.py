import streamlit as st
import easyocr
import pandas as pd
import numpy as np
from PIL import Image
import re

# Set Page & Theme
st.set_page_config(page_title="AssetControl PWA", layout="wide", initial_sidebar_state="collapsed")

# Load OCR dengan Cache agar tidak berat saat loading
@st.cache_resource
def load_reader():
    return easyocr.Reader(['en'], gpu=False) # Cloud biasanya tidak pakai GPU

reader = load_reader()

# Judul Minimalis untuk Mobile
st.title("📱 Asset Control OCR")
st.caption("Efisienkan kelola aset Saham & Crypto Anda")

# Sidebar Settings
with st.sidebar:
    st.header("⚙️ Konfigurasi")
    kurs = st.number_input("Kurs USD ke IDR", value=16000, step=100)

# 1. UPLOAD SECTION
uploaded_file = st.file_uploader("Upload Screenshot Portofolio", type=['png', 'jpg', 'jpeg'])

if 'all_assets' not in st.session_state:
    st.session_state.all_assets = []

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="Preview", width=250)
    
    if st.button("🚀 Scan Aset Sekarang", use_container_width=True):
        with st.spinner("Membaca teks..."):
            results = reader.readtext(np.array(img))
            # Ambil teks kapital 2-6 karakter (Ticker)
            detected = [re.sub(r'[^A-Z]', '', res[1].upper()) for res in results]
            st.session_state.all_assets = sorted(list(set([t for t in detected if 2 <= len(t) <= 6])))
            st.success(f"Ditemukan {len(st.session_state.all_assets)} kode aset")

# 2. TAB CONTROL
tab_saham, tab_crypto = st.tabs(["📊 Saham US", "🪙 Crypto"])

with tab_saham:
    if st.session_state.all_assets:
        pilihan_saham = st.multiselect("Pilih Ticker Saham:", st.session_state.all_assets, key="ms_saham")
        df_saham = pd.DataFrame({'Ticker': pilihan_saham, 'Jual (US$)': [0.0]*len(pilihan_saham)})
        edited_saham = st.data_editor(df_saham, num_rows="dynamic", key="edit_saham", use_container_width=True)
        total_s = edited_saham['Jual (US$)'].sum()
        st.info(f"Subtotal Saham: ${total_s:,.2f}")
    else:
        st.write("Silahkan upload & scan dulu.")

with tab_crypto:
    if st.session_state.all_assets:
        pilihan_crypto = st.multiselect("Pilih Ticker Crypto:", st.session_state.all_assets, key="ms_crypto")
        df_crypto = pd.DataFrame({'Ticker': pilihan_crypto, 'Jual (US$)': [0.0]*len(pilihan_crypto)})
        edited_crypto = st.data_editor(df_crypto, num_rows="dynamic", key="edit_crypto", use_container_width=True)
        total_c = edited_crypto['Jual (US$)'].sum()
        st.info(f"Subtotal Crypto: ${total_c:,.2f}")
    else:
        st.write("Silahkan upload & scan dulu.")

# 3. RINGKASAN & DISTRIBUSI (EFFICIENCY CALCULATOR)
st.divider()
total_usd = (total_s if 'total_s' in locals() else 0) + (total_c if 'total_c' in locals() else 0)
total_idr = total_usd * kurs

st.subheader("💰 Ringkasan Distribusi")
c1, c2 = st.columns(2)
c1.metric("Total Pool (US$)", f"${total_usd:,.2f}")
c2.metric("Total Pool (IDR)", f"Rp {total_idr:,.0f}")

persen_reinvest = st.select_slider("Rencana Re-investasi (%)", options=[0, 10, 25, 50, 75, 100], value=50)
reinvest_val = total_usd * (persen_reinvest/100)
cashout_val = total_usd - reinvest_val

st.warning(f"Saran: Re-investasikan **${reinvest_val:,.2f}** dan tarik tunai **Rp {(cashout_val*kurs):,.0f}**")
