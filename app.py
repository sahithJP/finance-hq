import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, date
import calendar
import numpy as np

# --- CONFIGURATION ---
st.set_page_config(page_title="Life Operating System", page_icon="🧬", layout="wide")

# --- AUTHENTICATION ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

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

    # 3. TIME LOGS (UPDATED FOR MANUAL ENTRY)
    try:
        ws_time = sh.worksheet("Time_Logs")
        raw_time = ws_time.get_all_values()
        df_time = pd.DataFrame(raw_time[1:], columns=raw_time[0]) if len(raw_time) > 1 else pd.DataFrame()
        if not df_time.empty:
            # We expect columns: Date, Category, Activity, Hours
            df_time['Hours'] = pd.to_numeric(df_time['Hours'], errors='coerce').fillna(0)
            df_time['Date'] = pd.to_datetime(df_time['Date'].astype(str), errors='coerce')
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

    # --- FORM 1: ADD EXPENSE ---
    with st.expander("💸 Add Expense", expanded=True):
        with st.form(key='add_txn_form'):
            input_amount = st.number_input("Amount", min_value=0.0, step=10.0)
            input_category = st.selectbox("Category", ["Food", "Transport", "Bills", "Shopping", "Entertainment", "Health", "Investments","Travel"])
            input_desc = st.text_input("Description (Expense)")
            input_mode = st.selectbox("Payment Mode", ["UPI", "Credit Card", "Cash","SI"])
            
            if st.form_submit_button('Save Expense'):
                try:
                    client = get_gspread_client()
                    sheet = client.open("Master_Finance_DB").sheet1
                    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
                    date_str = ist_now.strftime("%Y-%m-%d %H:%M:%S")
                    sheet.append_row([date_str, input_amount, input_category, input_desc, input_mode])
                    st.success("Expense Saved!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    # --- FORM 2: LOG TIME (NEW) ---
    with st.expander("⏱️ Log Time", expanded=False):
        with st.form(key='add_time_form'):
            # Default date is today
            t_date = st.date_input("Date", value=date.today())
            t_cat = st.selectbox("Category", ["Deep Work", "Meetings", "Commute", "Health/Gym", "Learning", "Life Admin", "Sleep", "Entertainment"])
            t_desc = st.text_input("Activity Description")
            t_hours = st.number_input("Hours Spent", min_value=0.1, step=0.5, format="%.1f")
            
            if st.form_submit_button('Save Time Log'):
                try:
                    client = get_gspread_client()
                    sh = client.open("Master_Finance_DB")
                    
                    # Ensure Time_Logs sheet exists or create it
                    try:
                        ws_t = sh.worksheet("Time_Logs")
                    except:
                        ws_t = sh.add_worksheet(title="Time_Logs", rows=1000, cols=5)
                        ws_t.append_row(["Date", "Category", "Activity", "Hours"])
                    
                    # Append Data
                    ws_t.append_row([str(t_date), t_cat, t_desc, t_hours])
                    st.success("Time Logged!")
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
            if total_budget > 0:
                year, month = map(int, selected_month.split('-'))
                last_day = calendar.monthrange(year, month)[1]
                all_dates = pd.date_range(start=f"{selected_month}-01", end=f"{selected_month}-{last_day}")
                
                daily_spends = sub_tx.groupby('Date')['Amount'].sum().reindex(all_dates, fill_value=0).reset_index()
                daily_spends.columns = ['Date', 'Daily_Spend']
                daily_spends['Cumulative_Spend'] = daily_spends['Daily_Spend'].cumsum()
                daily_spends['Remaining'] = total_budget - daily_spends['Cumulative_Spend']
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

# --- TAB 2: BUDGET VS ACTUAL (SAFE MODE) ---
with tab_budget:
    if not sub_tx.empty and not df_budget.empty:
        actuals = sub_tx.groupby('Category')['Amount'].sum().reset_index()
        merged = pd.merge(df_budget, actuals, on='Category', how='outer').fillna(0)
        
        merged['Usage %'] = 0.0
        mask_valid = merged['Monthly_Limit'] > 0
        merged.loc[mask_valid, 'Usage %'] = (merged.loc[mask_valid, 'Amount'] / merged.loc[mask_valid, 'Monthly_Limit']) * 100
        
        mask_zero = (merged['Monthly_Limit'] == 0) & (merged['Amount'] > 0)
        merged.loc[mask_zero, 'Usage %'] = 100.0
        
        merged = merged.replace([np.inf, -np.inf], 0)
        merged = merged.sort_values(by='Amount', ascending=False)
        
        for i, row in merged.iterrows():
            cat = row['Category']
            spent = float(row['Amount'])
            limit = float(row['Monthly_Limit'])
            pct = row['Usage %']
            
            col_status = "✅" if pct < 80 else "⚠️" if pct < 100 else "🚨"
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f"**{cat}** {col_status}")
                try:
                    if pd.isna(pct): pct = 0
                    safe_pct = int(pct)
                    safe_pct = max(0, min(safe_pct, 100))
                    st.progress(safe_pct)
                except: st.progress(0)
                    
            with c2:
                st.write(f"₹{spent:,.0f} / ₹{limit:,.0f}")
    else:
        st.info("Add transactions and budget targets to see comparison.")

# --- TAB 3: TIME AUDIT (MANUAL LOG VISUALS) ---
with tab_time:
    if not sub_time.empty:
        total_hrs = sub_time['Hours'].sum()
        
        # CATEGORY MATCHING
        work_hrs = sub_time[sub_time['Category'].isin(['Deep Work', 'Meetings'])]['Hours'].sum()
        commute_hrs = sub_time[sub_time['Category'] == 'Commute']['Hours'].sum()
        health_hrs = sub_time[sub_time['Category'] == 'Health/Gym']['Hours'].sum()
        learn_hrs = sub_time[sub_time['Category'] == 'Learning']['Hours'].sum()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Logged", f"{total_hrs:.1f}h")
        m2.metric("Work & Meet", f"{work_hrs:.1f}h")
        m3.metric("Commute", f"{commute_hrs:.1f}h")
        m4.metric("Learning", f"{learn_hrs:.1f}h")
        
        st.divider()
        
        c_vis, c_stack = st.columns(2)
        with c_vis:
            st.plotly_chart(px.pie(sub_time, values='Hours', names='Category', hole=0.4, title="Time Distribution"), use_container_width=True)
            
        with c_stack:
            daily_stack = sub_time.groupby(['Date', 'Category'])['Hours'].sum().reset_index()
            st.plotly_chart(px.bar(daily_stack, x='Date', y='Hours', color='Category', title="Daily Rhythm"), use_container_width=True)
            
        # HOURLY RATE CALCULATOR
        st.divider()
        st.subheader("🧠 Real Hourly Rate")
        c_calc, _ = st.columns([1, 2])
        with c_calc:
            salary = st.number_input("Monthly Income", value=100000, step=5000)
            real_effort = work_hrs + commute_hrs # Total time 'spent' on job
            
            if real_effort > 0:
                # Extrapolate to month if we are only part way through
                days_logged = sub_time['Date'].nunique()
                if days_logged > 0:
                    projected_hours = (real_effort / days_logged) * 22 # Approx 22 work days
                    rate = salary / projected_hours if projected_hours > 0 else 0
                    st.metric("Effective Hourly Rate", f"₹{rate:,.0f} / hr", help="Income / (Work + Commute Hours)")
    else:
        st.info("Start logging time using the sidebar form '⏱️ Log Time'!")

# --- TAB 4: RAW DATA ---
with tab_raw:
    st.subheader("Transactions")
    st.dataframe(sub_tx, use_container_width=True)
    st.divider()
    st.subheader("Time Logs")
    st.dataframe(sub_time, use_container_width=True)