import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. Page Setup
st.set_page_config(page_title="Finance HQ", layout="wide")
st.title("💰 Finance Control Center")

# 2. Secure Data Connection
# We use st.cache_data to prevent spamming Google's API on every click
@st.cache_data(ttl=600) # Clears cache every 10 mins
def load_data():
    # Access the secrets (we will set this up in Cloud next)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Create credentials from the Streamlit Secrets dictionary
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # Connect
    client = gspread.authorize(creds)
    
    # Open Sheet (Make sure the name matches EXACTLY)
    sheet = client.open("Master_Finance_DB").sheet1
    data = sheet.get_all_records()
    
    df = pd.DataFrame(data)
    
    # Clean Data
    if not df.empty:
        df['Amount'] = pd.to_numeric(df['Amount'])
        df['Date'] = pd.to_datetime(df['Date'])
        df['Month'] = df['Date'].dt.strftime('%Y-%m')
        
    return df

try:
    df = load_data()
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# 3. The Dashboard
if df.empty:
    st.warning("No data found in the sheet.")
else:
    # Sidebar Filters
    months = sorted(df['Month'].unique(), reverse=True)
    selected_month = st.sidebar.selectbox("Select Month", months)
    
    mask = df['Month'] == selected_month
    filtered_df = df[mask]
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    spend = filtered_df['Amount'].sum()
    
    col1.metric("Total Spend", f"₹{spend:,.0f}")
    col2.metric("Tx Count", len(filtered_df))
    
    # Visuals
    tab1, tab2 = st.tabs(["Charts", "Data"])
    
    with tab1:
        st.subheader("Spending by Category")
        fig = px.pie(filtered_df, values='Amount', names='Category', hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
        
    with tab2:
        st.dataframe(filtered_df)