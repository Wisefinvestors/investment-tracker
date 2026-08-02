import streamlit as st
import pandas as pd
import json
import datetime
import requests
import yfinance as yf
import gspread

st.set_page_config(page_title="Wise Finvestors", layout="wide")

# --- GOOGLE SHEETS CONNECTOR ---
@st.cache_resource
def get_gspread_client():
    return gspread.service_account_from_dict(st.secrets["gcp_service_account"])

connected = False
sheet_trans = None
sheet_users = None
sheet_demat = None

try:
    client = get_gspread_client()
    db_sheet = client.open("Investment_Database")
    sheet_trans = db_sheet.worksheet("Transactions")
    sheet_users = db_sheet.worksheet("Users_List")
    try:
        sheet_demat = db_sheet.worksheet("Demat_Accounts")
    except Exception:
        sheet_demat = None
    connected = True
except Exception:
    connected = False

# --- FETCH USERS ---
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
    except Exception:
        pass

if not USERS:
    USERS = {"9254893645": {"name": "Ashish", "pin": "1234", "default_rate": 10.0}}

# --- LOGIN & SESSION STABILITY ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = None
if "user_rate" not in st.session_state:
    st.session_state["user_rate"] = 10.0

if not st.session_state["logged_in"]:
    st.title("🔐 Wise Finvestors - Login")
    mobile = st.text_input("Mobile Number", key="login_mob").strip()
    pin = st.text_input("PIN / Password", type="password", key="login_pin").strip()
    
    if st.button("Login", type="primary"):
        if mobile in USERS and USERS[mobile]["pin"] == pin:
            st.session_state["logged_in"] = True
            st.session_state["current_user"] = USERS[mobile]["name"]
            st.session_state["user_rate"] = USERS[mobile]["default_rate"]
            st.rerun()
        else:
            st.error("Invalid Mobile Number or PIN!")
    st.stop()

# --- SIDEBAR ---
st.sidebar.markdown(f"👤 Logged in: **{st.session_state['current_user']}**")
if st.sidebar.button("Logout"):
    st.session_state["logged_in"] = False
    st.session_state["current_user"] = None
    st.rerun()

st.title("📈 Wise Finvestors")

# --- FETCH DEMAT ACCOUNTS ---
def load_demat_accounts():
    if connected and sheet_demat:
        try:
            records = sheet_demat.get_all_records()
            if records:
                return pd.DataFrame(records)
        except Exception:
            pass
    return pd.DataFrame(columns=["User", "Holder_Name", "PAN", "BO_ID", "UPI_ID", "Broker_Name"])

df_demat = load_demat_accounts()

# --- LIVE IPO FETCHING ENGINE ---
@st.cache_data(ttl=3600)
def fetch_live_ipos():
    try:
        url = "https://api.ipoji.com/v1/ipos"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            ipo_dict = {}
            for item in data.get("ipos", []):
                name = item.get("name")
                ipo_dict[name] = {
                    "price": float(item.get("cutOffPrice", 100)),
                    "lot": int(item.get("lotSize", 14))
                }
            if ipo_dict:
                return ipo_dict
    except Exception:
        pass
    
    return {
        "NTPC Green Energy Limited": {"price": 108.0, "lot": 138},
        "Swiggy Limited": {"price": 390.0, "lot": 38},
        "Hyundai Motor India": {"price": 1960.0, "lot": 7},
        "Other / Manual IPO Entry": {"price": 100.0, "lot": 1}
    }

live_ipo_data = fetch_live_ipos()

# --- TABS ---
tab_demat, tab_add, tab_check, tab_port, tab_settle = st.tabs([
    "👥 Manage Demat Profiles",
    "➕ Apply IPO / Add Entry", 
    "🔍 IPO Allotment Hub",
    "📊 Portfolio & Live P&L", 
    "🤝 Dynamic Interest & Settlement"
])

# --- TAB 1: MANAGE DEMAT PROFILES ---
with tab_demat:
    st.subheader("👥 Multiple Demat Accounts Directory")
    st.caption("Add all Demat accounts (Self, Family, Friends) to quickly apply IPOs and check allotments.")
    
    col_d1, col_d2 = st.columns([1, 1.5])
    
    with col_d1:
        st.markdown("##### ➕ Add New Demat Account")
        with st.form("add_demat_form", clear_on_submit=True):
            holder_name = st.text_input("Account Holder Name (e.g. Ashish Kumar)")
            pan_no = st.text_input("PAN Card Number").upper().strip()
            bo_id = st.text_input("BO ID / Demat No (16 Digits)").strip()
            upi_id = st.text_input("Linked UPI ID (e.g. 9876543210@paytm)").strip()
            broker = st.selectbox("Broker Name", ["Zerodha", "Groww", "AngelOne", "Upstox", "ICICI Direct", "HDFC Securities", "Other"])
            
            submit_demat = st.form_submit_button("💾 Save Demat Profile", type="primary")
            
            if submit_demat:
                if not holder_name or not pan_no:
                    st.error("Holder Name and PAN are required!")
                elif connected and sheet_demat:
                    new_demat_row = [st.session_state["current_user"], holder_name, pan_no, bo_id, upi_id, broker]
                    sheet_demat.append_row(new_demat_row)
                    st.success(f"Added Demat Profile for {holder_name} ({broker})!")
                    st.rerun()
                else:
                    st.error("Sheet Connection Error or 'Demat_Accounts' tab missing!")
                    
    with col_d2:
        st.markdown("##### 📜 Registered Demat Profiles")
        if not df_demat.empty:
            st.dataframe(df_demat, use_container_width=True)
        else:
            st.info("No Demat accounts added yet. Use the form on the left to add your first Demat profile.")

# --- TAB 2: ADD ENTRY / IPO BID ---
with tab_add:
    st.subheader("Record Investment / Apply IPO Bid")
    asset_type = st.radio("Investment Mode:", ["IPO Bid", "Shares / Stock", "Real Estate", "Mutual Fund"], horizontal=True)
    st.markdown("---")
    
    with st.form("main_entry_form"):
        col1, col2 = st.columns(2)
        
        if asset_type == "IPO Bid":
            with col1:
                selected_ipo = st.selectbox("Select Active IPO", list(live_ipo_data.keys()))
                default_price = live_ipo_data[selected_ipo]["price"]
                default_lot = live_ipo_data[selected_ipo]["lot"]
                
                ipo_name = st.text_input("Custom Name") if selected_ipo == "Other / Manual IPO Entry" else selected_ipo
                lots = st.number_input("Lots Applied", min_value=1, value=1, step=1)
                shares_per_lot = st.number_input("Shares/Lot", min_value=1, value=default_lot, step=1)
                cut_off = st.number_input("Cut-off Price (₹)", min_value=0.0, value=default_price, step=1.0)
                
            with col2:
                # Select Demat Profile for this bid
                user_demats = df_demat[df_demat["User"] == st.session_state["current_user"]] if not df_demat.empty else pd.DataFrame()
                
                if not user_demats.empty:
                    demat_opts = [f"{row['Holder_Name']} - {row['Broker_Name']} ({row['PAN']})" for idx, row in user_demats.iterrows()]
                    selected_demat_idx = st.selectbox("Select Demat Account Used:", range(len(demat_opts)), format_func=lambda x: demat_opts[x])
                    chosen_demat = user_demats.iloc[selected_demat_idx]
                    demat_info_str = f"Holder: {chosen_demat['Holder_Name']} | PAN: {chosen_demat['PAN']} | BO_ID: {chosen_demat['BO_ID']} | UPI: {chosen_demat['UPI_ID']}"
                else:
                    st.warning("⚠️ No Demat accounts found! Go to 'Manage Demat Profiles' tab to add one.")
                    demat_info_str = "Default Demat Profile"
                
                total_qty = lots * shares_per_lot
                total_bid_amt = total_qty * cut_off
                st.info(f"📌 **Bid Amount:** ₹{total_bid_amt:,.2f} ({total_qty} Shares)\n\n💳 **Selected Demat Details:**\n{demat_info_str}")
                
                ipo_status = st.selectbox("ASBA Status", ["Funds Blocked / Applied", "Allotted", "Un-Allotted (Refunded)"])
                interest_rate = st.number_input("Interest Rate (% p.a.)", min_value=0.0, value=st.session_state["user_rate"], step=0.5)
                inv_date = st.date_input("Application Date", datetime.date.today())
                
            ticker_val = ipo_name
            qty_val = total_qty
            price_val = cut_off
            total_amt_val = total_bid_amt
            note_val = f"IPO ({lots} Lots) | {demat_info_str}"

        else:
            with col1:
                ticker_val = st.text_input("Stock Ticker (e.g., HFCL.NS, TATAMOTORS.NS)").upper().strip()
                qty_val = st.number_input("Quantity", min_value=1.0, value=10.0, step=1.0)
                price_val = st.number_input("Buy Price (₹)", min_value=0.0, value=100.0, step=1.0)
                
            with col2:
                total_amt_val = qty_val * price_val
                st.info(f"📌 Total Amount: **₹{total_amt_val:,.2f}**")
                ipo_status = "N/A"
                interest_rate = st.number_input("Interest Rate (% p.a.)", min_value=0.0, value=st.session_state["user_rate"], step=0.5)
                inv_date = st.date_input("Transaction Date", datetime.date.today())
                note_val = "Direct Market Purchase"

        submit = st.form_submit_button("🚀 Save Bid to Sheet", type="primary")
        
        if submit and ticker_val:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user = st.session_state["current_user"]
            new_row = [timestamp, str(inv_date), user, asset_type, ticker_val, qty_val, price_val, total_amt_val, interest_rate, ipo_status, 0, note_val]
            
            if connected and sheet_trans:
                sheet_trans.append_row(new_row)
                st.success(f"✅ Recorded {ticker_val} Bid successfully!")
                st.rerun()

# --- TAB 3: IPO ALLOTMENT CHECKER ---
with tab_check:
    st.subheader("🔍 IPO Allotment Quick Check Hub")
    st.caption("Copy PAN/BO-ID in 1-click and check status directly on registrar portals.")
    
    col_reg1, col_reg2, col_reg3, col_reg4 = st.columns(4)
    col_reg1.link_button("🌐 Link Intime Portal", "https://linkintime.co.in/initial_offer/public-issues.html")
    col_reg2.link_button("🌐 KFintech Portal", "https://ris.kfintech.com/ipostatus/")
    col_reg3.link_button("🌐 Bigshare Portal", "https://ipo.bigshareonline.com/ipo_status.html")
    col_reg4.link_button("🌐 IPO Premium Hub", "https://www.ipopremium.in/")
    
    st.markdown("---")
    st.markdown("##### 📋 Applied IPO Bids & Demat Info")
    
    if connected and sheet_trans:
        records = sheet_trans.get_all_records()
        if records:
            df_ipo = pd.DataFrame(records)
            df_ipo = df_ipo[df_ipo["Asset_Class"] == "IPO Bid"]
            
            if not df_ipo.empty:
                st.dataframe(df_ipo[["Date", "User", "Ticker", "Qty", "Total_Amount", "IPO_Status", "Note"]], use_container_width=True)
            else:
                st.info("No IPO applications found.")
        else:
            st.info("No records in Google Sheet.")

# --- TAB 4: PORTFOLIO & LIVE P&L ---
with tab_port:
    st.subheader("📊 Live Portfolio Analytics")
    if connected and sheet_trans:
        records = sheet_trans.get_all_records()
        if records:
            df = pd.DataFrame(records)
            df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce").fillna(0)
            df["Buy_Price"] = pd.to_numeric(df["Buy_Price"], errors="coerce").fillna(0)
            df["Total_Amount"] = pd.to_numeric(df["Total_Amount"], errors="coerce").fillna(0)
            
            def get_live_price(symbol):
                try:
                    if "." not in symbol:
                        symbol = symbol + ".NS"
                    stock = yf.Ticker(symbol)
                    return stock.fast_info.last_price
                except Exception:
                    return None

            live_data = []
            for idx, row in df.iterrows():
                ticker = str(row.get("Ticker", "")).strip()
                qty = row["Qty"]
                buy_price = row["Buy_Price"]
                invested = row["Total_Amount"]
                asset = row.get("Asset_Class", "")
                
                if asset == "Shares / Stock" and ticker:
                    curr_price = get_live_price(ticker) or buy_price
                    curr_val = qty * curr_price
                    pnl = curr_val - invested
                    pnl_pct = (pnl / invested) * 100 if invested > 0 else 0
                else:
                    curr_price = buy_price
                    curr_val = invested
                    pnl = 0.0
                    pnl_pct = 0.0
                    
                live_data.append({
                    "Date": row.get("Date"),
                    "User": row.get("User"),
                    "Asset": asset,
                    "Ticker/IPO": ticker,
                    "Qty": qty,
                    "Buy Price (₹)": buy_price,
                    "Invested (₹)": invested,
                    "Live Price (₹)": round(curr_price, 2),
                    "Current Value (₹)": round(curr_val, 2),
                    "Unrealized P&L (₹)": round(pnl, 2),
                    "P&L %": f"{round(pnl_pct, 2)}%"
                })
                
            res_df = pd.DataFrame(live_data)
            tot_inv = res_df["Invested (₹)"].sum()
            tot_val = res_df["Current Value (₹)"].sum()
            tot_pnl = res_df["Unrealized P&L (₹)"].sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Investment", f"₹{tot_inv:,.2f}")
            m2.metric("Current Portfolio Value", f"₹{tot_val:,.2f}")
            m3.metric("Total Unrealized P&L", f"₹{tot_pnl:,.2f}", delta=f"{round(tot_pnl, 2)}")
            
            st.markdown("---")
            st.dataframe(res_df, use_container_width=True)

# --- TAB 5: DYNAMIC INTEREST & ASBA SETTLEMENT ---
with tab_settle:
    st.subheader("🤝 Dynamic ASBA & Capital Interest Ledger")
    
    if connected and sheet_trans:
        records = sheet_trans.get_all_records()
        if records:
            df_settle = pd.DataFrame(records)
            calc_date = st.date_input("Settlement Target Date", datetime.date.today())
            
            settle_records = []
            for idx, row in df_settle.iterrows():
                try:
                    inv_date = datetime.datetime.strptime(str(row["Date"]), "%Y-%m-%d").date()
                except Exception:
                    inv_date = calc_date
                    
                amt = float(row.get("Total_Amount", 0))
                rate = float(row.get("Interest_Rate", 10))
                user = row.get("User", "")
                asset = row.get("Asset_Class", "")
                ticker = row.get("Ticker", "")
                
                days_blocked = (calc_date - inv_date).days if calc_date >= inv_date else 0
                accrued_interest = (amt * rate * days_blocked) / (100 * 365)
                
                settle_records.append({
                    "Investor": user,
                    "Asset Type": asset,
                    "Details": ticker,
                    "Principal (₹)": amt,
                    "ROI (% p.a.)": rate,
                    "Days Blocked": days_blocked,
                    "Accrued Interest (₹)": round(accrued_interest, 2),
                    "Total Claim Value (₹)": round(amt + accrued_interest, 2)
                })
                
            s_df = pd.DataFrame(settle_records)
            st.dataframe(s_df, use_container_width=True)
            
            st.markdown("---")
            summary = s_df.groupby("Investor").agg({
                "Principal (₹)": "sum",
                "Accrued Interest (₹)": "sum",
                "Total Claim Value (₹)": "sum"
            }).reset_index()
            st.dataframe(summary, use_container_width=True)
