import streamlit as st
from src.db import init_db, get_db_connection
from src.components.sidebar import render_sidebar
from src.views.overview import render_overview_view
from src.views.drilldown import render_drilldown_view
# -----------------------------------------------------------------------------
# PAGE CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Universal Financial Dashboard (Polars + DuckDB)",
    page_icon="💸",
    layout="wide"
)

# Initialize database connection
con = get_db_connection()
init_db(con)

# Pass 'con' into your sidebar function
selected_view_account, show_closed_accounts = render_sidebar(con)

st.session_state.current_account_view = selected_view_account

st.set_page_config(page_title="Personal Finance", page_icon="💰", layout="wide")


# -----------------------------------------------------------------------------
# 3. DASHBOARD VIEWS & ANALYTICS
# -----------------------------------------------------------------------------
table_check = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'transactions'").fetchone()[0]

if table_check == 0:
    st.info("👋 Welcome! Upload a statement file via the sidebar to initialize your analytical workspace.")
else:
    # Route to appropriate view
    if selected_view_account == "All Accounts":
        render_overview_view(con, selected_view_account, show_closed_accounts)
    else:
        render_drilldown_view(con, selected_view_account)
        
