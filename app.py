import streamlit as st
import pandas as pd
import json
import datetime
import requests
from bs4 import BeautifulSoup
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

# --- SAFE FETCH TRANSACTIONS ---
def fetch_transactions():
    if connected and sheet_trans:
        try:
            records = sheet_trans.get_all_records()
            return pd.DataFrame(records)
        except Exception:
            try:
                data = sheet_trans.get_all_values()
                if len(data) > 1:
                    headers = data[0]
                    return pd.DataFrame(data[1:], columns=headers)
            except Exception:
                pass
    return pd.DataFrame()

# --- DYNAMIC LATEST IPO & LIVE GMP SCRAPER ---
@st.cache_data(ttl=1800) # Auto refresh every 30 mins
def fetch_live_ipos_and_gmp():
    ipo_dict = {}
    
    # Primary Stream Scraper (IPO Premium / Aggregator Data)
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        url = "https://www.investorgain.com/report/live-ipo-gmp/331/"
        res = requests.get(url, headers=headers, timeout=6)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')[1:]
                for row in rows[:15]: # Latest 15 active IPOs
                    cols = row.find_all('td')
                    if len(cols) >= 6:
                        name = cols[0].text.strip()
                        price_str = cols[2].text.strip().replace("₹", "").replace(",", "")
                        gmp_str = cols[3].text.strip().replace("₹", "").replace(",", "")
                        
                        try:
                            price = float(price_str) if price_str and price_str != '--' else 100.0
                        except ValueError:
                            price = 100.0
                            
                        try:
                            gmp = float(gmp_str) if gmp_str and gmp_str != '--' else 0.0
                        except ValueError:
                            gmp = 0.0
                            
                        lot = 14 if price > 500 else (30 if price > 200 else 100)
                        
                        ipo_dict[name] = {
                            "price": price,
                            "lot": lot,
                            "gmp": gmp,
                            "gain_pct": round((gmp / price) * 100, 2) if price > 0 else 0.0
                        }
    except Exception:
        pass
        
    # Manual Entry Fallback
    ipo_dict["Other / Manual IPO Entry"] = {"price": 100.0, "lot": 1, "gmp": 0.0, "gain_pct": 0.0}
    return ipo_dict

live_ipo_data = fetch_live_ipos_and_gmp()

# --- TABS ---
tab_demat, tab_add, tab_check, tab_port, tab_settle = st.tabs([
    "👥 Manage Demat Profiles",
    "➕ Apply IPO / Add Entry", 
    "🔍 IPO Allotment & Sell Tracker",
    "📊 Portfolio & Live P&L", 
    "🤝 Dynamic Interest & Profit Ledger"
])

# --- TAB 1: MANAGE DEMAT PROFILES ---
with tab_demat:
    st.subheader("👥 Multiple Demat Accounts Directory")
    col_d1, col_d2 = st.columns([1, 1.5])
    
    with col_d1:
        st.markdown("##### ➕ Add New Demat Account")
        with st.form("add_demat_form", clear_on_submit=True):
            holder_name = st.text_input("Account Holder Name")
            pan_no = st.text_input("PAN Card Number").upper().strip()
            bo_id = st.text_input("BO ID / Demat No").strip()
            upi_id = st.text_input("Linked UPI ID").strip()
            broker = st.selectbox("Broker Name", ["Zerodha", "Groww", "AngelOne", "Upstox", "ICICI Direct", "HDFC Securities", "Other"])
            submit_demat = st.form_submit_button("💾 Save Demat Profile", type="primary")
            
            if submit_demat:
                if holder_name and pan_no and connected and sheet_demat:
                    new_demat_row = [st.session_state["current_user"], holder_name, pan_no, bo_id, upi_id, broker]
                    sheet_demat.append_row(new_demat_row)
                    st.success(f"Added Demat Profile for {holder_name}!")
                    st.rerun()
                else:
                    st.error("Fill required fields or check database connection!")
                    
    with col_d2:
        st.markdown("##### 📜 Registered Demat Profiles")
        if not df_demat.empty:
            st.dataframe(df_demat, use_container_width=True)
        else:
            st.info("No Demat profiles added yet.")

# --- TAB 2: ADD ENTRY / IPO BID ---
with tab_add:
    st.subheader("Record Investment / Apply IPO Bid")
    asset_type = st.radio("Investment Mode:", ["IPO Bid", "Shares / Stock", "Real Estate", "Mutual Fund"], horizontal=True)
    st.markdown("---")
    
    with st.form("main_entry_form"):
        col1, col2 = st.columns(2)
        
        if asset_type == "IPO Bid":
            with col1:
                selected_ipo = st.selectbox("Select Active / Upcoming IPO", list(live_ipo_data.keys()))
                
                default_price = live_ipo_data[selected_ipo]["price"]
                default_lot = live_ipo_data[selected_ipo]["lot"]
                live_gmp = live_ipo_data[selected_ipo]["gmp"]
                gain_pct = live_ipo_data[selected_ipo]["gain_pct"]
                
                ipo_name = st.text_input("Custom Name") if selected_ipo == "Other / Manual IPO Entry" else selected_ipo
                lots = st.number_input("Lots Applied", min_value=1, value=1, step=1)
                shares_per_lot = st.number_input("Shares/Lot", min_value=1, value=default_lot, step=1)
                cut_off = st.number_input("Cut-off Price (₹)", min_value=0.0, value=default_price, step=1.0)
                
            with col2:
                user_demats = df_demat[df_demat["User"] == st.session_state["current_user"]] if not df_demat.empty else pd.DataFrame()
                
                if not user_demats.empty:
                    demat_opts = [f"{row['Holder_Name']} - {row['Broker_Name']} ({row['PAN']})" for idx, row in user_demats.iterrows()]
                    selected_demat_idx = st.selectbox("Select Demat Used:", range(len(demat_opts)), format_func=lambda x: demat_opts[x])
                    chosen_demat = user_demats.iloc[selected_demat_idx]
                    demat_info_str = f"Holder: {chosen_demat['Holder_Name']} | PAN: {chosen_demat['PAN']}"
                else:
                    st.warning("⚠️ No Demat accounts found! Add one in Tab 1.")
                    demat_info_str = "Default Demat"
                
                total_qty = lots * shares_per_lot
                total_bid_amt = total_qty * cut_off
                
                st.info(f"🔥 **Live GMP:** ₹{live_gmp}/share ({gain_pct}% Est. Gain)\n\n📌 **Bid Amount:** ₹{total_bid_amt:,.2f} | **Demat:** {demat_info_str}")
                
                ipo_status = st.selectbox("ASBA Status", ["Funds Blocked / Applied", "Allotted", "Un-Allotted (Refunded)"])
                interest_rate = st.number_input("Interest Rate (% p.a.)", min_value=0.0, value=st.session_state["user_rate"], step=0.5)
                inv_date = st.date_input("Application Date", datetime.date.today())
                
            ticker_val = ipo_name
            qty_val = total_qty
            price_val = cut_off
            total_amt_val = total_bid_amt
            note_val = f"IPO ({lots} Lots) | GMP: ₹{live_gmp} | {demat_info_str}"

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
            new_row = [
                timestamp, str(inv_date), user, asset_type, ticker_val, 
                qty_val, price_val, total_amt_val, interest_rate, ipo_status, 
                0, note_val, "NO", 0.0, ""
            ]
            
            if connected and sheet_trans:
                sheet_trans.append_row(new_row)
                st.success(f"✅ Recorded {ticker_val} successfully!")
                st.rerun()

# --- TAB 3: IPO ALLOTMENT & SELL TRACKER ---
with tab_check:
    st.subheader("🔍 Allotment Portal & Share Sale Hub")
    
    col_reg1, col_reg2, col_reg3, col_reg4 = st.columns(4)
    col_reg1.link_button("🌐 Link Intime Portal", "https://linkintime.co.in/initial_offer/public-issues.html")
    col_reg2.link_button("🌐 KFintech Portal", "https://ris.kfintech.com/ipostatus/")
    col_reg3.link_button("🌐 Bigshare Portal", "https://ipo.bigshareonline.com/ipo_status.html")
    col_reg4.link_button("🌐 IPO Premium Hub", "https://www.ipopremium.in/")
    
    st.markdown("---")
    
    df_raw = fetch_transactions()
    if not df_raw.empty:
        st.markdown("##### 📈 Update Allotment / Record Sale")
        st.dataframe(df_raw[["Date", "User", "Asset_Class", "Ticker", "Qty", "Buy_Price", "Total_Amount", "IPO_Status", "Is_Sold", "Sell_Price"]], use_container_width=True)
        
        st.markdown("---")
        st.markdown("##### 💰 Sale Entry / Realize Profit")
        with st.form("sell_shares_form"):
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                sell_ticker = st.text_input("Ticker / IPO Name to Sell").upper().strip()
            with col_s2:
                sell_price = st.number_input("Selling Price per Share (₹)", min_value=0.0, value=200.0, step=1.0)
            with col_s3:
                sell_date = st.date_input("Sell Date", datetime.date.today())
                
            btn_sell = st.form_submit_button("💰 Record Share Sale", type="primary")
            
            if btn_sell and sell_ticker:
                if connected and sheet_trans:
                    user = st.session_state["current_user"]
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    sell_row = [
                        timestamp, str(sell_date), user, "Shares / Stock", sell_ticker, 
                        0, sell_price, 0.0, 0.0, "Sold", 0, f"SOLD on {sell_date}", "YES", sell_price, str(sell_date)
                    ]
                    sheet_trans.append_row(sell_row)
                    st.success(f"Successfully recorded sale for {sell_ticker}!")
                    st.rerun()

# --- TAB 4: PORTFOLIO & LIVE P&L ---
with tab_port:
    st.subheader("📊 Live Portfolio (Including Allotted IPOs)")
    df = fetch_transactions()
    if not df.empty:
        df["Qty"] = pd.to_numeric(df["Qty"], errors="coerce").fillna(0)
        df["Buy_Price"] = pd.to_numeric(df["Buy_Price"], errors="coerce").fillna(0)
        df["Total_Amount"] = pd.to_numeric(df["Total_Amount"], errors="coerce").fillna(0)
        
        portfolio_df = df[(df["Asset_Class"] == "Shares / Stock") | (df["IPO_Status"] == "Allotted")]
        
        def get_live_price(symbol):
            try:
                if "." not in symbol:
                    symbol = symbol + ".NS"
                stock = yf.Ticker(symbol)
                return stock.fast_info.last_price
            except Exception:
                return None

        live_data = []
        for idx, row in portfolio_df.iterrows():
            ticker = str(row.get("Ticker", "")).strip()
            qty = row["Qty"]
            buy_price = row["Buy_Price"]
            invested = row["Total_Amount"]
            asset = row.get("Asset_Class", "")
            is_sold = str(row.get("Is_Sold", "NO")).upper()
            
            if is_sold != "YES":
                curr_price = get_live_price(ticker) or buy_price
                curr_val = qty * curr_price
                pnl = curr_val - invested
                pnl_pct = (pnl / invested) * 100 if invested > 0 else 0
                
                live_data.append({
                    "Date": row.get("Date"),
                    "User": row.get("User"),
                    "Asset": "Allotted IPO" if asset == "IPO Bid" else asset,
                    "Ticker": ticker,
                    "Qty": qty,
                    "Buy Price (₹)": buy_price,
                    "Invested (₹)": invested,
                    "Live Price (₹)": round(curr_price, 2),
                    "Current Value (₹)": round(curr_val, 2),
                    "Unrealized P&L (₹)": round(pnl, 2),
                    "P&L %": f"{round(pnl_pct, 2)}%"
                })
                
        if live_data:
            res_df = pd.DataFrame(live_data)
            tot_inv = res_df["Invested (₹)"].sum()
            tot_val = res_df["Current Value (₹)"].sum()
            tot_pnl = res_df["Unrealized P&L (₹)"].sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Investment", f"₹{tot_inv:,.2f}")
            m2.metric("Current Value", f"₹{tot_val:,.2f}")
            m3.metric("Unrealized P&L", f"₹{tot_pnl:,.2f}", delta=f"{round(tot_pnl, 2)}")
            
            st.markdown("---")
            st.dataframe(res_df, use_container_width=True)

# --- TAB 5: DYNAMIC INTEREST & PROFIT LEDGER ---
with tab_settle:
    st.subheader("🤝 Dynamic ASBA Interest & Settlement")
    df_settle = fetch_transactions()
    if not df_settle.empty:
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
            ipo_st = row.get("IPO_Status", "")
            
            days_blocked = (calc_date - inv_date).days if calc_date >= inv_date else 0
            accrued_interest = (amt * rate * days_blocked) / (100 * 365) if ipo_st != "Allotted" else 0.0
            
            settle_records.append({
                "Investor": user,
                "Type": asset,
                "Details": ticker,
                "Principal (₹)": amt,
                "Status": ipo_st,
                "Days Blocked": days_blocked,
                "Accrued Interest (₹)": round(accrued_interest, 2),
            })
            
        s_df = pd.DataFrame(settle_records)
        st.dataframe(s_df, use_container_width=True)
        
        st.markdown("---")
        summary = s_df.groupby("Investor").agg({
            "Principal (₹)": "sum",
            "Accrued Interest (₹)": "sum"
        }).reset_index()
        st.dataframe(summary, use_container_width=True)
