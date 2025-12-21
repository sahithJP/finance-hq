import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Finance HQ", page_icon="💰", layout="wide")

# --- AUTHENTICATION ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- LOAD DATA (Defensive Mode) ---
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sh = client.open("Master_Finance_DB")
    
    # --- 1. FINANCE DATA (The Critical Part) ---
    try:
        ws_tx = sh.sheet1
        # Get all values (raw strings) to avoid format errors
        raw_tx = ws_tx.get_all_values()
        
        if len(raw_tx) > 1:
            df_tx = pd.DataFrame(raw_tx[1:], columns=raw_tx[0])
            
            # THE NUCLEAR FIX (Restored)
            # 1. Clean Amount: Remove anything that isn't a digit or dot
            df_tx['Amount'] = df_tx['Amount'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
            df_tx['Amount'] = pd.to_numeric(df_tx['Amount'], errors='coerce').fillna(0)
            
            # 2. Clean Date: Split by space to ignore time, force standard format
            df_tx['Date'] = df_tx['Date'].astype(str).apply(lambda x: x.split(' ')[0])
            df_tx['Date'] = pd.to_datetime(df_tx['Date'], errors='coerce')
            
            # Drop invalid rows
            df_tx = df_tx.dropna(subset=['Date'])
            df_tx['Month_Sort'] = df_tx['Date'].dt.strftime('%Y-%m')
        else:
            df_tx = pd.DataFrame()
    except Exception as e:
        st.error(f"Finance Data Error: {e}")
        df_tx = pd.DataFrame()

    # --- 2. TIME LOGS (Isolated) ---
    try:
        # Check if tab exists first
        worksheet_list = [w.title for w in sh.worksheets()]
        if "Time_Logs" in worksheet_list:
            ws_time = sh.worksheet("Time_Logs")
            raw_time = ws_time.get_all_values()
            
            if len(raw_time) > 1:
                df_time = pd.DataFrame(raw_time[1:], columns=raw_time[0])
                # Minimal cleaning for visibility
                df_time['Duration_Mins'] = pd.to_numeric(df_time['Duration_Mins'], errors='coerce').fillna(0)
                # Handle Apple's default seconds (divide by 3600 for hours)
                df_time['Hours'] = df_time['Duration_Mins'] / 3600
                
                df_time['Date'] = pd.to_datetime(df_time['Date'].astype(str).apply(lambda x: x.split('T')[0]), errors='coerce')
                df_time['Month_Sort'] = df_time['Date'].dt.strftime('%Y-%m')
            else:
                df_time = pd.DataFrame()
        else:
            df_time = pd.DataFrame()
    except Exception as e:
        # Don't crash the app if time logs fail
        st.warning(f"Time Log Warning: {e}")
        df_time = pd.DataFrame()

    return df_tx, df_time

# --- MAIN APP ---
st.title("💰 Finance & Life Control")

# Load Data
try:
    df_tx, df_time = load_data()
except Exception as e:
    st.error(f"Critical Connection Error: {e}")
    st.stop()

# --- DIAGNOSTICS (Debug View) ---
with st.expander("🛠️ Debug / Raw Data Checker"):
    c1, c2 = st.columns(2)
    with c1:
        st.write("Finance Sheet Raw:")
        st.dataframe(df_tx.head())
    with c2:
        st.write("Time Sheet Raw:")
        if df_time.empty:
            st.error("Time DataFrame is Empty. Check Google Sheet manually.")
        else:
            st.dataframe(df_time.head())

# --- FINANCE DASHBOARD ---
if not df_tx.empty:
    # Filter Setup
    all_months = sorted(df_tx['Month_Sort'].unique(), reverse=True)
    selected_month = st.sidebar.selectbox("Select Month", all_months)
    
    # Filter Data
    sub_tx = df_tx[df_tx['Month_Sort'] == selected_month]
    
    # Metrics
    spend = sub_tx['Amount'].sum()
    st.metric("Total Spend", f"₹{spend:,.0f}")
    
    # Chart
    daily = sub_tx.groupby('Date')['Amount'].sum().reset_index()
    st.plotly_chart(px.bar(daily, x='Date', y='Amount'), use_container_width=True)

# --- TIME DASHBOARD ---
st.divider()
st.subheader("⏳ Time Analysis")

if df_time.empty:
    st.info("No Time Data found. Please check the 'Debug' section above.")
else:
    # Filter Time (Safe Mode)
    # Ensure selected_month exists in time data, else show all
    if selected_month in df_time['Month_Sort'].values:
        sub_time = df_time[df_time['Month_Sort'] == selected_month]
    else:
        st.warning(f"No time logs for {selected_month}. Showing all data.")
        sub_time = df_time

    if not sub_time.empty:
        t_hours = sub_time['Hours'].sum()
        st.metric("Total Tracked Hours", f"{t_hours:.1f}")
        
        fig_time = px.pie(sub_time, values='Hours', names='Category', hole=0.4)
        st.plotly_chart(fig_time, use_container_width=True)
    else:
        st.write("Month selected has no time logs.")