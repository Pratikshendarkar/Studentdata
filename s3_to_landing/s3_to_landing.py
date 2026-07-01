"""
S3 -> Snowflake LND ingestion for the RD2 pipeline.

Loads randomdata.csv from an S3 stage into LND.student_enrollment
using COPY INTO. Mirrors the ARR_Calc Round 1 ingestion pattern, adapted
for a single source table.

Usage:
    python s3_to_landing.py [--full-refresh]
"""

import argparse
import os

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

SNOWFLAKE_CONFIG = {
    "user": os.getenv("SNOWFLAKE_USER"),
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "account": os.getenv("SNOWFLAKE_ACCOUNT"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
    "database": os.getenv("SNOWFLAKE_DATABASE"),
    "role": os.getenv("SNOWFLAKE_ROLE"),
    "schema": os.getenv("SNOWFLAKE_LANDING_SCHEMA", "LND"),
}

# Snowflake external stage backed by a storage integration (no static AWS
# keys -- see snowflake_setup.sql).
STAGE_NAME = "LND.rd2_s3_stage"

TABLE = "LND.student_enrollment"
FILENAME = "randomdata.csv"
COL_COUNT = 16  # student_id .. term_code, per the data dictionary


def get_connection():
    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    warehouse = SNOWFLAKE_CONFIG["warehouse"]
    conn.cursor().execute(
        f"ALTER WAREHOUSE {warehouse} SET AUTO_SUSPEND = 60 AUTO_RESUME = TRUE"
    )
    return conn


def copy_into(cursor):
    """Run COPY INTO using a SELECT so a load timestamp can be appended."""
    col_refs = ", ".join(f"${i}" for i in range(1, COL_COUNT + 1))
    cursor.execute(
        f"""
        COPY INTO {TABLE}
        FROM (
            SELECT {col_refs},
                   CURRENT_TIMESTAMP()
            FROM @{STAGE_NAME}/{FILENAME}
        )
        FILE_FORMAT = (FORMAT_NAME = 'LND.csv_format')
        ON_ERROR = 'CONTINUE'
        """
    )
    return cursor.fetchall()


def main(full_refresh: bool):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        if full_refresh:
            cursor.execute(f"TRUNCATE TABLE {TABLE}")
            print(f"[INFO] Truncated {TABLE}")

        result = copy_into(cursor)
        for row in result:
            print(f"[COPY INTO {TABLE}] {row}")

        cursor.execute(f"SELECT COUNT(*) FROM {TABLE}")
        count = cursor.fetchone()[0]
        print(f"[INFO] {TABLE} row count: {count}")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Truncate the landing table before loading",
    )
    args = parser.parse_args()
    main(full_refresh=args.full_refresh)
