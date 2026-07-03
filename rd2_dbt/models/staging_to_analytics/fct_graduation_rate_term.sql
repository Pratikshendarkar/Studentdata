-- Term-over-term graduation rate, one row per
-- (current_term, degtype, u_g, gender, school, pell).
--
-- Formula mirrors Round 1 ARR style:
--
--   Term Graduation Rate = Students who graduated between prior_term
--                          and current_term / Prior term students x 100
--
-- Where:
--   Prior term students = distinct students enrolled in the immediately
--                         preceding major term (Fall->Spring, Spring->Fall).
--                         Summer/Winter excluded.
--   Graduates           = students whose academic_state = 'Graduated'
--                         between prior_term (inclusive) and current_term
--                         (exclusive) under the same (student_id, u_g, degtype).
--
-- Complements fct_term_retention_rate (same grain, same formula style)
-- by answering "what % of last term's students completed their degree
-- by this term?" rather than "what % came back?"

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
        e.gender,
        e.school,
        e.pell,
        e.academic_state
    from {{ ref('stg_student_enrollment') }} e
    where right(e.term_code, 2) in ('10', '90')

),

-- prior term headcount per dimension group
prior_population as (

    select
        m.current_term,
        e.degtype,
        e.u_g,
        e.gender,
        e.school,
        e.pell,
        count(distinct e.student_id) as prior_students
    from major_terms m
    join enrollment e on e.term_code = m.previous_major_term
    group by m.current_term, e.degtype, e.u_g, e.gender, e.school, e.pell

),

-- students who graduated between prior_term and current_term
graduates as (

    select
        m.current_term,
        e.degtype,
        e.u_g,
        e.gender,
        e.school,
        e.pell,
        count(distinct e.student_id) as graduated_students
    from major_terms m
    join enrollment e on e.term_code = m.previous_major_term
    join {{ ref('stg_student_enrollment') }} g
        on  g.student_id     = e.student_id
        and g.u_g            = e.u_g
        and g.degtype        = e.degtype
        and g.academic_state = 'Graduated'
        and g.term_code      >= m.previous_major_term
        and g.term_code      <  m.current_term
    group by m.current_term, e.degtype, e.u_g, e.gender, e.school, e.pell

)

select
    pp.current_term,
    pp.degtype,
    pp.u_g,
    pp.gender,
    pp.school,
    pp.pell,
    pp.prior_students,
    coalesce(g.graduated_students, 0)                               as graduated_students,
    round(
        100.0 * coalesce(g.graduated_students, 0)
              / nullif(pp.prior_students, 0),
        4
    )                                                               as term_graduation_rate_pct,
    current_timestamp()                                             as loaded_at,
    current_timestamp()                                             as updated_at
from prior_population pp
left join graduates g
    on  g.current_term = pp.current_term
    and g.degtype      = pp.degtype
    and g.u_g          = pp.u_g
    and g.gender       = pp.gender
    and g.school       = pp.school
    and g.pell         = pp.pell
order by pp.current_term, pp.degtype, pp.u_g, pp.gender, pp.school, pp.pell
