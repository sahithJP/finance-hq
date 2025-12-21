import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Finance & Life", page_icon="🧬", layout="wide")

# --- AUTHENTICATION ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- HELPER: CLEAN DURATION ---
def parse_duration_to_hours(x):
    """Converts '1:00:00' OR '3600' into Hours (float)"""
    x = str(x).strip()
    try:
        # Case A: Format "H:MM:SS" (e.g., "1:00:00")
        if ':' in x:
            parts = x.split(':')
            if len(parts) == 3: # H:M:S
                h, m, s = map(float, parts)
                return h + (m/60) + (s/3600)
            elif len(parts) == 2: # M:S
                m, s = map(float, parts)
                return (m/60) + (s/3600)
        
        # Case B: Pure Seconds (e.g., "3600")
        val = float(x)
        return val / 3600  # Convert seconds to hours
    except:
        return 0

# --- LOAD DATA ---
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sh = client.open("Master_Finance_DB")
    
    # 1. FINANCE DATA
    try:
        ws_tx = sh.sheet1
        raw_tx = ws_tx.get_all_values()
        if len(raw_tx) > 1:
            df_tx = pd.DataFrame(raw_tx[1:], columns=raw_tx[0])
            # Clean Amount
            df_tx['Amount'] = df_tx['Amount'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
            df_tx['Amount'] = pd.to_numeric(df_tx['Amount'], errors='coerce').fillna(0)
            # Clean Date
            df_tx['Date'] = df_tx['Date'].astype(str).apply(lambda x: x.split(' ')[0])
            df_tx['Date'] = pd.to_datetime(df_tx['Date'], errors='coerce')
            df_tx = df_tx.dropna(subset=['Date'])
            df_tx['Month_Sort'] = df_tx['Date'].dt.strftime('%Y-%m')
        else:
            df_tx = pd.DataFrame()
    except:
        df_tx = pd.DataFrame()

    # 2. TIME LOGS
    try:
        # Check if tab exists
        if "Time_Logs" in [w.title for w in sh.worksheets()]:
            ws_time = sh.worksheet("Time_Logs")
            raw_time = ws_time.get_all_values()
            
            if len(raw_time) > 1:
                df_time = pd.DataFrame(raw_time[1:], columns=raw_time[0])
                
                # THE FIX: Use custom parser for "1:00:00"
                df_time['Hours'] = df_time['Duration_Mins'].apply(parse_duration_to_hours)
                
                # Clean Date
                df_time['Date'] = pd.to_datetime(df_time['Date'].astype(str).apply(lambda x: x.split('T')[0]), errors='coerce')
                df_time['Month_Sort'] = df_time['Date'].dt.strftime('%Y-%m')
            else:
                df_time = pd.DataFrame()
        else:
            df_time = pd.DataFrame()
    except:
        df_time = pd.DataFrame()

    return df_tx, df_time

# --- MAIN APP ---
st.title("🧬 Life Operating System")

df_tx, df_time = load_data()

# Global Month Filter
all_months = set()
if not df_tx.empty: all_months.update(df_tx['Month_Sort'].dropna())
if not df_time.empty: all_months.update(df_time['Month_Sort'].dropna())
all_months = sorted(list(all_months), reverse=True)

selected_month = st.sidebar.selectbox("Select Month", all_months) if all_months else "No Data"

# Filter
sub_tx = df_tx[df_tx['Month_Sort'] == selected_month] if not df_tx.empty else pd.DataFrame()
sub_time = df_time[df_time['Month_Sort'] == selected_month] if not df_time.empty else pd.DataFrame()

# TABS
tab1, tab2 = st.tabs(["💰 Finance", "⏳ Time Audit"])

with tab1:
    if not sub_tx.empty:
        total = sub_tx['Amount'].sum()
        st.metric("Total Spend", f"₹{total:,.0f}")
        daily = sub_tx.groupby('Date')['Amount'].sum().reset_index()
        st.plotly_chart(px.bar(daily, x='Date', y='Amount', title="Daily Trend"), use_container_width=True)
    else:
        st.info("No finance data.")

with tab2:
    if not sub_time.empty:
        # Metrics
        total_hrs = sub_time['Hours'].sum()
        
        # Determine "Work" vs "Life" based on Calendar Names
        # Note: Your calendar name is currently your email "pranaysahith@gmail.com"
        # You should rename calendars in Apple Calendar app to "Work", "Gym" for better charts.
        
        c1, c2 = st.columns(2)
        c1.metric("Total Tracked", f"{total_hrs:.1f} Hrs")
        
        # Charts
        st.subheader("Where did the time go?")
        fig = px.pie(sub_time, values='Hours', names='Category', hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("Raw Log")
        st.dataframe(sub_time[['Date', 'Event', 'Category', 'Hours', 'Duration_Mins']])
    else:
        st.warning("No time logs found for this month.")