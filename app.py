import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="Life OS", page_icon="🧬", layout="wide")

# --- AUTHENTICATION ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- DATA LOADING ---
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sh = client.open("Master_Finance_DB")
    
    # 1. LOAD FINANCE
    try:
        ws_tx = sh.sheet1
        raw_tx = ws_tx.get_all_values()
        df_tx = pd.DataFrame(raw_tx[1:], columns=raw_tx[0]) if len(raw_tx) > 1 else pd.DataFrame()
        if not df_tx.empty:
            df_tx['Amount'] = pd.to_numeric(df_tx['Amount'].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0)
            df_tx['Date'] = pd.to_datetime(df_tx['Date'].astype(str).apply(lambda x: x.split(' ')[0]), errors='coerce')
            df_tx['Month_Sort'] = df_tx['Date'].dt.strftime('%Y-%m')
    except:
        df_tx = pd.DataFrame()

    # 2. LOAD BUDGETS
    try:
        ws_budget = sh.worksheet("Budgets")
        raw_b = ws_budget.get_all_values()
        df_budget = pd.DataFrame(raw_b[1:], columns=raw_b[0]) if len(raw_b) > 1 else pd.DataFrame()
        if not df_budget.empty:
            df_budget['Monthly_Limit'] = pd.to_numeric(df_budget['Monthly_Limit'].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0)
    except:
        df_budget = pd.DataFrame(columns=['Category', 'Monthly_Limit'])

    # 3. LOAD TIME LOGS
    try:
        ws_time = sh.worksheet("Time_Logs")
        raw_time = ws_time.get_all_values()
        df_time = pd.DataFrame(raw_time[1:], columns=raw_time[0]) if len(raw_time) > 1 else pd.DataFrame()
        
        if not df_time.empty:
            # CLEAN DURATION (Assuming Seconds)
            # If your sheet has Minutes, change 3600 to 60 below
            df_time['Duration_Mins'] = pd.to_numeric(df_time['Duration_Mins'], errors='coerce').fillna(0)
            df_time['Hours'] = df_time['Duration_Mins'] / 3600 
            
            # CLEAN DATES
            df_time['Date'] = pd.to_datetime(df_time['Date'].astype(str).apply(lambda x: x.split('T')[0]), errors='coerce')
            df_time['Month_Sort'] = df_time['Date'].dt.strftime('%Y-%m')
            
            # Clean Categories (strip whitespace)
            df_time['Category'] = df_time['Category'].astype(str).str.strip()
    except:
        df_time = pd.DataFrame()

    return df_tx, df_budget, df_time

# --- MAIN APP LAYOUT ---
st.title("🧬 Life Operating System")

try:
    df_tx, df_budget, df_time = load_data()
except Exception as e:
    st.error(f"Data Error: {e}")
    st.stop()

# --- GLOBAL FILTER ---
# Merge all available months from both datasets
all_months = set()
if not df_tx.empty: all_months.update(df_tx['Month_Sort'].dropna())
if not df_time.empty: all_months.update(df_time['Month_Sort'].dropna())
all_months = sorted(list(all_months), reverse=True)

selected_month = st.sidebar.selectbox("Select Month", all_months) if all_months else "No Data"

# Filter Dataframes
sub_tx = df_tx[df_tx['Month_Sort'] == selected_month].copy() if not df_tx.empty else pd.DataFrame()
sub_time = df_time[df_time['Month_Sort'] == selected_month].copy() if not df_time.empty else pd.DataFrame()

# --- TABS ---
tab_money, tab_time, tab_raw = st.tabs(["💰 Finance", "⏳ Time Audit", "📄 Raw Data"])

# ==========================
# TAB 1: FINANCE (Simplified)
# ==========================
with tab_money:
    if sub_tx.empty:
        st.info("No finance data for this month.")
    else:
        # Metrics
        spend = sub_tx['Amount'].sum()
        budget = df_budget['Monthly_Limit'].sum() if not df_budget.empty else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Spend", f"₹{spend:,.0f}")
        c2.metric("Budget", f"₹{budget:,.0f}")
        c3.metric("Remaining", f"₹{budget - spend:,.0f}", delta_color="normal")
        
        # Charts
        c_left, c_right = st.columns(2)
        with c_left:
            # Daily Trend
            daily = sub_tx.groupby('Date')['Amount'].sum().reset_index()
            st.plotly_chart(px.bar(daily, x='Date', y='Amount', title="Daily Spend"), use_container_width=True)
        with c_right:
            # Category Split
            cat_agg = sub_tx.groupby('Category')['Amount'].sum().reset_index()
            st.plotly_chart(px.pie(cat_agg, values='Amount', names='Category', title="Categories", hole=0.4), use_container_width=True)

# ==========================
# TAB 2: TIME AUDIT (The New Feature)
# ==========================
with tab_time:
    if sub_time.empty:
        st.warning("No time logs found for this month. Run your 'Sync Calendar' shortcut!")
    else:
        st.caption("Data Source: Apple Calendar (Synced via Shortcuts)")
        
        # 1. TIME METRICS
        total_hours = sub_time['Hours'].sum()
        
        # Intelligent Categorization (Adjust keywords to match your Calendar names)
        # Example: Looks for "Work" or "Job" or "Office"
        work_mask = sub_time['Category'].str.contains('Work|Office|Job', case=False, na=False)
        commute_mask = sub_time['Category'].str.contains('Commute|Travel', case=False, na=False)
        health_mask = sub_time['Category'].str.contains('Gym|Health|Workout', case=False, na=False)
        
        work_hrs = sub_time[work_mask]['Hours'].sum()
        commute_hrs = sub_time[commute_mask]['Hours'].sum()
        health_hrs = sub_time[health_mask]['Hours'].sum()
        
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Total Tracked", f"{total_hours:.1f} hrs")
        t2.metric("Deep Work", f"{work_hrs:.1f} hrs")
        t3.metric("Commute", f"{commute_hrs:.1f} hrs")
        t4.metric("Health", f"{health_hrs:.1f} hrs")
        
        st.divider()
        
        # 2. THE REAL HOURLY RATE
        # Interactive Inputs
        col_calc, col_chart = st.columns([1, 2])
        
        with col_calc:
            st.subheader("🧠 Real Hourly Rate")
            salary = st.number_input("Monthly Income (₹)", value=100000, step=5000)
            
            # Calculation: Income / (Work + Commute)
            real_effort_hours = work_hrs + commute_hrs
            
            if real_effort_hours > 0:
                # Extrapolate to month if data is partial? 
                # Better: Calculate "Rate based on tracked hours"
                # If we tracked 5 days, we assume the salary covers those 5 days roughly? 
                # Let's keep it simple: Rate = (Salary / 30 days * days_tracked) / hours_worked
                # SIMPLEST: Just show Rate = Salary / 160 (Standard) vs Rate = Salary / Actual
                
                # Let's assume standard 160 hours for comparison
                std_rate = salary / 160
                
                # Actual Rate (Monthly Salary / Total Life Hours spent on Work this month)
                # We project the monthly hours based on current pace
                days_passed = sub_time['Date'].nunique()
                projected_hours = (real_effort_hours / days_passed) * 22 if days_passed > 0 else 0
                
                if projected_hours > 0:
                    real_rate = salary / projected_hours
                    st.metric("Your Real Rate", f"₹{real_rate:,.0f} / hr", delta=f"{real_rate - std_rate:.0f} vs Standard")
                    
                    if real_rate < (std_rate * 0.8):
                        st.error("📉 You are overworking/commuting. Your rate is diluted.")
                    else:
                        st.success("📈 You are protecting your time well.")
            else:
                st.info("Log 'Work' or 'Commute' events to see your rate.")

        with col_chart:
            st.subheader("Where did the time go?")
            # Pie Chart
            fig_pie = px.pie(sub_time, values='Hours', names='Category', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        # 3. DAILY RHYTHM
        st.subheader("Daily Rhythm")
        # Stacked Bar Chart
        daily_stack = sub_time.groupby(['Date', 'Category'])['Hours'].sum().reset_index()
        fig_stack = px.bar(daily_stack, x='Date', y='Hours', color='Category', title="Daily Time Distribution")
        st.plotly_chart(fig_stack, use_container_width=True)

# ==========================
# TAB 3: RAW DATA
# ==========================
with tab_raw:
    c1, c2 = st.columns(2)
    with c1:
        st.write("Finance Logs")
        st.dataframe(sub_tx, use_container_width=True)
    with c2:
        st.write("Time Logs")
        st.dataframe(sub_time, use_container_width=True)