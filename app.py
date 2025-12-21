import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta # <--- ADD THIS
# --- CONFIGURATION ---
st.set_page_config(page_title="Finance HQ", page_icon="💰", layout="wide")

# --- AUTHENTICATION HELPER ---
def get_gspread_client():
    """Connects to Google Sheets using Streamlit Secrets."""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- READ DATA (Cached) ---
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    sheet = client.open("Master_Finance_DB").sheet1 
    # Use get_all_values instead of records to handle messy headers better, 
    # but records is fine if headers are solid. Let's stick to records.
    data = sheet.get_all_records()
    
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    
    # 1. Clean Amount
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
    
    # 2. Clean Date (THE NUCLEAR FIX)
    # Step A: Ensure it is a string
    df['Date'] = df['Date'].astype(str)
    
    # Step B: Split by space and take the first chunk (The Date)
    # This strips the time off the iPhone entries
    df['Date'] = df['Date'].apply(lambda x: x.split(' ')[0])
    
    # Step C: Convert to datetime (Now everything looks identical: YYYY-MM-DD)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    
    # 3. Helpers
    df['Month_Sort'] = df['Date'].dt.strftime('%Y-%m')
    df['Month_Label'] = df['Date'].dt.strftime('%b %Y')
    
    return df

# --- SIDEBAR: ADD TRANSACTION FORM ---
with st.sidebar.form(key='add_txn_form'):
    st.header("➕ Add Transaction")
    
    # Removed Date Input (System will handle it)
    
    # Input Widgets
    input_amount = st.number_input("Amount", min_value=0.0, step=10.0)
    input_category = st.selectbox("Category", ["Food", "Transport", "Bills", "Shopping", "Entertainment", "Health", "Investments"])
    input_desc = st.text_input("Description")
    input_mode = st.selectbox("Payment Mode", ["UPI", "Credit Card", "Cash"])
    
    submit_button = st.form_submit_button(label='Save Expense')

    if submit_button:
        try:
            # 1. Connect (No cache for writing)
            client = get_gspread_client()
            sheet = client.open("Master_Finance_DB").sheet1
            
            # 2. Get Current Time in IST (Hyderabad)
            # Streamlit Cloud is UTC, so we add 5 hours 30 mins
            utc_now = datetime.utcnow()
            ist_now = utc_now + timedelta(hours=5, minutes=30)
            
            # Format exactly like iPhone: "YYYY-MM-DD HH:MM:SS"
            date_str = ist_now.strftime("%Y-%m-%d %H:%M:%S")
            
            # 3. Append Row (Order: Date, Amount, Category, Desc, Mode)
            sheet.append_row([date_str, input_amount, input_category, input_desc, input_mode])
            
            st.success(f"✅ Saved! Date logged: {date_str}")
            
            # 4. Clear Cache & Reload
            st.cache_data.clear()
            st.rerun()
            
        except Exception as e:
            st.error(f"Error saving: {e}")

# --- MAIN DASHBOARD ---
st.title("💰 Personal Finance Control Center")

try:
    df = load_data()
except Exception as e:
    st.error(f"🚨 Connection Error: {e}")
    st.stop()

if df.empty:
    st.warning("Connected successfully, but the Google Sheet is empty or headers are missing.")
    st.stop()

# 1. Filters (Sidebar)
st.sidebar.divider()
st.sidebar.header("🔍 Filters")
all_months = sorted(df['Month_Sort'].unique(), reverse=True)
# Create a mapping for the dropdown (Show "Dec 2025", but filter by "2025-12")
month_map = {m: pd.to_datetime(m).strftime('%b %Y') for m in all_months}
selected_month_sort = st.sidebar.selectbox("Select Month", all_months, format_func=lambda x: month_map[x])

# Apply Filter
df_month = df[df['Month_Sort'] == selected_month_sort].copy()

# 2. KPI Cards
col1, col2, col3, col4 = st.columns(4)
total_spend = df_month['Amount'].sum()
tx_count = len(df_month)
avg_spend = total_spend / tx_count if tx_count > 0 else 0
top_cat = df_month.groupby('Category')['Amount'].sum().idxmax() if not df_month.empty else "N/A"

col1.metric("Total Spent", f"₹{total_spend:,.0f}")
col2.metric("Transactions", tx_count)
col3.metric("Avg. Ticket", f"₹{avg_spend:,.0f}")
col4.metric("Top Category", top_cat)

# 3. Visualizations
tab1, tab2 = st.tabs(["📊 Analytics", "📄 Raw Data"])

with tab1:
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("Daily Spending Trend")
        # Aggregate by day
        daily = df_month.groupby('Date')['Amount'].sum().reset_index()
        fig_bar = px.bar(daily, x='Date', y='Amount', text_auto='.2s')
        st.plotly_chart(fig_bar, use_container_width=True)
        
    with c2:
        st.subheader("Category Split")
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