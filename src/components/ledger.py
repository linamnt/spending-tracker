
import streamlit as st

def render_ledger(con, selected_view_account):
    sub1, sub2 = st.columns([3, 1])
    sub1.subheader("📋 Transaction Ledger & Inline Editor")
    sub2.caption("💡 Click any Category, Note, or Review checkbox to edit inline.")

    # Fetch transactions (including notes and rowid) based on current view
    if selected_view_account == "All Accounts":
        ledger_query = """
            SELECT 
                rowid AS id, 
                transaction_date, 
                account_name, 
                description, 
                category, 
                amount, 
                transaction_type, 
                COALESCE(reviewed, false) AS reviewed,
                COALESCE(notes, '') AS notes
            FROM transactions 
            ORDER BY transaction_date DESC, id DESC
            LIMIT 500
        """
        ledger_df = con.execute(ledger_query).df()
    else:
        ledger_query = """
            SELECT 
                rowid AS id, 
                transaction_date, 
                account_name, 
                description, 
                category, 
                amount, 
                transaction_type, 
                COALESCE(reviewed, false) AS reviewed,
                COALESCE(notes, '') AS notes
            FROM transactions 
            WHERE account_name = ?
            ORDER BY transaction_date DESC, id DESC
        """
        ledger_df = con.execute(ledger_query, [selected_view_account]).df()

    if not ledger_df.empty:
        # Add a deletion selection column at the very front
        ledger_df.insert(0, "Delete?", False)
        
        edited_ledger = st.data_editor(
            ledger_df,
            column_config={
                "Delete?": st.column_config.CheckboxColumn("Delete?", help="Check to delete this row"),
                "id": None,  # Hide internal DuckDB rowid
                "transaction_date": st.column_config.DateColumn("Date", disabled=True),
                "account_name": st.column_config.TextColumn("Account", disabled=True),
                "description": st.column_config.TextColumn("Description", disabled=False),    # <--- Editable!
                "category": st.column_config.TextColumn("Category", disabled=False),       # <--- Editable!
                "amount": st.column_config.NumberColumn("Amount", disabled=True, format="$%.2f"),
                "transaction_type": st.column_config.TextColumn("Type", disabled=True),
                "reviewed": st.column_config.CheckboxColumn("Reviewed", disabled=False),    # <--- Editable!
                "notes": st.column_config.TextColumn("Notes / Details", disabled=False)     # <--- Editable!
            },
            hide_index=True,
            use_container_width=True,
            key="editable_transaction_ledger"
        )

        col_save, col_del = st.columns(2)
        
        with col_save:
            if st.button("💾 Save Ledger Changes", type="primary", use_container_width=True, key="save_ledger_btn"):
                try:
                    for _, row in edited_ledger.iterrows():
                        con.execute(
                            """
                            UPDATE transactions 
                            SET description = ?, category = ?, notes = ?, reviewed = ? 
                            WHERE rowid = ?
                            """,
                            [row["description"], row["category"], row["notes"], row["reviewed"], row["id"]]
                        )
                    st.success("Ledger changes saved successfully! Refreshing...")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving changes: {e}")
                    
        with col_del:
            rows_to_delete = edited_ledger[edited_ledger["Delete?"] == True]
            if not rows_to_delete.empty:
                if st.button(f"🗑️ Delete Selected ({len(rows_to_delete)})", type="secondary", use_container_width=True, key="delete_ledger_btn"):
                    try:
                        for row_id in rows_to_delete["id"].tolist():
                            con.execute("DELETE FROM transactions WHERE rowid = ?", [row_id])
                        st.success(f"Deleted {len(rows_to_delete)} transaction(s)!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error deleting rows: {e}")
