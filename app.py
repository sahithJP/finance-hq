import streamlit as st
import pandas as pd
import plotly.express as px
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

# --- LOAD DATA (Unbreakable Version) ---
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sheet = client.open("Master_Finance_DB").sheet1
    
    # METHOD CHANGE: Use get_all_values() instead of get_all_records()
    # This treats everything as raw text first, preventing type confusion
    raw_data = sheet.get_all_values()
    
    # If only headers or empty
    if len(raw_data) < 2:
        return pd.DataFrame()

    # Manually build DataFrame
    headers = raw_data[0]
    rows = raw_data[1:]
    df = pd.DataFrame(rows, columns=headers)

    # 1. Clean Amount (Remove currency symbols, commas, spaces)
    # This regex handles "₹ 1,200.00" or "1200" or "1,200"
    df['Amount'] = df['Amount'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
    
    # 2. Clean Date (The Logic that cannot fail)
    # We force string, split by space (to remove time), then parse
    df['Date'] = df['Date'].astype(str).apply(lambda x: x.split(' ')[0])
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    
    # Drop rows where Date is invalid (NaT) to prevent crashes later
    df = df.dropna(subset=['Date'])

    # 3. Helpers
    df['Month_Sort'] = df['Date'].dt.strftime('%Y-%m')
    df['Month_Label'] = df['Date'].dt.strftime('%b %Y')
    
    return df

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh Data & Clear Cache"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()

    # --- ADD TRANSACTION FORM ---
    with st.form(key='add_txn_form'):
        st.header("➕ Add Transaction")
        
        input_amount = st.number_input("Amount", min_value=0.0, step=10.0)
        input_category = st.selectbox("Category", ["Food", "Transport", "Bills", "Shopping", "Entertainment", "Health", "Investments"])
        input_desc = st.text_input("Description")
        input_mode = st.selectbox("Payment Mode", ["UPI", "Credit Card", "Cash"])
        
        submit_button = st.form_submit_button(label='Save Expense')

        if submit_button:
            try:
                client = get_gspread_client()
                sheet = client.open("Master_Finance_DB").sheet1
                
                # Get IST Time
                utc_now = datetime.utcnow()
                ist_now = utc_now + timedelta(hours=5, minutes=30)
                date_str = ist_now.strftime("%Y-%m-%d %H:%M:%S")
                
                sheet.append_row([date_str, input_amount, input_category, input_desc, input_mode])
                
                st.success(f"✅ Saved! {date_str}")
                st.cache_data.clear() # Force reload
                st.rerun()
                
            except Exception as e:
                st.error(f"Error saving: {e}")

# --- MAIN DASHBOARD ---
st.title("💰 Personal Finance Control Center")

try:
    df = load_data()
except Exception as e:
    st.error(f"🚨 Data Error: {e}")
    st.stop()

if df.empty:
    st.warning("⚠️ Connected to Sheet, but no data rows found.")
    st.stop()

# 1. Filters
all_months = sorted(df['Month_Sort'].unique(), reverse=True)
# Safe mapping: Handle cases where map key might miss
month_map = {m: pd.to_datetime(m + "-01").strftime('%b %Y') for m in all_months}

selected_month_sort = st.sidebar.selectbox(
    "Select Month", 
    all_months, 
    format_func=lambda x: month_map.get(x, x)
)

df_month = df[df['Month_Sort'] == selected_month_sort].copy()

# 2. KPIs
col1, col2, col3, col4 = st.columns(4)
total_spend = df_month['Amount'].sum()
tx_count = len(df_month)
avg_spend = total_spend / tx_count if tx_count > 0 else 0
top_cat = df_month.groupby('Category')['Amount'].sum().idxmax() if not df_month.empty else "N/A"

col1.metric("Total Spent", f"₹{total_spend:,.0f}")
col2.metric("Transactions", tx_count)
col3.metric("Avg. Ticket", f"₹{avg_spend:,.0f}")
col4.metric("Top Category", top_cat)

# 3. Visuals
tab1, tab2 = st.tabs(["📊 Analytics", "📄 Raw Data"])

with tab1:
    c1, c2 = st.columns([2, 1])
    with c1:
        daily = df_month.groupby('Date')['Amount'].sum().reset_index()
        fig_bar = px.bar(daily, x='Date', y='Amount', text_auto='.2s')
        st.plotly_chart(fig_bar, use_container_width=True)
    with c2:
        cat_agg = df_month.groupby('Category')['Amount'].sum().reset_index()
        fig_pie = px.pie(cat_agg, values='Amount', names='Category', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

with tab2:
    st.dataframe(
        df_month.sort_values(by='Date', ascending=False),
        column_config={
            "Date": st.column_config.DateColumn("Date", format="DD MMM YYYY"),
            "Amount": st.column_config.NumberColumn("Amount", format="₹ %.2f"),
        },
        use_container_width=True,
        hide_index=True
    )