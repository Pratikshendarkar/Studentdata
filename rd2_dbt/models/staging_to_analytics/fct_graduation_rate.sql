-- Graduation rate, pre-aggregated across degtype, u_g, gender, school,
-- pell, and cohort_year -- one row per unique combination of those six
-- dimensions, with cohort_size/graduated_count/graduation_rate_pct
-- computed directly. Answers the brief's Pell graduation-rate trend
-- question and generalizes it: a BI tool can filter/group on any subset
-- of these six dimensions (e.g. just school, just gender, school+pell,
-- all six) since they're all present at this grain.
--
-- MATURED-COHORT FILTER IS BAKED IN HERE, not left as a query-time/
-- dashboard-time filter (same principle as fct_first_year_retention_by_school).
-- Cohorts whose entry term is too recent to have had a realistic chance to
-- graduate are excluded from this model's own output. The cutoff is
-- computed dynamically off MAX(cohort_term) actually present in the data,
-- not a hardcoded date. Without this, recent cohorts appear to have
-- "collapsing" graduation rates purely because they haven't had time to
-- graduate yet -- a previously-seen false artifact, not a real trend.
--
-- Maturity window: a program is considered to have had a fair chance to
-- graduate once (max_term_in_data - cohort_term) >= the typical program
-- length for that level. Using conservative, level-specific windows:
--   U (undergrad): 4 years   G (master's): 2 years   D (doctoral): 5 years
-- expressed in term-code arithmetic (each year = 100 in YYYYTT terms, e.g.
-- 202010 -> 202410 is 4 years later).

with data_bounds as (

    select max(cohort_term) as max_term_in_data
    from {{ ref('int_program_episodes') }}

),

maturity_windows as (

    select
        pe.*,
        case pe.u_g
            when 'U' then 400
            when 'G' then 200
            when 'D' then 500
        end as maturity_window_terms
    from {{ ref('int_program_episodes') }} pe

),

matured_episodes as (

    select m.*
    from maturity_windows m
    cross join data_bounds d
    where cast(m.cohort_term as integer) + m.maturity_window_terms <= cast(d.max_term_in_data as integer)

)

select
    degtype,
    u_g,
    cohort_gender as gender,
    cohort_school as school,
    cohort_pell as pell,
    cohort_year,
    count(*) as cohort_size,
    sum(graduated_flag) as graduated_count,
    round(100.0 * sum(graduated_flag) / nullif(count(*), 0), 4) as graduation_rate_pct,
    current_timestamp() as loaded_at,
    current_timestamp() as updated_at
from matured_episodes
group by degtype, u_g, cohort_gender, cohort_school, cohort_pell, cohort_year
order by degtype, u_g, gender, school, pell, cohort_year
