-- Student headcount by semester, program level, and Pell eligibility.
-- One row per (term_code, u_g, pell) combination -- no u_g filter baked
-- in, so a BI tool can filter to any level (U/G/D) or see all levels
-- side-by-side. Answers the brief's question "What is the number of
-- Pell Grant-eligible students by semester in Master's level programs?"
-- by filtering u_g = 'G' in the dashboard, and generalizes to the same
-- question for undergrads or doctoral students without a new model.
--
-- No episode/cohort dependency -- headcount is a per-term enrollment
-- snapshot, so this reads straight from stg_student_enrollment.

select
    term_code,
    term_year,
    term_season,
    u_g,
    school,
    pell,
    count(distinct student_id) as student_count,
    current_timestamp() as loaded_at,
    current_timestamp() as updated_at
from {{ ref('stg_student_enrollment') }}
group by term_code, term_year, term_season, u_g, school, pell
order by term_code, u_g, school, pell
