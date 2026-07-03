-- One row per program episode per term -- base fact table for headcount,
-- filter-driven dashboard queries (e.g. "Pell-eligible Master's students
-- by semester"). Carries the episode key so dashboard tools can join back
-- to dim_program_episode for cohort-level attributes when needed.

select
    e.student_id,
    e.u_g,
    e.degtype,
    e.term_code,
    e.term_year,
    e.term_season,
    e.school,
    e.school_name,
    e.pell,
    e.firstgen,
    e.ethnicity_description,
    e.citizen_description,
    e.creditenr,
    e.accumgpa,
    e.academic_state,
    e.regstat_description,
    pe.program_episode_id,
    pe.cohort_term,
    pe.is_first_time_cohort,
    current_timestamp() as loaded_at,
    current_timestamp() as updated_at,
    current_user()      as updated_by
from {{ ref('stg_student_enrollment') }} e
join {{ ref('int_program_episodes') }} pe
    on pe.student_id = e.student_id
   and pe.u_g = e.u_g
   and pe.degtype = e.degtype
