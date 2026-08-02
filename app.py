import streamlit as st
import pandas as pd
import json
import datetime
import yfinance as yf
import gspread

st.set_page_config(page_title="Wise Finvestors", layout="wide", initial_sidebar_state="expanded")

# --- GOOGLE SHEETS CONNECTOR ---
@st.cache_resource
def get_gspread_client():
    return gspread.service_account_from_dict(st.secrets["gcp_service_account"])

connected = False
sheet_trans = None
sheet_users = None
sheet_paper = None

try:
    client = get_gspread_client()
    sheet_trans = client.open("Investment_Database").worksheet("Transactions")
    sheet_users = client.open("Investment_Database").worksheet("Users_List")
    sheet_paper = client.open("Investment_Database").worksheet("Paper_Trades")
    connected = True
except Exception as e:
    connected = False

# --- FETCH USERS FROM GOOGLE SHEET ---
USERS = {}
if connected and sheet_users:
    try:
        user_records = sheet_users.get_all_records()
        for row in user_records:
            mob = str(row.get("Mobile", "")).strip().replace(".0", "")
            pin = str(row.get("PIN", "")).strip().replace(".0", "")
            name = str(row.get("Name", "")).strip()
            rate = row.get("Interest_Rate", 10.0)
            if mob:
                USERS[mob] = {
                    "name": name,
                    "pin": pin,
                    "default_rate": float(rate) if rate else 10.0
                }
    except Exception as e:
        pass

if not USERS:
    USERS = {"9999911111": {"name": "Admin", "pin": "admin123", "default_rate": 10.0}}

# --- LOGIN SYSTEM ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = None

if not st.session_state.logged_in:
    st.title("🔐 Wise Finvestors - Login")
    
    if connected:
        st.success("🟢 Database Online & Connected")
    else:
        st.warning("⚠️ Running in Standalone / Offline Mode")
        
    mobile = st.text_input("Mobile Number").strip()
    pin = st.text_input("PIN / Password", type="password").strip()
    
    if st.button("Login", type="primary"):
        if mobile in USERS and USERS[mobile]["pin"] == pin:
            st.session_state.logged_in = True
            st.session_state.current_user = USERS[mobile]["name"]
            st.session_state.user_rate = USERS[mobile]["default_rate"]
            st.rerun()
        else:
            st.error("Invalid Mobile Number or PIN!")
    st.stop()

# --- LOGGED IN DASHBOARD ---
st.sidebar.markdown(f"👤 Logged in as: **{st.session_state.current_user}**")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

st.title("📈 Wise Finvestors - Investment & Settlement Dashboard")

# MAIN TABS
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Portfolio & Live Market", 
    "➕ Add Entry / IPO Bid", 
    "🤝 Interest & Settlement", 
    "🧪 Paper Trading", 
    "📦 Raw Data & JSON"
])

# --- HELPER FUNCTIONS ---
def load_transactions():
    if connected and sheet_trans:
        try:
            records = sheet_trans.get_all_records()
            if records:
                df = pd.DataFrame(records)
                df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
                df['Interest_Rate'] = pd.to_numeric(df['Interest_Rate'], errors='coerce').fillna(10.0)
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=["Timestamp", "Date", "User", "Asset_Class", "Amount", "Interest_Rate", "Note"])

def fetch_live_price(ticker):
    try:
        if not ticker or "." not in ticker:
            ticker = ticker + ".NS" if ticker else ""
        stock = yf.Ticker(ticker)
        fast_info = stock.fast_info
        return fast_info.last_price
    except Exception:
        return None

df_trans = load_transactions()

# --- TAB 1: PORTFOLIO & LIVE MARKET ---
with tab1:
    st.subheader("📊 Portfolio Overview")
    
    if df_trans.empty:
        st.info("No investments recorded yet. Add your first transaction in the next tab!")
    else:
        # Top Metrics
        total_inv = df_trans['Amount'].sum()
        user_inv = df_trans[df_trans['User'] == st.session_state.current_user]['Amount'].sum()
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total Group Capital", f"₹{total_inv:,.2f}")
        col_m2.metric(f"Your Investment ({st.session_state.current_user})", f"₹{user_inv:,.2f}")
        col_m3.metric("Total Recorded Entries", len(df_trans))
        
        st.markdown("---")
        
        # Breakdown by User & Asset Class
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Capital Contribution by Investor")
            user_summary = df_trans.groupby("User")["Amount"].sum().reset_index()
            st.dataframe(user_summary, use_container_width=True)
            
        with c2:
            st.markdown("##### Capital Allocation by Asset Class")
            asset_summary = df_trans.groupby("Asset_Class")["Amount"].sum().reset_index()
            st.dataframe(asset_summary, use_container_width=True)
            
        st.markdown("---")
        st.markdown("##### 📜 All Recorded Investments")
        st.dataframe(df_trans.sort_values(by="Date", ascending=False), use_container_width=True)

# --- TAB 2: ADD ENTRY / IPO BID ---
with tab2:
    st.subheader("➕ Record Investment / Apply IPO")
    
    with st.form("investment_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            asset_type = st.selectbox("Asset Class", ["Shares / Stock", "IPO Bid", "Real Estate", "Mutual Fund", "Expense"])
            amount = st.number_input("Investment Amount (₹)", min_value=0.0, step=1000.0)
            interest_rate = st.number_input("Interest Rate (% p.a.)", min_value=0.0, value=st.session_state.user_rate, step=0.5)
        
        with col2:
            note = st.text_input("Stock Ticker / Details (e.g. HFCL.NS, TATAMOTORS.NS, IPO Name)")
            inv_date = st.date_input("Investment Date", datetime.date.today())
            investor_name = st.selectbox("Investor", list(USERS.keys()), format_func=lambda x: USERS[x]["name"])
        
        submit = st.form_submit_button("🚀 Submit Entry to Sheet", type="primary")
        
        if submit:
            user_selected = USERS[investor_name]["name"]
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = [timestamp, str(inv_date), user_selected, asset_type, amount, interest_rate, note]
            
            if connected and sheet_trans:
                sheet_trans.append_row(new_row)
                st.success(f"✅ Successfully added entry for **{user_selected}** (₹{amount:,.2f})!")
                st.rerun()
            else:
                st.error("Sheet Connection Error. Unable to save.")

# --- TAB 3: INTEREST & SETTLEMENT ENGINE ---
with tab3:
    st.subheader("🤝 Interest & Dynamic Settlement Ledger")
    st.caption("Calculates exact per-day interest based on individual transaction dates and custom ROI.")
    
    if df_trans.empty:
        st.info("No entries to calculate settlement.")
    else:
        settlement_date = st.date_input("Settlement Calculation Date", datetime.date.today())
        
        settlement_data = []
        for idx, row in df_trans.iterrows():
            inv_d = row["Date"]
            amt = row["Amount"]
            rate = row["Interest_Rate"]
            user = row["User"]
            
            if pd.notnull(inv_d) and inv_d <= settlement_date:
                days_held = (settlement_date - inv_d).days
                # Simple per-day accrued interest: (P * R * T) / 365
                interest_accrued = (amt * rate * days_held) / (100 * 365)
                total_claim = amt + interest_accrued
            else:
                days_held = 0
                interest_accrued = 0.0
                total_claim = amt
                
            settlement_data.append({
                "Investor": user,
                "Asset": row["Asset_Class"],
                "Details": row["Note"],
                "Principal (₹)": amt,
                "ROI (% p.a.)": rate,
                "Holding Days": days_held,
                "Accrued Interest (₹)": round(interest_accrued, 2),
                "Total Settlement (₹)": round(total_claim, 2)
            })
            
        settle_df = pd.DataFrame(settlement_data)
        st.dataframe(settle_df, use_container_width=True)
        
        st.markdown("---")
        st.markdown("#### 💵 Net Investor Payout Summary")
        summary_payout = settle_df.groupby("Investor").agg({
            "Principal (₹)": "sum",
            "Accrued Interest (₹)": "sum",
            "Total Settlement (₹)": "sum"
        }).reset_index()
        st.dataframe(summary_payout, use_container_width=True)

# --- TAB 4: PAPER TRADING SANDBOX ---
with tab4:
    st.subheader("🧪 Isolated Paper Trading Sandbox")
    st.info("Virtual trading space for practice - completely separate from real settlement calculations.")
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        p_ticker = st.text_input("Paper Ticker (e.g. RELIANCE.NS)").upper()
        p_buy = st.number_input("Virtual Buy Price (₹)", min_value=0.0, step=10.0)
        p_qty = st.number_input("Quantity", min_value=1, step=1)
        
        if st.button("📌 Record Paper Trade"):
            user = st.session_state.current_user
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            p_row = [timestamp, user, p_ticker, p_buy, p_qty, "OPEN"]
            
            if connected and sheet_paper:
                sheet_paper.append_row(p_row)
                st.success(f"Recorded Virtual Trade: {p_qty} shares of {p_ticker}")
                st.rerun()
            else:
                st.error("Sheet Connection Error.")
                
    with col_p2:
        st.markdown("##### 📈 Virtual Positions")
        if connected and sheet_paper:
            try:
                p_records = sheet_paper.get_all_records()
                if p_records:
                    st.dataframe(pd.DataFrame(p_records), use_container_width=True)
                else:
                    st.write("No paper trades found.")
            except Exception:
                st.write("Unable to fetch paper trades.")

# --- TAB 5: RAW DATA & JSON BACKUP ---
with tab5:
    st.subheader("📦 Database JSON Backup & Raw Logs")
    if not df_trans.empty:
        json_str = df_trans.to_json(orient="records", date_format="iso", indent=4)
        st.download_button(
            label="📥 Download Database Backup (JSON)",
            data=json_str,
            file_name=f"wise_finvestors_backup_{datetime.date.today()}.json",
            mime="application/json",
            type="primary"
        )
        st.json(df_trans.to_dict(orient="records"))
