import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import calendar

# --- CONFIGURATION ---
st.set_page_config(page_title="Finance HQ", page_icon="💰", layout="wide")

# --- AUTHENTICATION ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- LOAD DATA ---
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
        df_tx['Amount'] = df_tx['Amount'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
        df_tx['Amount'] = pd.to_numeric(df_tx['Amount'], errors='coerce').fillna(0)
        df_tx['Date'] = df_tx['Date'].astype(str).apply(lambda x: x.split(' ')[0])
        df_tx['Date'] = pd.to_datetime(df_tx['Date'], errors='coerce')
        df_tx = df_tx.dropna(subset=['Date'])
        df_tx['Month_Sort'] = df_tx['Date'].dt.strftime('%Y-%m')

    # 2. FETCH BUDGETS
    df_budget = pd.DataFrame(columns=['Category', 'Monthly_Limit'])
    try:
        ws_budget = sh.worksheet("Budgets")
        raw_budget = ws_budget.get_all_values()
        if len(raw_budget) > 1:
            df_budget = pd.DataFrame(raw_budget[1:], columns=raw_budget[0])
            df_budget['Monthly_Limit'] = pd.to_numeric(df_budget['Monthly_Limit'].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0)
    except:
        pass 

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

# --- FILTER ---
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
c3.metric("Remaining", f"₹{total_budget - total_spend:,.0f}", delta_color="normal")

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📊 Analytics", "🎯 Categories", "📄 Data"])

with tab1:
    c_left, c_right = st.columns([2,1])
    
    with c_left:
        # --- BURNDOWN CHART LOGIC ---
        if total_budget > 0:
            # 1. Create a full date range for the month
            year, month = map(int, selected_month_sort.split('-'))
            last_day = calendar.monthrange(year, month)[1]
            all_dates = pd.date_range(start=f"{selected_month_sort}-01", end=f"{selected_month_sort}-{last_day}")
            
            # 2. Daily Spends (Fill missing days with 0)
            daily_spends = df_month.groupby('Date')['Amount'].sum().reindex(all_dates, fill_value=0).reset_index()
            daily_spends.columns = ['Date', 'Daily_Spend']
            
            # 3. Cumulative Calculation
            daily_spends['Cumulative_Spend'] = daily_spends['Daily_Spend'].cumsum()
            daily_spends['Remaining_Budget'] = total_budget - daily_spends['Cumulative_Spend']
            
            # 4. Ideal Line (Straight line from Total to 0)
            daily_spends['Ideal_Burn'] = [total_budget - (total_budget / last_day * (i + 1)) for i in range(len(daily_spends))]
            
            # 5. Plot
            fig_burn = go.Figure()
            # Actual Line
            fig_burn.add_trace(go.Scatter(x=daily_spends['Date'], y=daily_spends['Remaining_Budget'], mode='lines+markers', name='Actual Balance', line=dict(color='#00CC96', width=3)))
            # Ideal Line
            fig_burn.add_trace(go.Scatter(x=daily_spends['Date'], y=daily_spends['Ideal_Burn'], mode='lines', name='Ideal Pace', line=dict(color='gray', dash='dash')))
            
            fig_burn.update_layout(title="📉 Cash Burndown (Runway)", xaxis_title="Date", yaxis_title="Remaining Budget", hovermode="x unified")
            st.plotly_chart(fig_burn, use_container_width=True)
            
            # Advice logic
            today_idx = (datetime.now() - datetime(year, month, 1)).days
            if 0 <= today_idx < len(daily_spends):
                actual_now = daily_spends.iloc[today_idx]['Remaining_Budget']
                ideal_now = daily_spends.iloc[today_idx]['Ideal_Burn']
                if actual_now > ideal_now:
                    st.success(f"🎉 You are ahead of schedule! You have ₹{actual_now - ideal_now:,.0f} extra buffer.")
                else:
                    st.error(f"⚠️ You are overspending. You are behind by ₹{ideal_now - actual_now:,.0f}.")
        else:
            st.info("Set a budget in the 'Budgets' tab to see the Burndown Chart.")

        # --- DAILY BAR CHART ---
        daily_bar = df_month.groupby('Date')['Amount'].sum().reset_index()
        st.plotly_chart(px.bar(daily_bar, x='Date', y='Amount', title="Daily Spending Spikes", text_auto='.2s'), use_container_width=True)

    with c_right:
        cat_agg = df_month.groupby('Category')['Amount'].sum().reset_index()
        st.plotly_chart(px.pie(cat_agg, values='Amount', names='Category', title="Spend Split", hole=0.4), use_container_width=True)

with tab2:
    # Existing Budget Bars
    actuals = df_month.groupby('Category')['Amount'].sum().reset_index()
    merged = pd.merge(df_budget, actuals, on='Category', how='outer').fillna(0)
    merged['Usage %'] = (merged['Amount'] / merged['Monthly_Limit']) * 100
    merged = merged.sort_values(by='Amount', ascending=False)

    for index, row in merged.iterrows():
        cat = row['Category']
        spent = row['Amount']
        limit = row['Monthly_Limit']
        pct = row['Usage %']
        
        color_status = "✅" if pct <= 80 else "⚠️" if pct <= 100 else "🚨"
        c1, c2 = st.columns([3, 1])
        with c1:
            st.write(f"**{cat}** {color_status}")
            st.progress(min(int(pct), 100))
        with c2:
            st.write(f"₹{spent:,.0f} / ₹{limit:,.0f}")

with tab3:
    st.dataframe(df_month)