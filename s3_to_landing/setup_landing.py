"""
One-time Snowflake setup for the RD2 pipeline: database objects, schemas,
warehouse, file format, S3 stage (static keys, pulled from .env at
runtime), and the LND.student_enrollment table.

Mirrors snowflake_setup.sql but issues the CREATE STAGE statement with
real credential values substituted in-memory, so no AWS key ever has to
be written into a .sql file on disk (snowflake_setup.sql keeps the
&AWS_KEY_ID / &AWS_SECRET_KEY placeholders for reference/documentation).

Usage:
    python setup_landing.py
"""

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
}

AWS_KEY_ID = os.getenv("AWS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
S3_BUCKET = os.getenv("S3_BUCKET")
S3_PATH = os.getenv("S3_PATH")

DDL_STATEMENTS = [
    "USE DATABASE {database}",
    "CREATE SCHEMA IF NOT EXISTS LND",
    "CREATE SCHEMA IF NOT EXISTS STG",
    "CREATE SCHEMA IF NOT EXISTS REPORT",
    """
    CREATE WAREHOUSE IF NOT EXISTS {warehouse}
        WAREHOUSE_SIZE = 'MEDIUM'
        AUTO_SUSPEND = 60
        AUTO_RESUME = TRUE
    """,
    """
    CREATE FILE FORMAT IF NOT EXISTS LND.csv_format
        TYPE = 'CSV'
        FIELD_DELIMITER = ','
        SKIP_HEADER = 1
        FIELD_OPTIONALLY_ENCLOSED_BY = '"'
        NULL_IF = ('', 'NULL', 'null')
        EMPTY_FIELD_AS_NULL = TRUE
    """,
    """
    CREATE TABLE IF NOT EXISTS LND.student_enrollment (
        student_id          VARCHAR(20)    NOT NULL,
        u_g                 VARCHAR(1)     NOT NULL,
        gender              VARCHAR(10),
        school              VARCHAR(2)     NOT NULL,
        degtype             VARCHAR(10),
        firstgen            VARCHAR(1),
        pell                VARCHAR(1),
        ethnicmultirace     VARCHAR(5),
        citizen             VARCHAR(2),
        creditenr           VARCHAR(5),
        year_field          VARCHAR(4),
        semester            VARCHAR(10),
        academic_state      VARCHAR(30),
        regstat             VARCHAR(2),
        accumgpa            VARCHAR(10),
        term_code           VARCHAR(6)     NOT NULL,
        loaded_at           TIMESTAMP      DEFAULT CURRENT_TIMESTAMP()
    )
    """,
]


def main():
    if not AWS_KEY_ID or not AWS_SECRET_KEY:
        raise SystemExit("AWS_KEY_ID / AWS_SECRET_KEY must be set in .env")

    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    cursor = conn.cursor()

    try:
        for stmt in DDL_STATEMENTS:
            sql = stmt.format(**SNOWFLAKE_CONFIG)
            cursor.execute(sql)
            print(f"[OK] {sql.strip().splitlines()[0]}...")

        # Stage credentials are bound parameters, never interpolated into
        # a string that gets logged or written to disk.
        # OR REPLACE so re-running this after a bucket/path change in .env
        # actually updates the stage instead of being a no-op.
        cursor.execute(
            """
            CREATE OR REPLACE STAGE LND.rd2_s3_stage
                URL = %(url)s
                CREDENTIALS = (AWS_KEY_ID = %(key_id)s AWS_SECRET_KEY = %(secret_key)s)
                FILE_FORMAT = LND.csv_format
            """,
            {
                "url": f"s3://{S3_BUCKET}/{S3_PATH}",
                "key_id": AWS_KEY_ID,
                "secret_key": AWS_SECRET_KEY,
            },
        )
        print(f"[OK] CREATE OR REPLACE STAGE LND.rd2_s3_stage -> s3://{S3_BUCKET}/{S3_PATH}")

    finally:
        cursor.close()
        conn.close()

    print("[INFO] Snowflake setup complete.")


if __name__ == "__main__":
    main()
