-- Required by dbt's semantic layer (MetricFlow) for time-based joins.
-- RD2 metrics are grouped by cohort_year/term_code (categorical/time
-- dimensions derived in the marts), but MetricFlow requires this model
-- to exist in every project. Spans 2015-01-01 through the dataset's
-- 2026 horizon plus headroom.

{{
    config(
        materialized = 'table',
    )
}}

select dateadd(day, seq4(), '2015-01-01'::date) as date_day
from table(generator(rowcount => 5479))
