import streamlit as st
import pandas as pd
import json
import datetime
import yfinance as yf
import gspread

st.set_page_config(page_title="Wise Finvestors", layout="wide")

# --- GOOGLE SHEETS CONNECTOR ---
@st.cache_resource
def get_gspread_client():
    # Streamlit's official gspread authentication
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
    st.error(f"⚠️ Connection Detail Error: {e}")

# --- FETCH USERS FROM GOOGLE SHEET ---
USERS = {}
if connected and sheet_users:
    try:
        user_records = sheet_users.get_all_records()
        for row in user_records:
            mob = str(row["Mobile"]).strip()
            USERS[mob] = {
                "name": str(row["Name"]).strip(),
                "pin": str(row["PIN"]).strip(),
                "default_rate": float(row.get("Interest_Rate", 10.0))
            }
    except Exception as e:
        pass

if not USERS:
    USERS = {"9999911111": {"name": "Admin", "pin": "1234", "default_rate": 10.0}}

# --- LOGIN SYSTEM ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = None

if not st.session_state.logged_in:
    st.title("🔐 Login - Wise Finvestors")
    
    if connected:
        st.success("🟢 Connected to Google Sheet Database")
    else:
        st.warning("⚠️ Sheet Connection Pending. Using Fallback Login.")
        
    mobile = st.text_input("Mobile Number").strip()
    pin = st.text_input("PIN / Password", type="password").strip()
    
    if st.button("Login"):
        if mobile in USERS and USERS[mobile]["pin"] == pin:
            st.session_state.logged_in = True
            st.session_state.current_user = USERS[mobile]["name"]
            st.session_state.user_rate = USERS[mobile]["default_rate"]
            st.rerun()
        else:
            st.error("Invalid Mobile Number or PIN!")
    st.stop()

# --- LOGGED IN DASHBOARD ---
st.sidebar.success(f"Logged in: **{st.session_state.current_user}**")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

st.title("📈 Wise Finvestors")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Real Investments", 
    "🧪 Paper Trading Sandbox", 
    "📥 JSON Backup", 
    "🤝 Dynamic Settlement"
])

# --- TAB 1: REAL INVESTMENTS ---
with tab1:
    st.subheader("Add Real Investment Entry")
    col1, col2 = st.columns(2)
    with col1:
        asset_type = st.selectbox("Asset Class", ["Shares / Stock", "IPO Bid", "Real Estate", "Expense"])
        amount = st.number_input("Investment Amount (₹)", min_value=0.0)
        interest_rate = st.number_input("Specific Loan Interest Rate (% p.a.)", min_value=0.0, value=st.session_state.user_rate, step=0.1)
        note = st.text_input("Stock Ticker / Investment Details (e.g., TATAMOTORS.NS)")
        inv_date = st.date_input("Investment Date", datetime.date.today())
        
        if st.button("Save Real Entry"):
            user = st.session_state.current_user
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = [timestamp, str(inv_date), user, asset_type, amount, interest_rate, note]
            
            if connected and sheet_trans:
                sheet_trans.append_row(new_row)
                st.success(f"Saved to Google Sheet & tagged to **{user}** @ {interest_rate}% Interest!")
            else:
                st.warning("Sheet Not Connected. Entry saved in session only.")

# --- TAB 2: PAPER TRADING ---
with tab2:
    st.subheader("🧪 Paper Trading Sandbox (Isolated)")
    st.info("💡 Yeh virtual trading ledger hai. Iska real settlement ya interest calculation se koi lene-dena nahi hai.")
    
    col1, col2 = st.columns(2)
    with col1:
        p_ticker = st.text_input("Virtual Ticker (e.g. RELIANCE.NS)")
        p_buy = st.number_input("Virtual Buy Price (₹)", min_value=0.0)
        p_qty = st.number_input("Quantity", min_value=1)
        
        if st.button("Save Paper Trade"):
            user = st.session_state.current_user
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            p_row = [timestamp, user, p_ticker, p_buy, p_qty, "OPEN"]
            
            if connected and sheet_paper:
                sheet_paper.append_row(p_row)
                st.success(f"Virtual Paper Trade recorded for **{user}**!")

# --- TAB 3: JSON EXPORT ---
with tab3:
    st.subheader("📦 Database JSON Export")
    if connected and sheet_trans:
        try:
            records = sheet_trans.get_all_records()
            json_data = json.dumps(records, indent=4)
            st.download_button("⬇️ Download Real Trades JSON", json_data, f"real_trades_{datetime.date.today()}.json", "application/json")
        except Exception as e:
            st.error(f"Error fetching data: {e}")

# --- TAB 4: SETTLEMENT ---
with tab4:
    st.subheader("🤝 Interest & Dynamic Settlement Ledger")
    st.write("Calculates exact per-day interest based on individual rates attached to each transaction.")
