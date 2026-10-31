import streamlit as st
import altair as alt

def total_expense_by_category_month(con):

    st.subheader("Total Expenses by Category (Current Month)")
    cat_df = con.execute("""
        SELECT category, SUM(ABS(amount)) as total 
        FROM transactions 
        WHERE amount < 0 
        AND date_trunc('month', transaction_date) = date_trunc('month', CURRENT_DATE())
        GROUP BY category 
        ORDER BY total DESC
    """).df()
    
    if not cat_df.empty:
        st.bar_chart(cat_df.set_index('category'))
    else:
        st.info("No expense transactions found for the current month.")

def monthly_cash_flow_trend(con):
    st.subheader("Monthly Cash Flow Trend")
    monthly_df = con.execute("""
        SELECT 
            strftime('%Y-%m', transaction_date) as month,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as expense
        FROM transactions
        GROUP BY month
        ORDER BY month ASC
    """).df()
    if not monthly_df.empty:
        st.line_chart(monthly_df.set_index('month'))



def render_monthly_spend_vs_income(con):
    st.subheader("📊 Monthly Spend vs. Income Trend")
    
    # Aggregate monthly expenses (negative amounts converted to positive) and income
    query = """
        SELECT 
            strftime('%Y-%m', transaction_date) AS month,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS Expenses,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS Income
        FROM transactions
        GROUP BY month
        ORDER BY month ASC
    """
    
    try:
        df = con.execute(query).df()
        
        if not df.empty:
            # Melt dataframe from wide to long format for Altair grouped bar charting
            df_melted = df.melt('month', var_name='Type', value_name='Amount')
            
            # Build grouped bar chart with custom color mapping (Red for Expenses, Green for Income)
            chart = alt.Chart(df_melted).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X('month:N', title='Month', sort=None),
                y=alt.Y('Amount:Q', title='Amount ($)'),
                color=alt.Color(
                    'Type:N', 
                    scale=alt.Scale(domain=['Expenses', 'Income'], range=['#e74c3c', '#2ecc71']),
                    title="Flow Type"
                ),
                xOffset='Type:N',
                tooltip=['month:N', 'Type:N', alt.Tooltip('Amount:Q', format="$.2f")]
            ).properties(
                height=350
            ).configure_view(
                stroke=None
            ).interactive()
            
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No transaction data found for trend analysis.")
            
    except Exception as e:
        st.error(f"Error generating spend vs income chart: {e}")