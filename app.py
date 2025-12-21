import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import calendar

# --- CONFIGURATION ---
st.set_page_config(page_title="Life Operating System", page_icon="🧬", layout="wide")

# --- AUTHENTICATION ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- HELPER: TIME CLEANER ---
def parse_duration_to_hours(x):
    """Converts '1:00:00' OR '3600' into Hours (float)"""
    x = str(x).strip()
    try:
        if ':' in x:
            parts = x.split(':')
            if len(parts) == 3: return float(parts[0]) + (float(parts[1])/60) + (float(parts[2])/3600)
            elif len(parts) == 2: return (float(parts[0])/60) + (float(parts[1])/3600)
        return float(x) / 3600
    except:
        return 0

# --- LOAD DATA (ALL SHEETS) ---
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sh = client.open("Master_Finance_DB")
    
    # 1. FINANCE TRANSACTIONS
    try:
        ws_tx = sh.sheet1
        raw_tx = ws_tx.get_all_values()
        df_tx = pd.DataFrame(raw_tx[1:], columns=raw_tx[0]) if len(raw_tx) > 1 else pd.DataFrame()
        if not df_tx.empty:
            df_tx['Amount'] = pd.to_numeric(df_tx['Amount'].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0)
            df_tx['Date'] = pd.to_datetime(df_tx['Date'].astype(str).apply(lambda x: x.split(' ')[0]), errors='coerce')
            df_tx['Month_Sort'] = df_tx['Date'].dt.strftime('%Y-%m')
    except: df_tx = pd.DataFrame()

    # 2. BUDGET TARGETS
    try:
        ws_budget = sh.worksheet("Budgets")
        raw_b = ws_budget.get_all_values()
        df_budget = pd.DataFrame(raw_b[1:], columns=raw_b[0]) if len(raw_b) > 1 else pd.DataFrame()
        if not df_budget.empty:
            df_budget['Monthly_Limit'] = pd.to_numeric(df_budget['Monthly_Limit'].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0)
    except: df_budget = pd.DataFrame(columns=['Category', 'Monthly_Limit'])

    # 3. TIME LOGS
    try:
        ws_time = sh.worksheet("Time_Logs")
        raw_time = ws_time.get_all_values()
        df_time = pd.DataFrame(raw_time[1:], columns=raw_time[0]) if len(raw_time) > 1 else pd.DataFrame()
        if not df_time.empty:
            # Fix Duration
            if 'Duration_Mins' in df_time.columns:
                df_time['Hours'] = df_time['Duration_Mins'].apply(parse_duration_to_hours)
            else:
                df_time['Hours'] = 0
            
            df_time['Date'] = pd.to_datetime(df_time['Date'].astype(str).apply(lambda x: x.split('T')[0]), errors='coerce')
            df_time['Month_Sort'] = df_time['Date'].dt.strftime('%Y-%m')
            df_time['Category'] = df_time['Category'].astype(str).str.strip()
    except: df_time = pd.DataFrame()

    return df_tx, df_budget, df_time

# --- MAIN LOGIC ---
try:
    df_tx, df_budget, df_time = load_data()
except Exception as e:
    st.error(f"Data Error: {e}")
    st.stop()

# --- SIDEBAR: INPUT & FILTERS ---
with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    st.divider()

    # Month Selector
    all_months = set()
    if not df_tx.empty: all_months.update(df_tx['Month_Sort'].dropna())
    if not df_time.empty: all_months.update(df_time['Month_Sort'].dropna())
    all_months = sorted(list(all_months), reverse=True)
    selected_month = st.selectbox("Select Month", all_months) if all_months else "No Data"

    st.divider()

    # ADD TRANSACTION FORM
    with st.form(key='add_txn_form'):
        st.header("➕ Add Expense")
        input_amount = st.number_input("Amount", min_value=0.0, step=10.0)
        input_category = st.selectbox("Category", ["Food", "Transport", "Bills", "Shopping", "Entertainment", "Health", "Investments"])
        input_desc = st.text_input("Description")
        input_mode = st.selectbox("Payment Mode", ["UPI", "Credit Card", "Cash"])
        
        if st.form_submit_button('Save'):
            try:
                client = get_gspread_client()
                sheet = client.open("Master_Finance_DB").sheet1
                # IST Time Calculation
                ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
                date_str = ist_now.strftime("%Y-%m-%d %H:%M:%S")
                sheet.append_row([date_str, input_amount, input_category, input_desc, input_mode])
                st.success(f"Saved!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# --- DASHBOARD TABS ---
tab_fin, tab_budget, tab_time, tab_raw = st.tabs(["📊 Analytics", "🎯 Budget vs Actual", "⏳ Time Audit", "📄 Data"])

# 1. FILTER DATA
sub_tx = df_tx[df_tx['Month_Sort'] == selected_month] if not df_tx.empty else pd.DataFrame()
sub_time = df_time[df_time['Month_Sort'] == selected_month] if not df_time.empty else pd.DataFrame()

# --- TAB 1: ANALYTICS (BURNDOWN) ---
with tab_fin:
    if not sub_tx.empty:
        total_spend = sub_tx['Amount'].sum()
        total_budget = df_budget['Monthly_Limit'].sum() if not df_budget.empty else 0
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Spent", f"₹{total_spend:,.0f}")
        k2.metric("Budget Limit", f"₹{total_budget:,.0f}")
        k3.metric("Remaining", f"₹{total_budget - total_spend:,.0f}", delta_color="normal")
        
        c1, c2 = st.columns([2, 1])
        with c1:
            # BURNDOWN CHART
            if total_budget > 0:
                year, month = map(int, selected_month.split('-'))
                last_day = calendar.monthrange(year, month)[1]
                all_dates = pd.date_range(start=f"{selected_month}-01", end=f"{selected_month}-{last_day}")
                
                daily_spends = sub_tx.groupby('Date')['Amount'].sum().reindex(all_dates, fill_value=0).reset_index()
                daily_spends.columns = ['Date', 'Daily_Spend']
                daily_spends['Cumulative_Spend'] = daily_spends['Daily_Spend'].cumsum()
                daily_spends['Remaining'] = total_budget - daily_spends['Cumulative_Spend']
                # Ideal Line
                daily_spends['Ideal'] = [total_budget - (total_budget/last_day * (i+1)) for i in range(len(daily_spends))]
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=daily_spends['Date'], y=daily_spends['Remaining'], mode='lines+markers', name='Actual', line=dict(color='#00CC96', width=3)))
                fig.add_trace(go.Scatter(x=daily_spends['Date'], y=daily_spends['Ideal'], mode='lines', name='Ideal Pace', line=dict(color='gray', dash='dash')))
                fig.update_layout(title="📉 Budget Burndown", xaxis_title="Date", yaxis_title="Remaining")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Set budgets in 'Budgets' tab to see Burndown chart.")
                
        with c2:
            cat_agg = sub_tx.groupby('Category')['Amount'].sum().reset_index()
            st.plotly_chart(px.pie(cat_agg, values='Amount', names='Category', hole=0.4), use_container_width=True)

# --- TAB 2: BUDGET VS ACTUAL ---
with tab_budget:
    if not sub_tx.empty and not df_budget.empty:
        actuals = sub_tx.groupby('Category')['Amount'].sum().reset_index()
        merged = pd.merge(df_budget, actuals, on='Category', how='outer').fillna(0)
        merged['Usage %'] = (merged['Amount'] / merged['Monthly_Limit']) * 100
        merged = merged.sort_values(by='Amount', ascending=False)
        
        for i, row in merged.iterrows():
            cat = row['Category']
            spent = row['Amount']
            limit = row['Monthly_Limit']
            pct = row['Usage %']
            
            col_status = "✅" if pct < 80 else "⚠️" if pct < 100 else "🚨"
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f"**{cat}** {col_status}")
                st.progress(min(int(pct), 100))
            with c2:
                st.write(f"₹{spent:,.0f} / ₹{limit:,.0f}")
    else:
        st.info("Add transactions and budget targets to see comparison.")

# ---