import duckdb

def get_db_connection():
    return duckdb.connect("finance.duckdb", read_only=False)

def init_db(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_name VARCHAR PRIMARY KEY,
            status VARCHAR DEFAULT 'Active'
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_date DATE,
            account_name VARCHAR,
            description VARCHAR,
            category VARCHAR,
            amount DOUBLE,
            transaction_type VARCHAR,
            balance DOUBLE,
            reviewed BOOLEAN,
            notes VARCHAR
        )
    """)