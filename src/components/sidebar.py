
import streamlit as st

def render_sidebar(con):
    st.sidebar.title("📥 Ingestion Engine")
    uploaded_file = st.sidebar.file_uploader("Upload Bank Statement (CSV / Excel)", type=["csv", "xlsx"], key="file_upload")

    format_choice = st.sidebar.selectbox(
        "Select Source Layout Profile",
        [
            "Wealthsimple (WS) Export",
            "CIBC Credit Card Export",
            "CIBC Bank Account (Chequing/Savings)",
            "YNAB Export",
            "Signed Amount",
            "Split Columns"
        ], key="ingestion_format_choice",
    )

    custom_account_name = st.sidebar.selectbox("Account Identifier", 
        [
            "YNAB",
            "Wealthsimple Cash - 4732",
            "WS - Credit Card",
            "CIBC", 
            "CIBC Joint",
            "CIBC Visa",
        ], key="account_identifier"
    )

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                raw_df = pl.read_csv(uploaded_file)
            else:
                # Polars reads excel files efficiently
                raw_df = pl.read_excel(uploaded_file)
                
            with st.sidebar.expander("Preview Raw Upload"):
                st.dataframe(raw_df.head(3).to_pandas())
                
            # Normalize into Polars DataFrame
            normalized_df = normalize_bank_format(raw_df, format_choice, custom_account_name)
            

            # Register Polars DataFrame into DuckDB for zero-copy insertion
            con.register('incoming_data', normalized_df)
            
            con.execute("""
                INSERT INTO transactions 
                SELECT * FROM incoming_data 
                WHERE NOT EXISTS (
                    SELECT 1 FROM transactions t 
                    WHERE t.transaction_date = incoming_data.transaction_date 
                    AND t.description = incoming_data.description 
                    AND t.amount = incoming_data.amount 
                    AND t.account_name = incoming_data.account_name
                )
            """)
            
            # Automatically register new accounts as 'Active'
            con.execute("""
                INSERT INTO accounts (account_name, status)
                SELECT DISTINCT account_name, 'Active' FROM incoming_data
                ON CONFLICT (account_name) DO NOTHING
            """)
            
            con.unregister('incoming_data')
            
            st.sidebar.success(f"Successfully processed {len(normalized_df)} rows and saved to disk!")
        except Exception as e:
            st.sidebar.error(f"Error parsing file: {e}")


    st.sidebar.title("📂 Navigation & Ingestion")
    # ---------------------------------------
    # Closed Accounts and Picker (Sidebar)
    # ---------------------------------------
    # Toggle in sidebar for closed accounts
    show_closed_accounts = st.sidebar.checkbox("Show Closed Accounts", value=False)

    # Fetch accounts respecting the toggle
    if show_closed_accounts:
        accounts_query = "SELECT account_name FROM accounts ORDER BY account_name"
    else:
        # Filter out closed accounts (checking both lowercase and uppercase variants)
        try:
            accounts_query = """
                SELECT account_name FROM accounts 
                WHERE COALESCE(UPPER(status), 'ACTIVE') != 'CLOSED' 
                ORDER BY account_name
            """
            all_accounts_db = [row[0] for row in con.execute(accounts_query).fetchall()]
        except Exception:
            # Fallback if the 'status' column doesn't exist yet in the accounts table
            all_accounts_db = [row[0] for row in con.execute("SELECT account_name FROM accounts ORDER BY account_name").fetchall()]

    selected_view_account = st.sidebar.selectbox(
        "Select Account View", 
        ["All Accounts"] + all_accounts_db
    )


    # Keep session state in sync if the user manually uses the sidebar
    st.session_state.current_account_view = selected_view_account

    st.sidebar.markdown("---")
    # -----------------------------------------------------------------------------
    # DATABASE INSPECTOR UTILITY (Sidebar)
    # -----------------------------------------------------------------------------
    st.sidebar.markdown("---")
    with st.sidebar.expander("🛠️ Database Inspector", expanded=False):
        if st.button("Inspect Table Schemas"):
            try:
                st.write("**`transactions` Table Schema:**")
                tx_schema = con.execute("DESCRIBE transactions;").df()
                st.dataframe(tx_schema, hide_index=True, use_container_width=True)
                
                st.write("**`accounts` Table Schema:**")
                acct_schema = con.execute("DESCRIBE accounts;").df()
                st.dataframe(acct_schema, hide_index=True, use_container_width=True)
            except Exception as e:
                st.error(f"Error: {e}")
                
        if st.button("Check Row Counts"):
            try:
                tx_count = con.execute("SELECT COUNT(*) FROM transactions;").fetchone()[0]
                acct_count = con.execute("SELECT COUNT(*) FROM accounts;").fetchone()[0]
                st.success(f"📊 **transactions:** {tx_count:,} rows\n\n📁 **accounts:** {acct_count:,} rows")
            except Exception as e:
                st.error(f"Error: {e}")


    st.sidebar.subheader("⚠️ Danger Zone")
    if st.sidebar.button("🗑️ Reset Database (Clear All Data)", type="primary"):
        # Drop existing tables
        con.execute("DROP TABLE IF EXISTS transactions")
        con.execute("DROP TABLE IF EXISTS accounts")
        st.sidebar.success("Database wiped successfully! Please restart the app or refresh.")
        st.rerun()

    return selected_view_account, show_closed_accounts


