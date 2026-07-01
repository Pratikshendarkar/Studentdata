-- Descriptive dimension: one row per program episode with cohort
-- attributes only. Metric flags (retained_one_year, retained_two_year,
-- graduated_flag) are intentionally excluded here -- they carry implicit
-- denominator logic (matured-cohort filter, early-completer exclusions)
-- that a BI tool cannot know about if the flags are exposed as raw 0/1
-- columns. A dashboard builder seeing SUM(retained_one_year) / COUNT(*)
-- would produce a wrong retention rate because immature cohorts and early
-- completers would not be excluded. Those metrics live in fct_retention_rate
-- and fct_graduation_rate, where the correct denominators are already
-- enforced. This table is for filtering/slicing only (who/what/when),
-- not for computing rates directly.

select
    program_episode_id,
    student_id,
    u_g,
    degtype,
    cohort_term,
    cohort_year,
    cohort_season,
    cohort_school       as school,
    cohort_pell         as pell,
    cohort_firstgen     as firstgen,
    cohort_gender       as gender,
    last_term,
    is_first_time_cohort,
    current_timestamp() as loaded_at,
    current_timestamp() as updated_at
from {{ ref('int_program_episodes') }}
