-- RD2_PIPELINE: S3 STAGE SETUP
--
-- Uses static AWS credentials on the stage (matches Round 1's working
-- pattern). &AWS_KEY_ID / &AWS_SECRET_KEY are dbt/SnowSQL variables --
-- DO NOT hardcode real key values in this file, since unlike .env it is
-- not gitignored. Pass them at execution time, e.g.:
--   snowsql -f snowflake_setup.sql -D AWS_KEY_ID=... -D AWS_SECRET_KEY=...
-- or run setup_landing_table() in s3_to_landing.py, which reads the same
-- values from .env and issues the CREATE STAGE statement directly via the
-- Snowflake Python connector (no key ever touches a file on disk).

USE DATABASE NJIT;

CREATE SCHEMA IF NOT EXISTS LND;
CREATE SCHEMA IF NOT EXISTS STG;
CREATE SCHEMA IF NOT EXISTS REPORT;

CREATE WAREHOUSE IF NOT EXISTS NJIT_WH
    WAREHOUSE_SIZE = 'MEDIUM'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE;

CREATE FILE FORMAT IF NOT EXISTS LND.csv_format
    TYPE = 'CSV'
    FIELD_DELIMITER = ','
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF = ('', 'NULL', 'null')
    EMPTY_FIELD_AS_NULL = TRUE;

CREATE OR REPLACE STAGE LND.rd2_s3_stage
    URL = 's3://njitstudentdata/RD2_Landing/'
    CREDENTIALS = (AWS_KEY_ID = '&AWS_KEY_ID' AWS_SECRET_KEY = '&AWS_SECRET_KEY')
    FILE_FORMAT = LND.csv_format;

-- LND: source table (incremental, 1:1 with randomdata.csv)
CREATE TABLE IF NOT EXISTS LND.student_enrollment (
    student_id          VARCHAR(20)    NOT NULL,
    u_g                 VARCHAR(1)     NOT NULL,
    gender               VARCHAR(10),
    school               VARCHAR(2)     NOT NULL,
    degtype              VARCHAR(10),
    firstgen             VARCHAR(1),
    pell                 VARCHAR(1),
    ethnicmultirace       VARCHAR(5),
    citizen              VARCHAR(2),
    creditenr            VARCHAR(5),
    year_field           VARCHAR(4),
    semester             VARCHAR(10),
    academic_state        VARCHAR(30),
    regstat              VARCHAR(2),
    accumgpa             VARCHAR(10),
    term_code            VARCHAR(6)     NOT NULL,
    loaded_at            TIMESTAMP      DEFAULT CURRENT_TIMESTAMP()
);
