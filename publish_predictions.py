"""
publish_predictions.py -- Publish outputs/final_predicted_output.xlsx to S3 and Snowflake.

Uploads the scored predictions to:
  - s3://<S3_BUCKET>/<S3_PREDICTIONS_PATH>final_predicted_output.xlsx
  - Snowflake REPORT.PREDICTION_MODEL (truncate + load)

Usage:
    python publish_predictions.py
"""

import os
from pathlib import Path

import boto3
import pandas as pd
import snowflake.connector
from dotenv import load_dotenv
from snowflake.connector.pandas_tools import write_pandas

load_dotenv(Path(__file__).parent / ".env")

OUTPUT_DIR = Path(__file__).parent / os.getenv("OUTPUT_DIR", "outputs")
PREDICTIONS_FILE = OUTPUT_DIR / "final_predicted_output.xlsx"

S3_BUCKET = os.getenv("S3_BUCKET")
S3_PREDICTIONS_PATH = os.getenv("S3_PREDICTIONS_PATH", "RD2_Predictions/")

SNOWFLAKE_CONFIG = {
    "user": os.getenv("SNOWFLAKE_USER"),
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "account": os.getenv("SNOWFLAKE_ACCOUNT"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
    "database": os.getenv("SNOWFLAKE_DATABASE"),
    "role": os.getenv("SNOWFLAKE_ROLE"),
    "schema": os.getenv("SNOWFLAKE_ANALYTICS_SCHEMA", "REPORT"),
}

TABLE = "PREDICTION_MODEL"

# Matches REPORT.PREDICTION_MODEL column order exactly (excludes audit columns,
# which default in Snowflake: loaded_at, updated_at, updated_by).
TABLE_COLUMNS = [
    "student_id", "u_g", "gender", "school", "degtype", "firstgen", "pell",
    "ethnicmultirace", "citizen", "creditenr", "year", "semester",
    "academic_state", "regstat", "accumgpa", "term_code", "term_type",
    "term_year", "dropout_probability", "risk_flag",
]


def upload_to_s3():
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_KEY"),
        region_name=os.getenv("AWS_REGION"),
    )
    key = f"{S3_PREDICTIONS_PATH}{PREDICTIONS_FILE.name}"
    s3.upload_file(str(PREDICTIONS_FILE), S3_BUCKET, key)
    print(f"[S3] Uploaded to s3://{S3_BUCKET}/{key}")


def load_to_snowflake(df: pd.DataFrame):
    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    try:
        cursor = conn.cursor()
        cursor.execute(f"TRUNCATE TABLE {TABLE}")
        print(f"[Snowflake] Truncated {SNOWFLAKE_CONFIG['schema']}.{TABLE}")

        # write_pandas expects uppercase column names to match unquoted Snowflake identifiers
        df_upload = df[TABLE_COLUMNS].copy()
        df_upload.columns = [c.upper() for c in df_upload.columns]

        success, n_chunks, n_rows, _ = write_pandas(
            conn, df_upload, table_name=TABLE, schema=SNOWFLAKE_CONFIG["schema"]
        )
        print(f"[Snowflake] Loaded {n_rows:,} rows into {SNOWFLAKE_CONFIG['schema']}.{TABLE}")
    finally:
        conn.close()


def main():
    df = pd.read_excel(PREDICTIONS_FILE)
    print(f"[INFO] Loaded {len(df):,} rows from {PREDICTIONS_FILE}")

    # S3 upload disabled until awsarr IAM user has s3:PutObject on
    # njitstudentdata/RD2_Predictions/* -- re-enable once that's granted.
    # upload_to_s3()
    load_to_snowflake(df)


if __name__ == "__main__":
    main()
