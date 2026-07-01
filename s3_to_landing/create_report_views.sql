-- Create views in REPORT schema as stable Power BI source tables.
-- Views sit on top of the dbt-managed tables so Power BI connections
-- never break when the underlying table is rebuilt by a dbt run.

USE DATABASE NJIT;

-- Drop stale table that has no corresponding dbt model
DROP TABLE IF EXISTS REPORT.fct_attrition_rate;

-- Views
CREATE OR REPLACE VIEW REPORT.vw_dim_program_episode AS
    SELECT * FROM REPORT.dim_program_episode;

CREATE OR REPLACE VIEW REPORT.vw_fct_enrollment_term AS
    SELECT * FROM REPORT.fct_enrollment_term;

CREATE OR REPLACE VIEW REPORT.vw_fct_enrollment_by_semester_level AS
    SELECT * FROM REPORT.fct_enrollment_by_semester_level;

CREATE OR REPLACE VIEW REPORT.vw_fct_graduation_rate AS
    SELECT * FROM REPORT.fct_graduation_rate;

CREATE OR REPLACE VIEW REPORT.vw_fct_retention_rate_cohort AS
    SELECT * FROM REPORT.fct_retention_rate_cohort;

CREATE OR REPLACE VIEW REPORT.vw_fct_graduation_rate_term AS
    SELECT * FROM REPORT.fct_graduation_rate_term;

CREATE OR REPLACE VIEW REPORT.vw_fct_retention_rate_term AS
    SELECT * FROM REPORT.fct_retention_rate_term;

CREATE OR REPLACE VIEW REPORT.vw_stg_student_enrollment AS
    SELECT * FROM STG.stg_student_enrollment;
