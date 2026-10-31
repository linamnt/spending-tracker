import streamlit as st
from src.components.charts import (
    monthly_cash_flow_trend, 
    render_monthly_spend_vs_income, 
    total_expense_by_category_month
)
from src.components.ledger import render_ledger

def render_overview_view(con, selected_view_account, show_closed_accounts):
    table_check = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'transactions'").fetchone()[0]
    # -------------------------------------------------------------------------
    # GLOBAL VIEW (All Accounts)
    # -------------------------------------------------------------------------
    st.title("📊 Personal Financial Command Center")
    st.markdown("Unified multi-account intelligence powered by **Polars** & **DuckDB**.")   
    
    st.subheader("🏦 Account Portfolio & Status")

    metrics = con.execute("""
        SELECT 
            SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) as total_income,
            SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END) as total_expense,
            COUNT(*) as tx_count,
            MIN(t.transaction_date) as min_date,
            MAX(t.transaction_date) as max_date
        FROM transactions t
        JOIN accounts a ON t.account_name = a.account_name
        WHERE (? = TRUE OR a.status = 'Active')
    """, [show_closed_accounts]).fetchone()


    try:
        summary_query = """
            SELECT 
                a.account_name, 
                CASE WHEN COALESCE(UPPER(a.status), 'ACTIVE') = 'CLOSED' THEN True ELSE False END AS is_closed,
                COUNT(t.amount) AS total_transactions,
                COALESCE(SUM(t.amount), 0.0) AS net_balance
            FROM accounts a
            LEFT JOIN transactions t ON a.account_name = t.account_name
            GROUP BY a.account_name, a.status
            ORDER BY a.account_name;
        """
        accounts_df = con.execute(summary_query.strip()).df()

        if not accounts_df.empty:
            edited_accounts_df = st.data_editor(
                accounts_df,
                column_config={
                    "account_name": st.column_config.TextColumn("Account Name", disabled=True),
                    "is_closed": st.column_config.CheckboxColumn("Closed?", help="Check to mark account as closed"),
                    "total_transactions": st.column_config.NumberColumn("Transactions", disabled=True, format="%d"),
                    "net_balance": st.column_config.NumberColumn("Net Balance", disabled=True, format="$%.2f")
                },
                hide_index=True,
                use_container_width=True,
                key="accounts_summary_editor"
            )

            if st.button("💾 Save Status Updates", type="primary", key="save_account_status_btn"):
                try:
                    for _, row in edited_accounts_df.iterrows():
                        new_status = 'Closed' if row['is_closed'] else 'Active'
                        con.execute(
                            "UPDATE accounts SET status = ? WHERE account_name = ?",
                            [new_status, row['account_name']]
                        )
                    st.toast("Account statuses updated successfully! Refreshing...")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error updating account statuses: {e}")

            st.markdown("---")

        else:
            st.info("No accounts found in the database yet. Upload a statement to get started.")

    except Exception as e:
        st.error(f"Error loading accounts summary: {e}")
    
    st.markdown("---")

    # -----------------------------------------------------------------------------
    # MANUAL TRANSACTION MODAL DIALOG & BUTTON
    # -----------------------------------------------------------------------------
    import datetime
    # Define the modal popup form
    @st.dialog("➕ Add Manual Transaction")
    def manual_transaction_modal():
        with st.form("manual_transaction_form_modal"):
            m_date = st.date_input("Transaction Date", value=datetime.date.today())
            
            # Fetch active accounts for the dropdown
            try:
                active_accounts = [
                    row[0] for row in con.execute(
                        "SELECT account_name FROM accounts WHERE COALESCE(UPPER(status), 'ACTIVE') != 'CLOSED' ORDER BY account_name"
                    ).fetchall()
                ]
            except Exception:
                active_accounts = []
            
            if not active_accounts:
                active_accounts = ["Checking Account"]  # Fallback if no accounts exist yet
                
            m_account = st.selectbox("Account Name", active_accounts, key="modal_acct_select")
            m_desc = st.text_input("Description / Payee", placeholder="e.g., Coffee Shop")
            
            m_amount = st.number_input(
                "Amount ($)", 
                value=0.00, 
                step=0.01, 
                help="Use negative values for expenses/debits (e.g., -15.50), and positive for income/credits."
            )
            m_category = st.text_input("Category", value="Unassigned", placeholder="e.g., Food")
            
            # Automatically infer transaction type based on sign
            m_type = "DEBIT" if m_amount < 0 else "CREDIT"
            st.caption(f"Inferred Type: `{m_type}`")
            
            m_reviewed = st.checkbox("Mark as Reviewed", value=True)
            
            submitted = st.form_submit_button("Save Transaction", type="primary", use_container_width=True)
            
            if submitted:
                if not m_desc.strip():
                    st.error("Please enter a description or payee.")
                else:
                    try:
                        # 1. Ensure the account exists in the accounts table
                        con.execute(
                            "INSERT OR IGNORE INTO accounts (account_name, status) VALUES (?, 'Active')",
                            [m_account]
                        )
                        
                        # 2. Insert the transaction into DuckDB
                        con.execute("""
                            INSERT INTO transactions (
                                transaction_date, 
                                account_name, 
                                description, 
                                category, 
                                amount, 
                                transaction_type, 
                                balance, 
                                reviewed
                            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                        """, [
                            m_date, 
                            m_account, 
                            m_desc.strip(), 
                            m_category.strip(), 
                            m_amount, 
                            m_type, 
                            m_reviewed
                        ])
                        
                        st.success(f"Successfully added: **{m_desc}** ({m_amount:+$})!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error saving transaction: {e}")

    # Render the button in your sidebar (or main page)
    if st.button("➕ Add Manual Transaction", use_container_width=True, type="secondary"):
        manual_transaction_modal()
    # -----------------------------------------------------------------------------
    # FILTERS TOOLBAR & CATEGORY CHECKBOXES
    # -----------------------------------------------------------------------------
    st.subheader("🔍 Transaction Explorer & Filters")
    
    # Fetch all unique categories from the database
    categories = [row[0] for row in con.execute("SELECT DISTINCT category FROM transactions ORDER BY category").fetchall()]

    # Initialize session state for category checkboxes
    if "category_filter_state" not in st.session_state:
        st.session_state.category_filter_state = {cat: True for cat in categories}
    else:
        # Ensure any newly imported categories default to checked
        for cat in categories:
            if cat not in st.session_state.category_filter_state:
                st.session_state.category_filter_state[cat] = True

    # Collapsible Category Filter Panel with Scrollable Box and Select All / Clear All
    with st.expander("🏷️ Filter by Category (Click to expand)", expanded=False):
        btn_col1, btn_col2 = st.columns(2)
        if btn_col1.button("Select All Categories"):
            for cat in categories:
                st.session_state.category_filter_state[cat] = True
            st.rerun()
        if btn_col2.button("Clear All Categories"):
            for cat in categories:
                st.session_state.category_filter_state[cat] = False
            st.rerun()
            
        st.markdown("---")
        

        # Render checkboxes inside a scrollable HTML container using st.container
        selected_categories = []
        with st.container(height=200):  # <--- Native scrollable container with fixed height in pixels
            for i, cat in enumerate(categories):
                is_checked = st.checkbox(
                    cat, 
                    value=st.session_state.category_filter_state.get(cat, True), 
                    key=f"cat_chk_{i}_{cat}"
                )
                st.session_state.category_filter_state[cat] = is_checked
                if is_checked:
                    selected_categories.append(cat)

    # Remaining filter controls (Keyword search & Amount slider)
    f_col1, f_col2 = st.columns(2)
    search_keyword = f_col1.text_input("Search Description", "")
    
    min_max_amounts = con.execute("SELECT MIN(amount), MAX(amount) FROM transactions").fetchone()
    selected_range = f_col2.slider(
        "Amount Range Filter", 
        float(min_max_amounts[0]), 
        float(max_del:=min_max_amounts[1]), 
        (float(min_max_amounts[0]), float(max_del))
    )

    # Updated SQL query using the selected categories list
    query = """
        SELECT t.transaction_date, t.account_name, t.description, t.category, t.amount, t.transaction_type 
        FROM transactions t
        JOIN accounts a ON t.account_name = a.account_name
        WHERE (? = TRUE OR a.status = 'Active')
        AND t.category = ANY(?) 
        AND (t.description LIKE ? OR ? = '')
        AND t.amount BETWEEN ? AND ?
        ORDER BY t.transaction_date DESC
    """
    filtered_df = con.execute(query, [
        show_closed_accounts, 
        selected_categories if selected_categories else [''], # Avoid empty array errors
        f"%{search_keyword}%", 
        search_keyword, 
        selected_range[0], 
        selected_range[1]
    ]).df()

    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------------
    # TRANSACTION REVIEW QUEUE
    # -----------------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🔍 Transaction Review Queue")

    review_query = """
        SELECT transaction_date, account_name, description, category, amount, reviewed 
        FROM transactions 
        WHERE reviewed = FALSE OR category IN ('General & Other', 'Uncategorized', '')
        ORDER BY transaction_date DESC
    """
    review_df = con.execute(review_query).df()

    if not review_df.empty:
        st.info(f"Found **{len(review_df)}** transactions requiring review or categorization.")

        edited_df = st.data_editor(
            review_df,
            column_config={
                "transaction_date": st.column_config.DateColumn("Date", disabled=True),
                "account_name": st.column_config.TextColumn("Account", disabled=True),
                "description": st.column_config.TextColumn("Description", disabled=True),
                "amount": st.column_config.NumberColumn("Amount", format="$%.2f", disabled=True),
                "category": st.column_config.TextColumn("Category"),
                "reviewed": st.column_config.CheckboxColumn("Mark Reviewed", default=True)
            },
            hide_index=True,
            use_container_width=True,
            key="review_queue_editor"
        )

        if st.button("💾 Save Review Updates", type="primary"):
            for _, row in edited_df.iterrows():
                con.execute("""
                    UPDATE transactions 
                    SET category = ?, reviewed = ? 
                    WHERE transaction_date = ? 
                    AND account_name = ? 
                    AND description = ? 
                    AND amount = ?
                """, [row['category'], row['reviewed'], row['transaction_date'], row['account_name'], row['description'], row['amount']])
            st.success("Review updates successfully saved to disk! Refreshing...")
            st.rerun()
    else:
        st.success("🎉 All transactions have been reviewed and categorized!")

    render_ledger(con, selected_view_account)

    col1, col2 = st.columns(2)
    with col1:
        render_monthly_spend_vs_income(con)
        
    with col2:
        total_expense_by_category_month(con)

    