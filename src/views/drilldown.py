import streamlit as st
from src.components.modals import manual_transaction_modal
from src.components.ledger import render_ledger

def render_drilldown_view(con, selected_view_account):
    # Define the modal popup form
    
    # Render the button in your sidebar (or main page)
    if st.button("➕ Add Manual Transaction", use_container_width=True, type="secondary"):
        manual_transaction_modal()

    # -------------------------------------------------------------------------
    # INDIVIDUAL ACCOUNT DRILL-DOWN VIEW
    # -------------------------------------------------------------------------
    st.title(f"🏦 Account: {st.session_state.current_account_view}")
    st.markdown(f"Detailed ledger, balance metrics, and review status for **{selected_view_account}**.")

    # Fetch account-specific KPI metrics
    acct_metrics = con.execute("""
        SELECT 
            COALESCE(SUM(amount), 0.0) as net_flow,
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0.0) as inflow,
            COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0.0) as outflow,
            COUNT(*) as total_tx,
            SUM(CASE WHEN reviewed = TRUE THEN 1 ELSE 0 END) as reviewed_count,
            SUM(CASE WHEN reviewed = FALSE THEN 1 ELSE 0 END) as unreviewed_count,
            MAX(balance) as latest_balance,
            MIN(transaction_date) as start_date,
            MAX(transaction_date) as end_date
        FROM transactions
        WHERE account_name = ?
    """, [selected_view_account]).fetchone()

    # Display Account KPI Cards
    a_col1, a_col2, a_col3, a_col4 = st.columns(4)
    a_col1.metric("Net Flow", f"${acct_metrics[0]:,.2f}")
    a_col2.metric("Latest Balance", f"${acct_metrics[6]:,.2f}" if acct_metrics[6] is not None else "N/A")
    a_col3.metric("Reviewed Transactions", f"{acct_metrics[4]} / {acct_metrics[3]}")
    a_col4.metric("Unreviewed Items", f"{acct_metrics[5]}", delta=f"-{acct_metrics[5]}" if acct_metrics[5] > 0 else "All Clear")

    st.markdown("---")

    render_ledger(con, selected_view_account)