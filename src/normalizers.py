# -----------------------------------------------------------------------------
# 1. CANONICAL SCHEMA & POLARS ADAPTERS
# -----------------------------------------------------------------------------
import json
import os
import polars as pl
# -----------------------------------------------------------------------------
# WEALTHSIMPLE TO APP CATEGORY MAPPING
# -----------------------------------------------------------------------------
WS_APP_MAPPING_JSON = {}
mapping_file_path = "data/ws_to_category_mapping.json"

# Try loading from JSON file safely
if os.path.exists(mapping_file_path):
    try:
        with open(mapping_file_path, "r", encoding="utf-8") as f:
            file_content = f.read().strip()
            if file_content:
                WS_APP_MAPPING_JSON = json.loads(file_content)
    except Exception:
        # Fall back silently if file has formatting errors
        pass

# Fallback default dictionary if file is missing or invalid
if not WS_APP_MAPPING_JSON:
    WS_APP_MAPPING_JSON = {
        "Coffee, Tea, Sodas": ["Coffee"],
        "Culture/Experience": ["Entertainment"],
        "Desserts and Treats": ["Other food and drink"],
        "Dining Out": ["Restaurants"],
        "Fast Food": ["Restaurants"],
        "Food": ["Groceries", "Other food and drink"],
        "Gas": ["Gas, parking, and tolls"],
        "General & Other": ["Other shopping", "Uncategorized"],
        "Gifts": ["Gifts"],
        "Hydro": ["Utilities"],
        "Income & Transfers": ["Uncategorized"],
        "Meat, seafood": ["Groceries"],
        "Medical": ["Medical"],
        "Pantry": ["Groceries"],
        "Produce": ["Groceries"],
        "Snacks, Prepared Meals": ["Other food and drink"]
    }

# GUARANTEE WS_TO_APP_LOOKUP IS ALWAYS CREATED
WS_TO_APP_LOOKUP = {}
for app_cat, ws_list in WS_APP_MAPPING_JSON.items():
    if isinstance(ws_list, list):
        for ws_cat in ws_list:
            if ws_cat not in WS_TO_APP_LOOKUP:
                WS_TO_APP_LOOKUP[ws_cat] = app_cat


def auto_categorize_expression() -> pl.Expr:
    """Polars expression for deterministic auto-categorization."""
    desc = pl.col("description").str.to_uppercase()
    return (
        pl.when(desc.str.contains("GROCERY|SUPERMARKET|MARKET|FOOD"))
        .then(pl.lit("Groceries & Food"))
        .when(desc.str.contains("UBER|LYFT|GAS|TRANSIT|METRO|PARKING"))
        .then(pl.lit("Transport & Commute"))
        .when(desc.str.contains("RESTAURANT|CAFE|COFFEE|BAR|DINING"))
        .then(pl.lit("Dining & Drinks"))
        .when(desc.str.contains("NETFLIX|SPOTIFY|SUBSCRIPTION|APPLE"))
        .then(pl.lit("Subscriptions"))
        .when(desc.str.contains("ELECTRIC|WATER|UTILITY|INTERNET|PHONE"))
        .then(pl.lit("Utilities"))
        .when(desc.str.contains("PAYROLL|DEPOSIT|SALARY|TRANSFER"))
        .then(pl.lit("Income & Transfers"))
        .otherwise(pl.lit("General & Other"))
    )

def normalize_bank_format(df: pl.DataFrame, format_type: str, account_name: str) -> pl.DataFrame:
    """Transforms disparate bank layouts and YNAB exports into the unified canonical schema using Polars."""

    if format_type == "YNAB Export (Account, Date, Payee, Category, Outflow, Inflow)":
        # Clean currency strings (e.g., "$1,234.56" -> 1234.56), handling nulls/empty cells
        def clean_currency(col_name: str) -> pl.Expr:
            if col_name in df.columns:
                return (
                    df[col_name]
                    .cast(pl.Utf8)
                    .str.replace_all(r"[\$,]", "")
                    .str.strip_chars()
                    .cast(pl.Float64, strict=False)
                    .fill_null(0.0)
                )
            return pl.lit(0.0)

        inflow = clean_currency("Inflow")
        outflow = clean_currency("Outflow")
        net_amount = inflow - outflow

        # Combine Payee and Memo for rich transaction descriptions
        payee = pl.col("Payee").cast(pl.Utf8).str.strip_chars().fill_null("")
        memo = pl.col("Memo").cast(pl.Utf8).str.strip_chars().fill_null("") if "Memo" in df.columns else pl.lit("")
        
        description = (
            pl.when((memo != "") & (memo != payee))
            .then(payee + " — " + memo)
            .otherwise(payee)
        )

        # Account mapping (falls back to sidebar input if column is missing/blank)
        account_col = (
            pl.col("Account").cast(pl.Utf8).str.strip_chars() 
            if "Account" in df.columns else pl.lit(account_name)
        )

        # Category mapping: Prioritize YNAB's Category column, fallback to Group/Category, then auto-categorizer
        category_col = pl.lit("")
        if "Category" in df.columns:
            category_col = pl.col("Category").cast(pl.Utf8).str.strip_chars()
        elif "Category Group/Category" in df.columns:
            category_col = pl.col("Category Group/Category").cast(pl.Utf8).str.strip_chars()

        norm = df.select([
            pl.col("Date").str.to_date(strict=False).alias("transaction_date"),
            account_col.alias("account_name"),
            description.alias("description"),
            category_col.alias("category"),
            net_amount.alias("amount"),
            pl.when(net_amount >= 0).then(pl.lit("CREDIT")).otherwise(pl.lit("DEBIT")).alias("transaction_type"),
            pl.lit(None).cast(pl.Float64).alias("balance"),
            pl.lit(True).alias("reviewed"),  # <--- Automatically set to True for YNAB imports
            pl.lit(None).alias("notes")
        ])

        # Handle unassigned, transfer, or empty YNAB categories with the rule engine
        norm = norm.with_columns(
            pl.when(
                (pl.col("category") == "") | 
                (pl.col("category").str.to_uppercase().is_in(["UNCATEGORIZED", "UNASSIGNED", "INFLOW: READY TO ASSIGN"]))
            )
            .then(auto_categorize_expression())
            .otherwise(pl.col("category"))
            .alias("category")
        )

    elif format_type == "Signed Amount (e.g., Chase/TD style: Date, Desc, Amount)":
        amount = pl.col("Amount").cast(pl.Utf8).str.replace_all(r"[\$,]", "").cast(pl.Float64, strict=False).fill_null(0.0)
        balance = pl.col("Balance").cast(pl.Utf8).str.replace_all(r"[\$,]", "").cast(pl.Float64, strict=False) if "Balance" in df.columns else pl.lit(None).cast(pl.Float64)
        
        norm = df.select([
            pl.col("Date").str.to_date(strict=False).alias("transaction_date"),
            pl.lit(account_name).alias("account_name"),
            pl.col("Description").cast(pl.Utf8).str.strip_chars().alias("description"),
            auto_categorize_expression().alias("category"),
            amount.alias("amount"),
            pl.when(amount >= 0).then(pl.lit("CREDIT")).otherwise(pl.lit("DEBIT")).alias("transaction_type"),
            balance.alias("balance"),
            pl.lit(False).alias("reviewed"),
            pl.lit(None).alias("notes")
        ])

    elif format_type == "Split Columns (e.g., RBC/BMO style: Date, Desc, Withdrawal, Deposit)":
        withdrawal = pl.col("Withdrawal").cast(pl.Utf8).str.replace_all(r"[\$,]", "").cast(pl.Float64, strict=False).fill_null(0.0)
        deposit = pl.col("Deposit").cast(pl.Utf8).str.replace_all(r"[\$,]", "").cast(pl.Float64, strict=False).fill_null(0.0)
        amount = deposit - withdrawal
        balance = pl.col("Balance").cast(pl.Utf8).str.replace_all(r"[\$,]", "").cast(pl.Float64, strict=False) if "Balance" in df.columns else pl.lit(None).cast(pl.Float64)

        norm = df.select([
            pl.col("Date").str.to_date(strict=False).alias("transaction_date"),
            pl.lit(account_name).alias("account_name"),
            pl.col("Description").cast(pl.Utf8).str.strip_chars().alias("description"),
            auto_categorize_expression().alias("category"),
            amount.alias("amount"),
            pl.when(amount >= 0).then(pl.lit("CREDIT")).otherwise(pl.lit("DEBIT")).alias("transaction_type"),
            balance.alias("balance"),
            pl.lit(False).alias("reviewed"),
            pl.lit(None).alias("notes")
        ])

    elif format_type == "Wealthsimple (WS) Export":
        amount = (
            pl.col("amount")
            .cast(pl.Utf8)
            .str.replace_all(r"[\$,]", "")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
        )
        
        merchant = pl.col("merchant").cast(pl.Utf8).str.strip_chars().fill_null("")
        notes = pl.col("notes").cast(pl.Utf8).str.strip_chars().fill_null("") if "notes" in df.columns else pl.lit("")
        
        description = (
            pl.when((notes != "") & (notes != merchant))
            .then(merchant + " — " + notes)
            .otherwise(merchant)
        )
        
        raw_ws_cat = pl.col("category").cast(pl.Utf8).str.strip_chars() if "category" in df.columns else pl.lit("")
        
        norm = df.select([
            pl.col("transaction_date").str.to_date(strict=False).alias("transaction_date"),
            pl.lit(account_name).alias("account_name"),
            description.alias("description"),
            raw_ws_cat.alias("raw_category"),
            amount.alias("amount"),
            pl.when(amount >= 0).then(pl.lit("CREDIT")).otherwise(pl.lit("DEBIT")).alias("transaction_type"),
            pl.lit(None).cast(pl.Float64).alias("balance"),
            pl.lit(False).alias("reviewed"),
            pl.lit(None).alias("notes")
        ])
 

        # Map WS category to App category via dictionary; fallback to raw WS category or auto-categorizer
        norm = norm.with_columns(
            pl.col("raw_category")
            .replace(WS_TO_APP_LOOKUP)
            .alias("mapped_category")
        )

        norm = norm.with_columns(
            pl.when(pl.col("mapped_category").is_in(list(WS_APP_MAPPING_JSON.keys())))
            .then(pl.col("mapped_category"))
            .when((pl.col("raw_category") != "") & (pl.col("raw_category") != "Uncategorized"))
            .then(pl.col("raw_category"))
            .otherwise(auto_categorize_expression())
            .alias("category")
        ).drop(["raw_category", "mapped_category"])

        norm = norm.select([
                "transaction_date",
                "account_name",
                "description",
                "category",
                "amount",
                "transaction_type",
                "balance",
                "reviewed",
                "notes"
            ])

    elif "CIBC Bank" in format_choice:
        # CIBC Bank Account CSVs: [Date, Description, Withdrawal Amount, Deposit Amount]
        raw_df = pl.read_csv(
            uploaded_file, 
            has_header=False, 
            new_columns=["date_raw", "desc_raw", "withdrawal_raw", "deposit_raw"],
            infer_schema_length=0,
            ignore_errors=True
        )
        
        norm = raw_df.select([
            # 1. Parse date
            pl.col("date_raw").str.to_date(strict=False).alias("transaction_date"),
            
            # 2. Account name
            pl.lit(account_name).alias("account_name"),
                
            # 3. Description / Payee
            pl.col("desc_raw").str.strip_chars().alias("description"),
            
            # 4. Default Category
            pl.lit("Unassigned").alias("category"),
            
            # 5. Amount calculation: Withdrawal (negated as DEBIT) vs Deposit (positive as CREDIT)
            pl.when(
                pl.col("withdrawal_raw").is_not_null() & 
                (pl.col("withdrawal_raw") != "") & 
                (pl.col("withdrawal_raw").str.strip_chars() != "")
            )
                .then(-1.0 * pl.col("withdrawal_raw").str.replace_all(r"[\$,]", "").cast(pl.Float64))
                .otherwise(
                    pl.col("deposit_raw").str.replace_all(r"[\$,]", "").cast(pl.Float64)
                )
                .alias("amount"),
                
            # 6. Transaction Type inference
            pl.when(
                pl.col("withdrawal_raw").is_not_null() & 
                (pl.col("withdrawal_raw") != "") & 
                (pl.col("withdrawal_raw").str.strip_chars() != "")
            )
                .then(pl.lit("DEBIT"))
                .otherwise(pl.lit("CREDIT"))
                .alias("transaction_type"),
                
            # 7. Balance and Review status
            pl.lit(None).cast(pl.Float64).alias("balance"),
            pl.lit(False).alias("reviewed"),
            pl.lit(None).alias("notes")
        ])

    elif "CIBC Credit" in format_choice:
        # Read all columns as strings (Utf8) to prevent type inference errors on blank cells
        raw_df = pl.read_csv(
            uploaded_file, 
            has_header=False, 
            new_columns=["date_raw", "desc_raw", "debit_raw", "credit_raw", "card_raw"],
            infer_schema_length=0
        )
        
        norm = raw_df.select([
            # 1. Parse date
            pl.col("date_raw").str.to_date(strict=False).alias("transaction_date"),
            
            # 2. Account name with card last 4 digits
            pl.lit(account_name).alias("account_name"),
                
            # 3. Description / Payee
            pl.col("desc_raw").str.strip_chars().alias("description"),
            
            # 4. Default Category
            pl.lit("Unassigned").alias("category"),
            
            # 5. Amount calculation: Check if debit string is non-empty/non-null, cast safely
            pl.when(
                pl.col("debit_raw").is_not_null() & 
                (pl.col("debit_raw") != "") & 
                (pl.col("debit_raw").str.strip_chars() != "")
            )
                .then(-1.0 * pl.col("debit_raw").str.replace_all(r"[\$,]", "").cast(pl.Float64))
                .otherwise(
                    pl.col("credit_raw").str.replace_all(r"[\$,]", "").cast(pl.Float64)
                )
                .alias("amount"),
                
            # 6. Transaction Type inference
            pl.when(
                pl.col("debit_raw").is_not_null() & 
                (pl.col("debit_raw") != "") & 
                (pl.col("debit_raw").str.strip_chars() != "")
            )
                .then(pl.lit("DEBIT"))
                .otherwise(pl.lit("CREDIT"))
                .alias("transaction_type"),
                
            # 7. Balance and Review status
            pl.lit(None).cast(pl.Float64).alias("balance"),
            pl.lit(False).alias("reviewed"),
            pl.lit(None).alias("notes")
        ])
    # Drop rows with null dates
    return norm.drop_nulls(subset=["transaction_date"])
