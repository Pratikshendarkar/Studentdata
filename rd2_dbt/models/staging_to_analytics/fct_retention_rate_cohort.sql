-- 1-year and 2-year retention rate, pre-aggregated across degtype, u_g,
-- gender, school, pell, and cohort_year -- one row per unique combination
-- of those six dimensions. Replaces fct_first_year_retention_by_school
-- (school-only grain): same retention logic, same matured-cohort/early-
-- completer handling, generalized to all program levels (U/G/D) and all
-- six dimensions so a BI tool can filter/group on any subset. Answers the
-- brief's "first-year retention rate for undergraduate students in the
-- College of Engineering" (u_g='U', school='EN') and generalizes it.
--
-- Reads retained_one_year / retained_two_year directly from
-- int_program_episodes -- does NOT recompute the forward-term lookup
-- here. Episode derivation and the retention check both live in
-- int_program_episodes; this model only aggregates the already-resolved
-- flags (see int_program_episodes.sql header for why that separation matters).
--
-- GRADUATION / TRANSFER HANDLING:
-- Early graduates (completed before the retention check term) are excluded
-- from the denominator via graduated_before_one_year_mark /
-- graduated_before_two_year_mark (computed once in int_program_episodes).
-- Key for Master's (G): a student completing a 2-yr MS in year 1 is a
-- successful completer, not an attrition -- excluded here, not penalised.
-- In the current dataset, 0 episodes trigger this exclusion at any level,
-- but the logic is correct by construction for future data.
--
-- "Transfer out" is not a trackable state in this dataset -- academic_state
-- only has Enrolled/Graduated/Maintaining Registration. A student who
-- transferred out simply stops appearing in the data, which
-- retained_one_year/retained_two_year = 0 already captures correctly as
-- not-retained. No explicit exclusion is needed.
--
-- MATURED-COHORT FILTERS ARE BAKED IN HERE for both metrics:
--   1-year retention: cohort needs 1 year of data elapsed (cohort_term + 100)
--   2-year retention: cohort needs 2 years of data elapsed (cohort_term + 200)
-- term_code is YYYYTT, and next_major_term alternates Fall<->Spring, so one
-- full year later in the SAME season is cohort_term + 100 (e.g. Fall 2020
-- 202090 -> Fall 2021 202190 = +100; Spring 2020 202010 -> Spring 2021
-- 202110 = +100) -- not +200, which is actually 2 years later. This mirrors
-- the 2-hop/4-hop next_major_term chaining already used correctly in
-- int_program_episodes.retention_lookup (2 major-term hops = 1 year).
-- Both cutoffs computed dynamically off MAX(cohort_term) in the data so
-- they stay correct as new terms land. Without these, recent cohorts show
-- false near-0% rates purely because their check term hasn't occurred yet.
-- A cohort can be mature for 1-year but not 2-year -- this is expected
-- and correct; the two metrics have independent denominators.

with data_bounds as (

    select max(cohort_term) as max_term_in_data
    from {{ ref('int_program_episodes') }}

),

episodes as (

    select
        pe.*,
        case
            when cast(pe.cohort_term as integer) + 100 <= cast(d.max_term_in_data as integer)
            then 1 else 0
        end as is_mature_for_one_year,
        case
            when cast(pe.cohort_term as integer) + 200 <= cast(d.max_term_in_data as integer)
            then 1 else 0
        end as is_mature_for_two_year
    from {{ ref('int_program_episodes') }} pe
    cross join data_bounds d
    where is_first_time_cohort = 1

)

select
    degtype,
    u_g,
    cohort_gender as gender,
    cohort_school as school,
    cohort_pell as pell,
    cohort_year,

    -- 1-year retention (matured cohorts only, early completers excluded from denominator)
    -- Denominator: matured episodes minus those who graduated before the 1-year mark
    -- Numerator  : episodes that are enrolled at the 1-year check term
    sum(case when is_mature_for_one_year = 1
              and graduated_before_one_year_mark = 0
             then 1 else 0 end)                                                      as one_year_eligible_cohort_size,
    sum(case when is_mature_for_one_year = 1
              and graduated_before_one_year_mark = 0
             then retained_one_year else 0 end)                                      as one_year_retained_count,
    round(
        100.0 * sum(case when is_mature_for_one_year = 1
                          and graduated_before_one_year_mark = 0
                         then retained_one_year else 0 end)
              / nullif(
                    sum(case when is_mature_for_one_year = 1
                              and graduated_before_one_year_mark = 0
                             then 1 else 0 end), 0),
        4
    )                                                                                as first_year_retention_rate_pct,

    -- 2-year retention (matured cohorts only, early completers excluded from denominator)
    sum(case when is_mature_for_two_year = 1
              and graduated_before_two_year_mark = 0
             then 1 else 0 end)                                                      as two_year_eligible_cohort_size,
    sum(case when is_mature_for_two_year = 1
              and graduated_before_two_year_mark = 0
             then retained_two_year else 0 end)                                      as two_year_retained_count,
    round(
        100.0 * sum(case when is_mature_for_two_year = 1
                          and graduated_before_two_year_mark = 0
                         then retained_two_year else 0 end)
              / nullif(
                    sum(case when is_mature_for_two_year = 1
                              and graduated_before_two_year_mark = 0
                             then 1 else 0 end), 0),
        4
    )                                                                                as second_year_retention_rate_pct,

    current_timestamp() as loaded_at,
    current_timestamp() as updated_at
from episodes
group by degtype, u_g, cohort_gender, cohort_school, cohort_pell, cohort_year
order by degtype, u_g, gender, school, pell, cohort_year
