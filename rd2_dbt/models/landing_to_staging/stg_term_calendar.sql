-- Major terms (Fall/Spring) mapped to their immediately following major
-- term. Generalizes Round 1's stg_major_terms (which mapped to the
-- *preceding* major term for the ARR formula) -- here we need the
-- *next* major term to check forward, one year out, for retention.
--
-- Only Fall (90) and Spring (10) are treated as major terms: Summer/Winter
-- enrollment is not used for cohort sequencing, and no Winter (95) rows
-- are actually present in the source data despite being a defined code.

select distinct
    term_code as current_term,
    {{ next_major_term('term_code') }} as next_major_term,
    current_timestamp() as loaded_at,
    current_timestamp() as updated_at
from {{ ref('stg_student_enrollment') }}
where right(term_code, 2) in ('10', '90')
