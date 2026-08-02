import streamlit as st
import pandas as pd
import datetime
import gspread
import yfinance as yf

st.set_page_config(page_title="Wise Finvestors", layout="wide")

# =========================================================
# GOOGLE SHEET CONNECTION
# =========================================================
@st.cache_resource
def get_gspread_client():
    return gspread.service_account_from_dict(st.secrets["gcp_service_account"])

connected = False
sheet_trans = None
sheet_users = None
sheet_settle = None

try:
    client = get_gspread_client()
    db = client.open("Investment_Database")
    sheet_trans = db.worksheet("Transactions")
    sheet_users = db.worksheet("Users_List")
    sheet_settle = db.worksheet("Settlements")
    connected = True
except Exception as e:
    connected = False
    conn_error = str(e)

# Column order in Transactions sheet (1-indexed for gspread updates)
COLS = ["Timestamp", "Date", "User", "Asset_Class", "Ticker", "Qty", "Buy_Price",
        "Total_Amount", "Interest_Rate", "Status", "Unblock_Date", "Last_Settled_Date", "Note"]
COL_IDX = {name: i + 1 for i, name in enumerate(COLS)}


# =========================================================
# HELPERS
# =========================================================
def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_date(val, fallback):
    """Parse a YYYY-MM-DD string into a date object; return fallback if blank/invalid."""
    if not val:
        return fallback
    try:
        return datetime.datetime.strptime(str(val).strip(), "%Y-%m-%d").date()
    except ValueError:
        return fallback


def fetch_transactions():
    """Always pulls fresh data - no caching, so entries show up immediately."""
    if not (connected and sheet_trans):
        return pd.DataFrame(columns=COLS)
    try:
        values = sheet_trans.get_all_values()
    except Exception:
        return pd.DataFrame(columns=COLS)

    if len(values) < 2:
        return pd.DataFrame(columns=COLS)

    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)

    # Ensure every expected column exists even if sheet is missing one
    for c in COLS:
        if c not in df.columns:
            df[c] = ""

    df["Qty"] = df["Qty"].apply(lambda x: safe_float(x, 0.0))
    df["Buy_Price"] = df["Buy_Price"].apply(lambda x: safe_float(x, 0.0))
    df["Total_Amount"] = df["Total_Amount"].apply(lambda x: safe_float(x, 0.0))
    df["Interest_Rate"] = df["Interest_Rate"].apply(lambda x: safe_float(x, 0.0))
    return df


def append_transaction(row_dict):
    new_row = [row_dict.get(c, "") for c in COLS]
    sheet_trans.append_row(new_row)


def update_transaction_cell(timestamp_value, column_name, new_value):
    """Finds the row by its unique Timestamp and updates one cell."""
    try:
        cell = sheet_trans.find(timestamp_value)
        sheet_trans.update_cell(cell.row, COL_IDX[column_name], new_value)
        return True
    except Exception:
        return False


def get_live_price(symbol):
    try:
        if "." not in symbol:
            symbol = symbol + ".NS"
        stock = yf.Ticker(symbol)
        price = stock.fast_info.last_price
        return float(price) if price else None
    except Exception:
        return None


# =========================================================
# USERS
# =========================================================
USERS = {}
if connected and sheet_users:
    try:
        for row in sheet_users.get_all_records():
            mob = str(row.get("Mobile", "")).strip().replace(".0", "")
            pin = str(row.get("PIN", "")).strip()
            name = str(row.get("Name", "")).strip()
            rate = safe_float(row.get("Interest_Rate", 10.0), 10.0)
            if mob:
                USERS[mob] = {"name": name, "pin": pin, "default_rate": rate}
    except Exception:
        pass

if not USERS:
    USERS = {"9999911111": {"name": "Admin", "pin": "1234", "default_rate": 10.0}}


# =========================================================
# LOGIN
# =========================================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["current_user"] = None
    st.session_state["user_rate"] = 10.0

if not st.session_state["logged_in"]:
    st.title("🔐 Wise Finvestors - Login")

    if connected:
        st.success("🟢 Connected to Google Sheet Database")
    else:
        st.error(f"⚠️ Could not connect to Google Sheet. Details: {conn_error}")

    mobile = st.text_input("Mobile Number").strip()
    pin = st.text_input("PIN / Password", type="password").strip()

    if st.button("Login", type="primary"):
        if mobile in USERS and USERS[mobile]["pin"] == pin:
            st.session_state["logged_in"] = True
            st.session_state["current_user"] = USERS[mobile]["name"]
            st.session_state["user_rate"] = USERS[mobile]["default_rate"]
            st.rerun()
        else:
            st.error("Invalid Mobile Number or PIN!")
    st.stop()

# =========================================================
# LOGGED-IN APP
# =========================================================
st.sidebar.markdown(f"👤 Logged in: **{st.session_state['current_user']}**")
if st.sidebar.button("Logout"):
    st.session_state["logged_in"] = False
    st.session_state["current_user"] = None
    st.rerun()

st.title("📈 Wise Finvestors")

tab_add, tab_ipo, tab_portfolio, tab_settle = st.tabs([
    "➕ Add Entry",
    "🔓 IPO Block / Unblock",
    "📊 Portfolio",
    "🤝 Monthly Settlement"
])

# ---------------------------------------------------------
# TAB 1: ADD ENTRY
# ---------------------------------------------------------
with tab_add:
    st.subheader("Record a New Entry")
    asset_type = st.radio(
        "Type of Entry:",
        ["Shares / Stock", "IPO Applied", "Real Estate", "Mutual Fund"],
        horizontal=True
    )
    st.markdown("---")

    with st.form("add_entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        if asset_type == "Shares / Stock":
            with col1:
                ticker = st.text_input("Ticker (e.g. HFCL.NS, TATAMOTORS.NS)").upper().strip()
                qty = st.number_input("Quantity", min_value=0.01, value=1.0, step=1.0)
                buy_price = st.number_input("Buy Price per Share (₹)", min_value=0.0, value=0.0, step=1.0)
            with col2:
                total_amount = qty * buy_price
                st.text_input("Total Amount (auto)", value=f"₹ {total_amount:,.2f}", disabled=True)
                interest_rate = st.number_input("Interest Rate (% p.a., 0 if self-funded)",
                                                 min_value=0.0, value=0.0, step=0.5)
                inv_date = st.date_input("Purchase Date", datetime.date.today())
            note = ""
            status = "Active"
            unblock_date = ""

        elif asset_type == "IPO Applied":
            with col1:
                ticker = st.text_input("IPO Name").strip()
                total_amount = st.number_input("Amount Blocked (₹)", min_value=0.0, value=0.0, step=1000.0)
            with col2:
                interest_rate = st.number_input("Interest Rate (% p.a.)",
                                                 min_value=0.0, value=st.session_state["user_rate"], step=0.5)
                inv_date = st.date_input("Application Date", datetime.date.today())
            qty = 0
            buy_price = 0
            note = "IPO application - funds blocked"
            status = "Blocked"
            unblock_date = ""

        else:  # Real Estate / Mutual Fund
            with col1:
                ticker = st.text_input("Details (e.g. Plot Advance, Fund Name)").strip()
                total_amount = st.number_input("Amount (₹)", min_value=0.0, value=0.0, step=1000.0)
            with col2:
                interest_rate = st.number_input("Interest Rate (% p.a.)",
                                                 min_value=0.0, value=st.session_state["user_rate"], step=0.5)
                inv_date = st.date_input("Date", datetime.date.today())
            qty = 0
            buy_price = 0
            note = ""
            status = "Active"
            unblock_date = ""

        submit = st.form_submit_button("🚀 Save Entry", type="primary")

        if submit:
            if not ticker:
                st.error("Please enter a name/ticker/details field.")
            elif not connected:
                st.error("Sheet not connected - cannot save.")
            else:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                row = {
                    "Timestamp": timestamp,
                    "Date": str(inv_date),
                    "User": st.session_state["current_user"],
                    "Asset_Class": asset_type,
                    "Ticker": ticker,
                    "Qty": qty,
                    "Buy_Price": buy_price,
                    "Total_Amount": total_amount,
                    "Interest_Rate": interest_rate,
                    "Status": status,
                    "Unblock_Date": unblock_date,
                    "Last_Settled_Date": str(inv_date),
                    "Note": note
                }
                append_transaction(row)
                st.success(f"✅ Saved: {asset_type} - {ticker} (₹{total_amount:,.2f})")
                st.rerun()

# ---------------------------------------------------------
# TAB 2: IPO BLOCK / UNBLOCK MANAGER
# ---------------------------------------------------------
with tab_ipo:
    st.subheader("🔓 Manage IPO Applications")
    st.caption("When your funds get released (allotted or refunded), mark it Unblocked here. "
               "Interest stops accruing from the unblock date you enter.")

    df_all = fetch_transactions()
    df_ipo = df_all[df_all["Asset_Class"] == "IPO Applied"].copy()

    if df_ipo.empty:
        st.info("No IPO applications recorded yet.")
    else:
        display_cols = ["Date", "User", "Ticker", "Total_Amount", "Interest_Rate", "Status", "Unblock_Date"]
        st.dataframe(df_ipo[display_cols], use_container_width=True)

        st.markdown("---")
        st.markdown("##### Mark an Application as Unblocked")

        blocked_df = df_ipo[df_ipo["Status"] == "Blocked"]
        if blocked_df.empty:
            st.info("No entries currently marked Blocked.")
        else:
            options = {}
            for _, r in blocked_df.iterrows():
                label = f"{r['User']} | {r['Ticker']} | ₹{r['Total_Amount']:,.0f} | Applied {r['Date']}"
                options[label] = r["Timestamp"]

            chosen_label = st.selectbox("Select IPO Entry", list(options.keys()))
            unblock_d = st.date_input("Unblock Date (allotment/refund date)", datetime.date.today())

            if st.button("🔓 Mark Unblocked", type="primary"):
                ts = options[chosen_label]
                ok1 = update_transaction_cell(ts, "Status", "Unblocked")
                ok2 = update_transaction_cell(ts, "Unblock_Date", str(unblock_d))
                if ok1 and ok2:
                    st.success("Marked as Unblocked. Interest will stop accruing from this date.")
                    st.rerun()
                else:
                    st.error("Could not update the sheet. Please check the connection and try again.")

# ---------------------------------------------------------
# TAB 3: PORTFOLIO (Weighted Average + Live P&L)
# ---------------------------------------------------------
with tab_portfolio:
    st.subheader("📊 Portfolio")

    df_all = fetch_transactions()

    st.markdown("##### 📈 Shares / Stock Holdings (Weighted Average Cost)")
    df_shares = df_all[df_all["Asset_Class"] == "Shares / Stock"].copy()

    if df_shares.empty:
        st.info("No stock holdings recorded yet.")
    else:
        grouped = df_shares.groupby(["User", "Ticker"]).agg(
            Total_Qty=("Qty", "sum"),
            Total_Invested=("Total_Amount", "sum")
        ).reset_index()
        grouped = grouped[grouped["Total_Qty"] > 0]
        grouped["Avg_Buy_Price"] = grouped["Total_Invested"] / grouped["Total_Qty"]

        rows = []
        for _, r in grouped.iterrows():
            live_price = get_live_price(r["Ticker"])
            if live_price is None:
                live_price = r["Avg_Buy_Price"]
            current_value = r["Total_Qty"] * live_price
            pnl = current_value - r["Total_Invested"]
            pnl_pct = (pnl / r["Total_Invested"] * 100) if r["Total_Invested"] > 0 else 0
            rows.append({
                "User": r["User"],
                "Ticker": r["Ticker"],
                "Qty": round(r["Total_Qty"], 2),
                "Avg Buy Price (₹)": round(r["Avg_Buy_Price"], 2),
                "Invested (₹)": round(r["Total_Invested"], 2),
                "Live Price (₹)": round(live_price, 2),
                "Current Value (₹)": round(current_value, 2),
                "Unrealized P&L (₹)": round(pnl, 2),
                "P&L %": f"{pnl_pct:.2f}%"
            })

        res_df = pd.DataFrame(rows)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Invested", f"₹{res_df['Invested (₹)'].sum():,.2f}")
        c2.metric("Current Value", f"₹{res_df['Current Value (₹)'].sum():,.2f}")
        c3.metric("Unrealized P&L", f"₹{res_df['Unrealized P&L (₹)'].sum():,.2f}")
        st.dataframe(res_df, use_container_width=True)

    st.markdown("---")
    st.markdown("##### 🏠 Real Estate / Mutual Fund / IPO Holdings")
    df_other = df_all[df_all["Asset_Class"].isin(["Real Estate", "Mutual Fund", "IPO Applied"])].copy()
    if df_other.empty:
        st.info("No other holdings recorded yet.")
    else:
        st.dataframe(
            df_other[["Date", "User", "Asset_Class", "Ticker", "Total_Amount", "Status"]],
            use_container_width=True
        )

# ---------------------------------------------------------
# TAB 4: MONTHLY SETTLEMENT (non-cumulative)
# ---------------------------------------------------------
with tab_settle:
    st.subheader("🤝 Monthly Interest Settlement")
    st.caption("Interest is calculated only from each entry's Last Settled Date (not from day one). "
               "Click 'Settle Now' to lock in this period's interest and reset the counter.")

    calc_date = st.date_input("Calculate Interest Up To", datetime.date.today())

    df_all = fetch_transactions()
    df_interest = df_all[df_all["Interest_Rate"] > 0].copy()

    if df_interest.empty:
        st.info("No interest-bearing entries found.")
    else:
        pending_rows = []
        for _, r in df_interest.iterrows():
            entry_date = safe_date(r["Date"], calc_date)
            last_settled = safe_date(r["Last_Settled_Date"], entry_date)

            # If an IPO has been unblocked, interest stops at the unblock date
            end_date = calc_date
            if r["Asset_Class"] == "IPO Applied" and r["Status"] == "Unblocked":
                unblock_d = safe_date(r["Unblock_Date"], calc_date)
                end_date = min(calc_date, unblock_d)

            days = (end_date - last_settled).days
            days = max(days, 0)
            interest = (r["Total_Amount"] * r["Interest_Rate"] * days) / (100 * 365)

            pending_rows.append({
                "Timestamp": r["Timestamp"],
                "User": r["User"],
                "Asset": r["Asset_Class"],
                "Details": r["Ticker"],
                "Principal (₹)": round(r["Total_Amount"], 2),
                "ROI (%)": r["Interest_Rate"],
                "From": str(last_settled),
                "To": str(end_date),
                "Days": days,
                "Pending Interest (₹)": round(interest, 2)
            })

        pending_df = pd.DataFrame(pending_rows)
        st.dataframe(pending_df.drop(columns=["Timestamp"]), use_container_width=True)

        st.markdown("---")
        st.markdown("#### 💰 Pending Interest by Investor")
        summary = pending_df.groupby("User").agg(
            Total_Principal=("Principal (₹)", "sum"),
            Total_Pending_Interest=("Pending Interest (₹)", "sum")
        ).reset_index()
        st.dataframe(summary, use_container_width=True)

        st.markdown("---")
        if st.button("✅ Settle All Entries Up To This Date", type="primary"):
            settled_count = 0
            for _, r in pending_df.iterrows():
                if r["Pending Interest (₹)"] <= 0 and r["Days"] == 0:
                    continue
                # Log the settlement
                if connected and sheet_settle:
                    log_row = [
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        r["User"], r["Details"], r["Asset"],
                        r["From"], r["To"], r["Days"], r["Principal (₹)"], r["Pending Interest (₹)"]
                    ]
                    sheet_settle.append_row(log_row)
                # Reset the counter on the original transaction
                update_transaction_cell(r["Timestamp"], "Last_Settled_Date", r["To"])
                settled_count += 1
            st.success(f"Settled {settled_count} entries. Interest will now accrue fresh from {calc_date}.")
            st.rerun()

        with st.expander("📜 View Settlement History"):
            if connected and sheet_settle:
                try:
                    hist = sheet_settle.get_all_records()
                    if hist:
                        st.dataframe(pd.DataFrame(hist), use_container_width=True)
                    else:
                        st.info("No settlements recorded yet.")
                except Exception:
                    st.info("Could not load settlement history.")
