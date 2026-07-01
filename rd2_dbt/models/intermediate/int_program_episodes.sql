-- Program episode derivation -- the SOLE place episode grain is resolved.
--
-- A "program episode" is one continuous run of a student in one program,
-- keyed by (student_id, u_g, degtype). This is necessary because student_id
-- alone is not unique to a program: a student can complete a BS and later,
-- separately, enroll in a PHD under the same student_id (verified e.g. for
-- STU54835, STU49262 during data profiling -- regstat=1 "first-time" and
-- academic_state='Graduated' both reset per episode, not per student_id).
--
-- Two-pass structure, deliberately not collapsed into one query:
--   Pass 1 (episode_bounds): resolve each episode's cohort term, last-seen
--     term, first-time flag, and graduation outcome from its own rows only.
--     This pass is fully self-contained -- it never looks at *other*
--     episodes or other students.
--   Pass 2 (retention_lookup): for each finished episode from Pass 1, check
--     whether THAT SAME episode (student_id + u_g + degtype) has a row at
--     the next major term following its cohort term. This is a lookup
--     against the finished episode list, not an inline re-derivation.
--
-- Keeping these as two distinct CTEs (not one combined window/join) is a
-- deliberate fix for a prior bug (case STU33711): a retention check that
-- looked only at the immediate next Fall term without first establishing
-- the episode's own cohort term independently produced a false negative
-- for a student who was, in fact, still actively continuing -- the episode
-- boundary and the forward-term check had been computed in the same pass
-- and gotten out of sync. Resolving episode_bounds completely first
-- prevents that class of bug from recurring.
--
-- "No further records" handling: if an episode has no row at
-- cohort_term -> next_major_term, it is treated as NOT retained for that
-- one-year mark. This is a gap-term-as-attrition rule (same convention
-- Round 1 used for CRT ARR): a true re-enrollment after a gap would start
-- a *new* episode (different min term_code for that student_id/u_g/degtype
-- combination isn't possible by construction -- the gap is captured within
-- this same episode's row set, since all rows sharing the key belong to one
-- episode here). We do not currently split a single (student_id, u_g,
-- degtype) into multiple episodes if there's an internal gap; the dataset's
-- own grain check (zero duplicates at student_id+u_g+degtype+term_code,
-- and regstat=1 appearing at most once per combination) supports treating
-- the full run as one episode. If stop-out/readmit (regstat=3) cases are
-- later found to restart regstat=1 within the same degtype, this should be
-- revisited as a candidate for episode splitting.

with enrollment_with_cohort_flag as (

    -- Flag each row as to whether it IS the episode's cohort (entry) term,
    -- via a window function scoped per (student_id, u_g, degtype). This is
    -- resolved before any aggregation, so the subsequent GROUP BY only has
    -- to pick out the already-flagged cohort-term row's attributes.
    select
        *,
        case
            when term_code = min(term_code) over (partition by student_id, u_g, degtype)
            then 1 else 0
        end as is_cohort_term_row
    from {{ ref('stg_student_enrollment') }}

),

episode_bounds as (

    select
        student_id,
        u_g,
        degtype,
        min(term_code) as cohort_term,
        max(term_code) as last_term,
        max(case when regstat_code = '1' then 1 else 0 end) as is_first_time_cohort,
        max(case when academic_state = 'Graduated' then 1 else 0 end) as graduated_flag,
        min(case when academic_state = 'Graduated' then term_code end) as graduation_term,
        -- representative attributes for the episode, taken at the cohort term
        max(case when is_cohort_term_row = 1 then school end) as cohort_school,
        max(case when is_cohort_term_row = 1 then pell end) as cohort_pell,
        max(case when is_cohort_term_row = 1 then firstgen end) as cohort_firstgen,
        max(case when is_cohort_term_row = 1 then gender end) as cohort_gender,
        max(case when is_cohort_term_row = 1 then term_year end) as cohort_year,
        max(case when is_cohort_term_row = 1 then term_season end) as cohort_season
    from enrollment_with_cohort_flag
    group by student_id, u_g, degtype

),

episode_bounds_keyed as (

    select
        *,
        student_id || '-' || u_g || '-' || degtype || '-' || cohort_term as program_episode_id
    from episode_bounds

),

-- Pre-compute the actual check-term values per distinct cohort_term.
-- Snowflake does not support correlated scalar subqueries inside CASE WHEN,
-- so we resolve these as a plain join before the retention_lookup CTE.
-- one_year_check_term  = cohort_term +2 major terms (1 year out)
-- two_year_check_term  = cohort_term +4 major terms (2 years out)
check_terms as (

    select
        c1.current_term                     as cohort_term,
        c2.next_major_term                  as one_year_check_term,
        c4.next_major_term                  as two_year_check_term
    from {{ ref('stg_term_calendar') }} c1
    join {{ ref('stg_term_calendar') }} c2 on c2.current_term = c1.next_major_term
    join {{ ref('stg_term_calendar') }} c3 on c3.current_term = c2.next_major_term
    join {{ ref('stg_term_calendar') }} c4 on c4.current_term = c3.next_major_term

),

retention_lookup as (

    -- Pass 2: forward-term persistence check against the finished episode
    -- list from Pass 1. Looks up the SAME episode key at 1 year out
    -- (2 major-term hops) and 2 years out (4 major-term hops).
    -- Each hop chains through stg_term_calendar so Summer/Winter terms
    -- are correctly skipped -- only Fall/Spring count as major terms.
    --
    -- graduated_before_one_year_mark / graduated_before_two_year_mark:
    -- a student who completed their program before the retention check term
    -- is a successful early completer, not an attrition, and should be
    -- excluded from the retention denominator in the downstream mart.
    -- Key for Master's (G): a 2-yr MS student finishing in year 1 is a
    -- success. In the current dataset, 0 episodes trigger this exclusion,
    -- but the logic is correct by construction for future data.
    select
        eb.program_episode_id,
        case when exists (
            select 1
            from {{ ref('stg_student_enrollment') }} e1
            join {{ ref('stg_term_calendar') }} c1
                on c1.current_term = eb.cohort_term
            where e1.student_id = eb.student_id
              and e1.u_g = eb.u_g
              and e1.degtype = eb.degtype
              and e1.term_code = c1.next_major_term
        ) then 1 else 0 end                                              as enrolled_next_term,

        -- 1-year retention: enrolled at cohort_term +2 major terms
        case when exists (
            select 1
            from {{ ref('stg_student_enrollment') }} e2
            join {{ ref('stg_term_calendar') }} c1
                on c1.current_term = eb.cohort_term
            join {{ ref('stg_term_calendar') }} c2
                on c2.current_term = c1.next_major_term
            where e2.student_id = eb.student_id
              and e2.u_g = eb.u_g
              and e2.degtype = eb.degtype
              and e2.term_code = c2.next_major_term
        ) then 1 else 0 end                                              as retained_one_year,

        case when eb.graduation_term is not null
              and eb.graduation_term <= ct.one_year_check_term
        then 1 else 0 end                                                as graduated_before_one_year_mark,

        -- 2-year retention: enrolled at cohort_term +4 major terms
        case when exists (
            select 1
            from {{ ref('stg_student_enrollment') }} e3
            join {{ ref('stg_term_calendar') }} c1
                on c1.current_term = eb.cohort_term
            join {{ ref('stg_term_calendar') }} c2
                on c2.current_term = c1.next_major_term
            join {{ ref('stg_term_calendar') }} c3
                on c3.current_term = c2.next_major_term
            join {{ ref('stg_term_calendar') }} c4
                on c4.current_term = c3.next_major_term
            where e3.student_id = eb.student_id
              and e3.u_g = eb.u_g
              and e3.degtype = eb.degtype
              and e3.term_code = c4.next_major_term
        ) then 1 else 0 end                                              as retained_two_year,

        case when eb.graduation_term is not null
              and eb.graduation_term <= ct.two_year_check_term
        then 1 else 0 end                                                as graduated_before_two_year_mark

    from episode_bounds_keyed eb
    left join check_terms ct on ct.cohort_term = eb.cohort_term

)

select
    eb.program_episode_id,
    eb.student_id,
    eb.u_g,
    eb.degtype,
    eb.cohort_term,
    eb.cohort_year,
    eb.cohort_season,
    eb.cohort_school,
    eb.cohort_pell,
    eb.cohort_firstgen,
    eb.cohort_gender,
    eb.last_term,
    eb.is_first_time_cohort,
    eb.graduated_flag,
    eb.graduation_term,
    rl.enrolled_next_term,
    rl.retained_one_year,
    rl.retained_two_year,
    rl.graduated_before_one_year_mark,
    rl.graduated_before_two_year_mark,
    current_timestamp() as loaded_at,
    current_timestamp() as updated_at
from episode_bounds_keyed eb
join retention_lookup rl
    on rl.program_episode_id = eb.program_episode_id
