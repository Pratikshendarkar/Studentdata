-- Cleaned, typed, decoded version of LND.student_enrollment.
--
-- Grain: one row per (student_id, u_g, degtype, term_code) -- verified
-- against the full 265,668-row dataset with zero duplicates at this
-- combination. student_id alone is NOT unique to a program: a student can
-- carry a completed BS episode and a separate, later PHD episode under the
-- same student_id (e.g. STU54835). Episode-level grain is resolved in
-- int_program_episodes, not here.
--
-- pell and firstgen arrive blank for ~20%/~19% of rows respectively (not
-- just Y/N). Blanks are decoded to 'Unknown' rather than coalesced to 'N',
-- so downstream Pell-eligibility breakdowns don't silently understate the
-- eligible population.

with source as (

    select * from {{ source('landing', 'student_enrollment') }}

)

select
    student_id,
    u_g,
    gender,
    school,
    sc.school_name,
    degtype,
    case when nullif(trim(firstgen), '') is null then 'Unknown' else firstgen end as firstgen,
    case when nullif(trim(pell), '') is null then 'Unknown' else pell end as pell,
    ethnicmultirace as ethnicity_code,
    eth.ethnicity_description,
    citizen as citizen_code,
    cz.citizen_description,
    cast(creditenr as integer) as creditenr,
    cast(accumgpa as decimal(4,2)) as accumgpa,
    academic_state,
    regstat as regstat_code,
    rs.regstat_description,
    term_code,
    {{ term_year('term_code') }} as term_year,
    {{ term_season('term_code') }} as term_season,
    current_timestamp() as loaded_at,
    current_timestamp() as updated_at
from source s
left join {{ ref('seed_school_codes') }} sc
    on s.school = sc.school_code
left join {{ ref('seed_citizen_codes') }} cz
    on s.citizen = cast(cz.citizen_code as varchar)
left join {{ ref('seed_regstat_codes') }} rs
    on s.regstat = cast(rs.regstat_code as varchar)
left join {{ ref('seed_ethnicity_codes') }} eth
    on s.ethnicmultirace = cast(eth.ethnicity_code as varchar)
