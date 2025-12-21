import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="Finance HQ", page_icon="💰", layout="wide")

# --- AUTHENTICATION ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- LOAD DATA (Multi-Sheet Logic) ---
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sh = client.open("Master_Finance_DB")
    
    # 1. FETCH TRANSACTIONS
    ws_tx = sh.sheet1
    raw_tx = ws_tx.get_all_values()
    
    df_tx = pd.DataFrame()
    if len(raw_tx) > 1:
        df_tx = pd.DataFrame(raw_tx[1:], columns=raw_tx[0])
        # Clean Amount
        df_tx['Amount'] = df_tx['Amount'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
        df_tx['Amount'] = pd.to_numeric(df_tx['Amount'], errors='coerce').fillna(0)
        # Clean Date
        df_tx['Date'] = df_tx['Date'].astype(str).apply(lambda x: x.split(' ')[0])
        df_tx['Date'] = pd.to_datetime(df_tx['Date'], errors='coerce')
        df_tx = df_tx.dropna(subset=['Date'])
        # Helpers
        df_tx['Month_Sort'] = df_tx['Date'].dt.strftime('%Y-%m')

    # 2. FETCH BUDGETS
    # We use try/except in case the tab doesn't exist yet
    df_budget = pd.DataFrame(columns=['Category', 'Monthly_Limit'])
    try:
        ws_budget = sh.worksheet("Budgets")
        raw_budget = ws_budget.get_all_values()
        if len(raw_budget) > 1:
            df_budget = pd.DataFrame(raw_budget[1:], columns=raw_budget[0])
            df_budget['Monthly_Limit'] = pd.to_numeric(df_budget['Monthly_Limit'].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0)
    except:
        pass # If no budget tab, we just continue with empty budget

    return df_tx, df_budget

# --- SIDEBAR & FORM ---
with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    
    with st.form(key='add_txn_form'):
        st.header("➕ Add Transaction")
        input_amount = st.number_input("Amount", min_value=0.0, step=10.0)
        input_category = st.selectbox("Category", ["Food", "Transport", "Bills", "Shopping", "Entertainment", "Health", "Investments"])
        input_desc = st.text_input("Description")
        input_mode = st.selectbox("Payment Mode", ["UPI", "Credit Card", "Cash"])
        
        if st.form_submit_button('Save'):
            try:
                client = get_gspread_client()
                sheet = client.open("Master_Finance_DB").sheet1
                utc_now = datetime.utcnow()
                ist_now = utc_now + timedelta(hours=5, minutes=30)
                date_str = ist_now.strftime("%Y-%m-%d %H:%M:%S")
                sheet.append_row([date_str, input_amount, input_category, input_desc, input_mode])
                st.success(f"Saved!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# --- MAIN APP ---
st.title("💰 Finance Control Center")

try:
    df, df_budget = load_data()
except Exception as e:
    st.error(f"Data Error: {e}")
    st.stop()

if df.empty:
    st.warning("No transactions found.")
    st.stop()

# --- FILTER CONTEXT ---
# Standard Month Selector
all_months = sorted(df['Month_Sort'].unique(), reverse=True)
month_map = {m: pd.to_datetime(m + "-01").strftime('%b %Y') for m in all_months}
selected_month_sort = st.sidebar.selectbox("Select Month", all_months, format_func=lambda x: month_map.get(x, x))
df_month = df[df['Month_Sort'] == selected_month_sort].copy()

# --- KPIS ---
c1, c2, c3 = st.columns(3)
total_spend = df_month['Amount'].sum()
total_budget = df_budget['Monthly_Limit'].sum()
c1.metric("Total Spent", f"₹{total_spend:,.0f}")
c2.metric("Total Budget", f"₹{total_budget:,.0f}")
# Delta color is inverted: Red is bad (Positive delta), Green is good (Negative delta)
c3.metric("Variance", f"₹{total_spend - total_budget:,.0f}", delta_color="inverse")

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📊 Overview", "🎯 Budget vs Actual", "📄 Data"])

with tab1:
    # Existing Charts
    c_left, c_right = st.columns([2,1])
    with c_left:
        daily = df_month.groupby('Date')['Amount'].sum().reset_index()
        st.plotly_chart(px.bar(daily, x='Date', y='Amount', title="Daily Trend"), use_container_width=True)
    with c_right:
        cat_agg = df_month.groupby('Category')['Amount'].sum().reset_index()
        st.plotly_chart(px.pie(cat_agg, values='Amount', names='Category', title="Split"), use_container_width=True)

with tab2:
    st.subheader("Monthly Performance")
    
    # PREPARE BUDGET DATA
    # Group actuals by category
    actuals = df_month.groupby('Category')['Amount'].sum().reset_index()
    
    # Merge with Budget Targets (Outer join to see missed budgets or unbudgeted spend)
    merged = pd.merge(df_budget, actuals, on='Category', how='outer').fillna(0)
    merged['Usage %'] = (merged['Amount'] / merged['Monthly_Limit']) * 100
    
    # Sort by highest spend
    merged = merged.sort_values(by='Amount', ascending=False)

    # VISUALIZATION: Progress Bars
    for index, row in merged.iterrows():
        cat = row['Category']
        spent = row['Amount']
        limit = row['Monthly_Limit']
        pct = row['Usage %']
        
        # Determine Color
        if limit == 0:
            color_status = "⚠️ Unbudgeted"
            bar_color = "red" # Just for logic
        elif pct > 100:
            color_status = "🚨 Over Budget"
            bar_color = "red"
        elif pct > 80:
            color_status = "⚠️ Warning"
            bar_color = "orange"
        else:
            color_status = "✅ On Track"
            bar_color = "green"
            
        # Display using Columns
        c1, c2 = st.columns([3, 1])
        with c1:
            st.write(f"**{cat}** ({color_status})")
            # Cap progress bar at 100 to avoid error
            st.progress(min(int(pct), 100))
        with c2:
            st.write(f"₹{spent:,.0f} / ₹{limit:,.0f}")
            
    st.divider()
    st.caption("Categories with no budget set are marked as Unbudgeted.")

with tab3:
    st.dataframe(df_month)