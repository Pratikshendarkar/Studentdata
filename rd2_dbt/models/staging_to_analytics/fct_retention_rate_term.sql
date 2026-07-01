-- Term-over-term retention rate, one row per (current_term, degtype,
-- u_g, school). Answers "what is the retention rate for each term?" --
-- different from fct_cohort_retention_rate which is cohort-based
-- (entry year -> year 1/year 2 checkpoints).
--
-- Formula mirrors Round 1 ARR (fct_adjusted_retention_rate.sql in ARR_Calc):
--
--   Adjusted_Retention_Rate = Continuing / (Prior Term Students - Graduates) x 100
--
-- Where:
--   Prior Term Students = distinct students enrolled in the immediately
--                         preceding major term (Fall->Spring, Spring->Fall).
--                         Summer/Winter excluded -- gap term = New.
--   Graduates           = students who graduated between prior_term and
--                         current_term. Excluded from denominator because
--                         they are successful completers, not attrition.
--   Continuing Students = students present in BOTH prior and current term
--                         under the same (student_id, u_g, degtype).

with major_terms as (

    select distinct
        term_code as current_term,
        case
            when right(term_code, 2) = '10'
                then concat(cast(cast(left(term_code, 4) as int) - 1 as varchar), '90')
            when right(term_code, 2) = '90'
                then concat(left(term_code, 4), '10')
        end as previous_major_term
    from {{ ref('stg_student_enrollment') }}
    where right(term_code, 2) in ('10', '90')

),

enrollment as (

    select
        e.student_id,
        e.term_code,
        e.u_g,
        e.degtype,
        e.school,
        e.academic_state
    from {{ ref('stg_student_enrollment') }} e
    where right(e.term_code, 2) in ('10', '90')

),

prior_population as (

    select
        m.current_term,
        e.degtype,
        e.u_g,
        e.school,
        count(distinct e.student_id) as prior_students
    from major_terms m
    join enrollment e on e.term_code = m.previous_major_term
    group by m.current_term, e.degtype, e.u_g, e.school

),

grad_exclusions as (

    select
        m.current_term,
        e.degtype,
        e.u_g,
        e.school,
        count(distinct e.student_id) as graduates_excluded
    from major_terms m
    join enrollment e on e.term_code = m.previous_major_term
    join {{ ref('stg_student_enrollment') }} g
        on  g.student_id      = e.student_id
        and g.u_g             = e.u_g
        and g.degtype         = e.degtype
        and g.academic_state  = 'Graduated'
        and g.term_code       >= m.previous_major_term
        and g.term_code       <  m.current_term
    group by m.current_term, e.degtype, e.u_g, e.school

),

eligible_prior as (

    select
        pp.current_term,
        pp.degtype,
        pp.u_g,
        pp.school,
        pp.prior_students,
        coalesce(ge.graduates_excluded, 0)                      as graduates_excluded,
        pp.prior_students - coalesce(ge.graduates_excluded, 0)  as eligible_prior_students
    from prior_population pp
    left join grad_exclusions ge
        on  ge.current_term = pp.current_term
        and ge.degtype      = pp.degtype
        and ge.u_g          = pp.u_g
        and ge.school       = pp.school

),

continuing as (

    select
        m.current_term,
        e_prior.degtype,
        e_prior.u_g,
        e_prior.school,
        count(distinct e_prior.student_id) as continuing_students
    from major_terms m
    join enrollment e_prior on e_prior.term_code = m.previous_major_term
    join enrollment e_curr
        on  e_curr.student_id = e_prior.student_id
        and e_curr.u_g        = e_prior.u_g
        and e_curr.degtype    = e_prior.degtype
        and e_curr.term_code  = m.current_term
    group by m.current_term, e_prior.degtype, e_prior.u_g, e_prior.school

)

select
    ep.current_term,
    ep.degtype,
    ep.u_g,
    ep.school,
    ep.prior_students,
    ep.graduates_excluded,
    ep.eligible_prior_students,
    coalesce(c.continuing_students, 0)                              as continuing_students,
    round(
        100.0 * coalesce(c.continuing_students, 0)
              / nullif(ep.eligible_prior_students, 0),
        4
    )                                                               as adjusted_retention_rate,
    round(
        100.0 * (ep.eligible_prior_students - coalesce(c.continuing_students, 0))
              / nullif(ep.eligible_prior_students, 0),
        4
    )                                                               as attrition_rate_pct,
    current_timestamp()                                             as loaded_at,
    current_timestamp()                                             as updated_at
from eligible_prior ep
left join continuing c
    on  c.current_term = ep.current_term
    and c.degtype      = ep.degtype
    and c.u_g          = ep.u_g
    and c.school       = ep.school
order by ep.current_term, ep.degtype, ep.u_g, ep.school