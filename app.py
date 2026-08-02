import streamlit as st
import pandas as pd
import datetime
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

# --- FETCH TRANSACTIONS SAFELY ---
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

# --- SIMPLIFIED TABS ---
tab_add, tab_ledger, tab_port, tab_demat = st.tabs([
    "➕ Add Entry / IPO Bid", 
    "🤝 Blocked Funds & Monthly Settlement",
    "📊 Stock Portfolio (Averaged)", 
    "👥 Demat Profiles"
])

# --- TAB 1: ADD ENTRY / IPO BID ---
with tab_add:
    st.subheader("➕ Record Investment / IPO Bid")
    asset_type = st.radio("Entry Type:", ["IPO Bid", "Shares / SME Stock"], horizontal=True)
    st.markdown("---")
    
    with st.form("main_entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        if asset_type == "IPO Bid":
            with col1:
                ipo_name = st.text_input("IPO Name / Ticker", placeholder="e.g. Swiggy IPO").strip()
                bid_amount = st.number_input("Total Blocked Amount (₹)", min_value=0.0, value=150000.0, step=1000.0)
                inv_date = st.date_input("Application / Block Date", datetime.date.today())
                
            with col2:
                user_demats = df_demat[df_demat["User"] == st.session_state["current_user"]] if not df_demat.empty else pd.DataFrame()
                if not user_demats.empty:
                    demat_opts = [f"{row['Holder_Name']} ({row['Broker_Name']})" for idx, row in user_demats.iterrows()]
                    selected_demat_idx = st.selectbox("Select Demat Used:", range(len(demat_opts)), format_func=lambda x: demat_opts[x])
                    chosen_demat = user_demats.iloc[selected_demat_idx]
                    demat_str = f"{chosen_demat['Holder_Name']} - {chosen_demat['Broker_Name']}"
                else:
                    demat_str = "Default Demat"
                    st.info("💡 Demat select karne ke liye Tab 4 mein Demat add karein.")
                
                fund_status = st.selectbox("Fund Status:", ["Funds Blocked", "Unblocked / Settled", "Allotted"])
                interest_rate = st.number_input("Interest Rate (% p.a.)", min_value=0.0, value=st.session_state["user_rate"], step=0.5)
                note_val = st.text_input("Note / Ref", value=f"Demat: {demat_str}")
                
            qty_val = 1
            price_val = bid_amount
            total_amt_val = bid_amount
            
        else:
            with col1:
                ipo_name = st.text_input("Stock Ticker / Symbol", placeholder="e.g. HFCL.NS, TATAMOTORS.NS").upper().strip()
                qty_val = st.number_input("Quantity Purchased", min_value=1.0, value=100.0, step=1.0)
                price_val = st.number_input("Buy Price per Share (₹)", min_value=0.0, value=150.0, step=1.0)
                
            with col2:
                total_amt_val = qty_val * price_val
                st.info(f"📌 Total Investment: **₹{total_amt_val:,.2f}**")
                inv_date = st.date_input("Purchase Date", datetime.date.today())
                fund_status = "Direct Holding"
                interest_rate = 0.0
                note_val = "Stock Purchase"

        submit = st.form_submit_button("🚀 Save Entry to Sheet", type="primary")
        
        if submit and ipo_name:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user = st.session_state["current_user"]
            
            # Row structure (15 columns compatible with Google Sheets)
            new_row = [
                timestamp, str(inv_date), user, asset_type, ipo_name, 
                qty_val, price_val, total_amt_val, interest_rate, fund_status, 
                0, note_val, "NO", 0.0, ""
            ]
            
            if connected and sheet_trans:
                sheet_trans.append_row(new_row)
                st.success(f"✅ Saved entry for {ipo_name} successfully!")
                st.rerun()

# --- TAB 2: BLOCKED FUNDS & MONTHLY SETTLEMENT ---
with tab_ledger:
    st.subheader("🤝 Blocked Funds Tracker & Interest Calculation")
    
    df_raw = fetch_transactions()
    if not df_raw.empty:
        # Filter IPO Bids
        df_ipo = df_raw[df_raw["Asset_Class"] == "IPO Bid"].copy()
        
        if not df_ipo.empty:
            calc_target_date = st.date_input("Select Settlement Target Date", datetime.date.today())
            
            records = []
            for idx, row in df_ipo.iterrows():
                try:
                    b_date = datetime.datetime.strptime(str(row["Date"]), "%Y-%m-%d").date()
                except Exception:
                    b_date = calc_target_date
                    
                amt = float(row.get("Total_Amount", 0))
                rate = float(row.get("Interest_Rate", 10))
                status = str(row.get("IPO_Status", "Funds Blocked"))
                
                # Interest calculates only while status is 'Funds Blocked'
                if status == "Funds Blocked":
                    days = (calc_target_date - b_date).days if calc_target_date >= b_date else 0
                    interest = (amt * rate * days) / (100 * 365)
                else:
                    days = 0
                    interest = 0.0
                    
                records.append({
                    "Date": row.get("Date"),
                    "User": row.get("User"),
                    "IPO Name": row.get("Ticker"),
                    "Blocked Amt (₹)": amt,
                    "Rate (% p.a.)": rate,
                    "Status": status,
                    "Days Blocked": days,
                    "Accrued Interest (₹)": round(interest, 2),
                    "Note": row.get("Note")
                })
                
            df_calc = pd.DataFrame(records)
            
            # Metrics
            tot_blocked = df_calc[df_calc["Status"] == "Funds Blocked"]["Blocked Amt (₹)"].sum()
            tot_interest = df_calc["Accrued Interest (₹)"].sum()
            
            c1, c2 = st.columns(2)
            c1.metric("Currently Blocked Capital", f"₹{tot_blocked:,.2f}")
            c2.metric(f"Total Interest (till {calc_target_date})", f"₹{tot_interest:,.2f}")
            
            st.markdown("---")
            st.markdown("##### 📜 Live Blocked Entries & Status Update")
            st.dataframe(df_calc, use_container_width=True)
            
            st.markdown("---")
            st.markdown("##### 🔄 Change Fund Status (Unblock / Allot)")
            
            # Quick status update controls
            with st.form("status_update_form"):
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    selected_ipo_name = st.selectbox("Select Entry", df_calc["IPO Name"].unique())
                with col_u2:
                    new_status = st.selectbox("New Status", ["Unblocked / Settled", "Allotted", "Funds Blocked"])
                    
                btn_update = st.form_submit_button("Update Status in Sheet", type="primary")
                
                if btn_update and connected and sheet_trans:
                    # Fetch fresh cells and update status column
                    all_rows = sheet_trans.get_all_values()
                    for r_idx, r_data in enumerate(all_rows[1:], start=2):
                        if len(r_data) >= 10 and r_data[4] == selected_ipo_name:
                            sheet_trans.update_cell(r_idx, 10, new_status) # Col 10 = IPO_Status
                    st.success(f"Status for {selected_ipo_name} updated to {new_status}!")
                    st.rerun()
        else:
            st.info("No IPO bids recorded yet.")

# --- TAB 3: STOCK PORTFOLIO (AVERAGED) ---
with tab_port:
    st.subheader("📊 Stock Portfolio (Weighted Average Costing)")
    
    df_raw = fetch_transactions()
    if not df_raw.empty:
        # Stock entries + Allotted IPOs
        df_stocks = df_raw[(df_raw["Asset_Class"] == "Shares / SME Stock") | (df_raw["IPO_Status"] == "Allotted")].copy()
        
        if not df_stocks.empty:
            df_stocks["Qty"] = pd.to_numeric(df_stocks["Qty"], errors="coerce").fillna(0)
            df_stocks["Total_Amount"] = pd.to_numeric(df_stocks["Total_Amount"], errors="coerce").fillna(0)
            
            # Group by Ticker for Weighted Average Price
            grouped = df_stocks.groupby("Ticker").agg({
                "Qty": "sum",
                "Total_Amount": "sum"
            }).reset_index()
            
            grouped["Avg Buy Price (₹)"] = grouped["Total_Amount"] / grouped["Qty"]
            
            def fetch_stock_price(symbol):
                try:
                    if "." not in symbol:
                        symbol = symbol + ".NS"
                    ticker = yf.Ticker(symbol)
                    return ticker.fast_info.last_price
                except Exception:
                    return None

            port_data = []
            for idx, row in grouped.iterrows():
                sym = str(row["Ticker"]).strip()
                qty = row["Qty"]
                invested = row["Total_Amount"]
                avg_price = row["Avg Buy Price (₹)"]
                
                curr_price = fetch_stock_price(sym) or avg_price
                curr_val = qty * curr_price
                pnl = curr_val - invested
                pnl_pct = (pnl / invested) * 100 if invested > 0 else 0
                
                port_data.append({
                    "Stock / SME Security": sym,
                    "Total Qty": qty,
                    "Avg Buy Price (₹)": round(avg_price, 2),
                    "Total Invested (₹)": round(invested, 2),
                    "Live Price (₹)": round(curr_price, 2),
                    "Current Value (₹)": round(curr_val, 2),
                    "Unrealized P&L (₹)": round(pnl, 2),
                    "Return (%)": f"{round(pnl_pct, 2)}%"
                })
                
            res_portfolio = pd.DataFrame(port_data)
            
            t_inv = res_portfolio["Total Invested (₹)"].sum()
            t_val = res_portfolio["Current Value (₹)"].sum()
            t_pnl = res_portfolio["Unrealized P&L (₹)"].sum()
            
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Total Stock Investment", f"₹{t_inv:,.2f}")
            col_m2.metric("Portfolio Value", f"₹{t_val:,.2f}")
            col_m3.metric("Unrealized Profit/Loss", f"₹{t_pnl:,.2f}", delta=f"{round(t_pnl, 2)}")
            
            st.markdown("---")
            st.dataframe(res_portfolio, use_container_width=True)
        else:
            st.info("No stock holdings or allotted shares found.")

# --- TAB 4: DEMAT PROFILES ---
with tab_demat:
    st.subheader("👥 Manage Demat Accounts")
    col_d1, col_d2 = st.columns([1, 1.5])
    
    with col_d1:
        st.markdown("##### ➕ Add Demat Profile")
        with st.form("add_demat_form", clear_on_submit=True):
            holder_name = st.text_input("Account Holder Name")
            pan_no = st.text_input("PAN Number").upper().strip()
            bo_id = st.text_input("BO ID / Demat No").strip()
            broker = st.selectbox("Broker", ["Zerodha", "Groww", "AngelOne", "Upstox", "ICICI Direct", "HDFC Securities", "Other"])
            submit_demat = st.form_submit_button("💾 Save Profile", type="primary")
            
            if submit_demat and holder_name and pan_no:
                if connected and sheet_demat:
                    new_demat_row = [st.session_state["current_user"], holder_name, pan_no, bo_id, "", broker]
                    sheet_demat.append_row(new_demat_row)
                    st.success(f"Added Demat Profile for {holder_name}!")
                    st.rerun()
                    
    with col_d2:
        st.markdown("##### 📜 Active Profiles")
        if not df_demat.empty:
            st.dataframe(df_demat, use_container_width=True)
        else:
            st.info("No Demat profiles added yet.")
