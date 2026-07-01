{% macro term_year(term_code_column) -%}
    cast(left({{ term_code_column }}, 4) as int)
{%- endmacro %}

{% macro term_season(term_code_column) -%}
    case right({{ term_code_column }}, 2)
        when '10' then 'Spring'
        when '50' then 'Summer'
        when '90' then 'Fall'
        when '95' then 'Winter'
    end
{%- endmacro %}

{#
    Major terms are Fall (90) and Spring (10) only -- Summer/Winter are not
    used for cohort/retention sequencing (mirrors Round 1's stg_major_terms).
    next_major_term(t):
        Fall  YYYY90 -> Spring (YYYY+1)10
        Spring YYYY10 -> Fall  YYYY90
#}
{% macro next_major_term(term_code_column) -%}
    case
        when right({{ term_code_column }}, 2) = '90'
            then concat(cast(cast(left({{ term_code_column }}, 4) as int) + 1 as varchar), '10')
        when right({{ term_code_column }}, 2) = '10'
            then concat(left({{ term_code_column }}, 4), '90')
    end
{%- endmacro %}
