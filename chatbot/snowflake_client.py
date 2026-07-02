"""
Snowflake connection and query execution for the NJIT chatbot.
All queries run against the REPORT schema (view layer).
"""

import os
import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

_SNOWFLAKE_CONFIG = {
    "user":      os.getenv("SNOWFLAKE_USER"),
    "password":  os.getenv("SNOWFLAKE_PASSWORD"),
    "account":   os.getenv("SNOWFLAKE_ACCOUNT"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
    "database":  os.getenv("SNOWFLAKE_DATABASE"),
    "role":      os.getenv("SNOWFLAKE_ROLE"),
    "schema":    os.getenv("SNOWFLAKE_REPORT_SCHEMA", "REPORT"),
}


def get_connection():
    conn = snowflake.connector.connect(**_SNOWFLAKE_CONFIG)
    conn.cursor().execute(
        f"ALTER WAREHOUSE {_SNOWFLAKE_CONFIG['warehouse']} "
        "SET AUTO_SUSPEND = 60 AUTO_RESUME = TRUE"
    )
    return conn


def run_query(sql: str) -> tuple[pd.DataFrame, str]:
    """
    Execute a SELECT query and return (DataFrame, error_message).
    error_message is empty string on success.
    Only SELECT statements are allowed — DDL/DML is blocked.
    """
    sql_stripped = sql.strip().lstrip(";").strip()
    first_word = sql_stripped.split()[0].upper() if sql_stripped else ""
    if first_word not in ("SELECT", "WITH", "SHOW"):
        return pd.DataFrame(), "Only SELECT queries are allowed."

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql_stripped)
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return pd.DataFrame(rows, columns=cols), ""
    except Exception as e:
        return pd.DataFrame(), str(e)


def test_connection() -> bool:
    """Return True if Snowflake connection is healthy."""
    try:
        conn = get_connection()
        conn.cursor().execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False
