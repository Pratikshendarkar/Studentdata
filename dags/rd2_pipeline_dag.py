"""
RD2 Pipeline DAG

S3 (staged file) -> quality_checks (gate) -> LND.student_enrollment ->
dbt run (staging + intermediate + marts) -> dbt test

quality_checks runs FIRST, against the staged S3 file directly (Snowflake
can SELECT off a staged CSV without loading it into a table), so bad data
never lands in LND.student_enrollment at all. s3_to_landing's COPY INTO
only executes if quality_checks exits 0 -- Airflow's task dependency
(quality_checks >> s3_to_landing) enforces this: if quality_checks fails,
s3_to_landing never runs and LND is left untouched.

Schedule: daily at 01:00 UTC.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PIPELINE_HOME = "/opt/airflow/pipeline"
DBT_PROJECT_DIR = f"{PIPELINE_HOME}/rd2_dbt"

default_args = {
    "owner": "rd2_pipeline",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="rd2_pipeline",
    description="S3 -> quality gate -> Snowflake LND -> dbt staging/intermediate/marts -> semantic layer",
    default_args=default_args,
    schedule_interval="0 1 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["rd2", "snowflake", "dbt"],
) as dag:

    quality_checks = BashOperator(
        task_id="quality_checks",
        bash_command=f"python {PIPELINE_HOME}/s3_to_landing/quality_checks.py",
    )

    s3_to_landing = BashOperator(
        task_id="s3_to_landing",
        bash_command=f"python {PIPELINE_HOME}/s3_to_landing/s3_to_landing.py --full-refresh",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            f"dbt run --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROJECT_DIR}"
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f"dbt test --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROJECT_DIR}"
        ),
    )

    quality_checks >> s3_to_landing >> dbt_run >> dbt_test
