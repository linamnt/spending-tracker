import streamlit as st
import datetime

@st.dialog("➕ Add Manual Transaction")
def manual_transaction_modal(con):
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
