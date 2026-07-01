"""
Pre-ingest data quality checks on the staged S3 file for the RD2 pipeline.

Runs BEFORE the file is loaded into LND.student_enrollment: queries the
file directly off the Snowflake stage (Snowflake can SELECT from a staged
CSV without loading it into a table first) so bad data never lands in
LND at all. Exits with non-zero status if any critical check fails, which
gates s3_to_landing.py's COPY INTO in the Airflow DAG -- the DAG only
proceeds to load if this script passes.

Mirrors the Round 1 ARR_Calc quality_checks.py structure, adapted to the
fields and accepted values actually present in randomdata.csv (verified
by profiling, not the brief alone -- e.g. pell has blank values in
addition to Y/N, and years start at 2015 not 2016).
"""

import os
import sys

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

STAGE_FILE = "@LND.rd2_s3_stage/randomdata.csv (FILE_FORMAT => 'LND.csv_format')"

PASS = "PASS"
FAIL = "FAIL"


def get_connection():
    return snowflake.connector.connect(**SNOWFLAKE_CONFIG)


def check(cursor, results, name, query, expect_zero=True):
    cursor.execute(query)
    value = cursor.fetchone()[0]
    ok = (value == 0) if expect_zero else (value > 0)
    status = PASS if ok else FAIL
    results.append((status, name, value))


def run_checks(cursor):
    results = []

    # Row count -- file must not be empty before anything downstream runs
    check(
        cursor, results, "staged file has rows",
        f"SELECT COUNT(*) FROM {STAGE_FILE}",
        expect_zero=False,
    )

    # Null checks on key columns ($1=student_id, $2=u_g, $5=degtype,
    # $4=school, $16=term_code per the data dictionary column order)
    check(
        cursor, results, "no nulls in key columns",
        f"""
        SELECT COUNT(*) FROM {STAGE_FILE}
        WHERE $1 IS NULL OR $2 IS NULL OR $5 IS NULL
           OR $4 IS NULL OR $16 IS NULL
        """,
    )

    # term_code format: 6 chars, last 2 digits a valid term suffix
    check(
        cursor, results, "term_code valid format",
        f"""
        SELECT COUNT(*) FROM {STAGE_FILE}
        WHERE LENGTH($16) != 6
           OR RIGHT($16, 2) NOT IN ('10', '50', '90', '95')
           OR NOT REGEXP_LIKE($16, '^[0-9]{{6}}$')
        """,
    )

    # Duplicate rows at the verified grain: (student_id, u_g, degtype, term_code)
    check(
        cursor, results, "no duplicate rows at (student_id, u_g, degtype, term_code) grain",
        f"""
        SELECT COUNT(*) FROM (
            SELECT $1, $2, $5, $16, COUNT(*) c
            FROM {STAGE_FILE}
            GROUP BY 1, 2, 3, 4
            HAVING COUNT(*) > 1
        )
        """,
    )

    # Accepted values
    check(
        cursor, results, "u_g in (U, G, D)",
        f"SELECT COUNT(*) FROM {STAGE_FILE} WHERE $2 NOT IN ('U','G','D')",
    )
    check(
        cursor, results, "school in (AD, CC, EN, SL, SM)",
        f"SELECT COUNT(*) FROM {STAGE_FILE} WHERE $4 NOT IN ('AD','CC','EN','SL','SM')",
    )
    check(
        cursor, results, "pell in (Y, N, '') -- blank is a known data state, decoded to Unknown in STG",
        f"SELECT COUNT(*) FROM {STAGE_FILE} WHERE $7 NOT IN ('Y','N','') AND $7 IS NOT NULL",
    )
    check(
        cursor, results, "regstat in (1, 2, 3, 4)",
        f"SELECT COUNT(*) FROM {STAGE_FILE} WHERE $14 NOT IN ('1','2','3','4')",
    )
    check(
        cursor, results, "academic_state in (Enrolled, Graduated, Maintaining Registration)",
        f"""
        SELECT COUNT(*) FROM {STAGE_FILE}
        WHERE $13 NOT IN ('Enrolled', 'Graduated', 'Maintaining Registration')
        """,
    )

    return results


def main():
    conn = get_connection()
    cursor = conn.cursor()

    try:
        results = run_checks(cursor)
    finally:
        cursor.close()
        conn.close()

    print("---- Pre-Ingest Data Quality Check Results (staged file) ----")
    failed = 0
    for status, name, value in results:
        print(f"  [{status}] {name} (value={value})")
        if status == FAIL:
            failed += 1

    print(f"\n{len(results) - failed} passed / {failed} failed out of {len(results)} checks")

    if failed > 0:
        print("\n[BLOCKED] Quality checks failed -- file will NOT be loaded into LND.student_enrollment.")
        sys.exit(1)

    print("\n[OK] Quality checks passed -- safe to load into LND.student_enrollment.")


if __name__ == "__main__":
    main()
