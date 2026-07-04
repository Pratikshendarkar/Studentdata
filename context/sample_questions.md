# Few-Shot Examples: Natural Language → SQL → Answer
# These examples train the chatbot to generate correct SQL for complex institutional questions.

---

## EXAMPLE 1 (Brief Question 1)
**Question:** How have graduation rates for Pell-eligible students shifted over the last decade?

**SQL:**
```sql
SELECT
    cohort_year,
    SUM(cohort_size)       AS cohort_size,
    SUM(graduated_count)   AS graduated_count,
    ROUND(100.0 * SUM(graduated_count) / NULLIF(SUM(cohort_size), 0), 2) AS graduation_rate_pct
FROM REPORT.fct_graduation_rate
WHERE pell = 'Y'
GROUP BY cohort_year
ORDER BY cohort_year;
```

**Answer:** "For Pell-eligible students, graduation rates have ranged from approximately 41% to 59% over the 2015–2024 cohort period. The 2015 cohort had the highest graduation rate at ~58.6%, while rates dipped in the middle years (2018: ~40.9%) before recovering. Note: cohorts after 2024 are excluded as students are still in progress."

---

## EXAMPLE 2 (Brief Question 2)
**Question:** What is the first-year retention rate for undergraduate students in the College of Engineering?

**SQL:**
```sql
SELECT
    cohort_year,
    SUM(one_year_eligible_cohort_size) AS eligible_cohort,
    SUM(one_year_retained_count)       AS retained,
    ROUND(100.0 * SUM(one_year_retained_count) / NULLIF(SUM(one_year_eligible_cohort_size), 0), 2) AS first_year_retention_rate_pct
FROM REPORT.fct_retention_rate_cohort
WHERE u_g = 'U'
  AND school = 'EN'
GROUP BY cohort_year
ORDER BY cohort_year;
```

**Answer:** "First-year retention for Engineering undergrads has been consistently strong, averaging around 83% across the 2015–2024 cohorts. The highest was 85.1% for the 2017 cohort, and the lowest was 79.0% for 2024. Note: 2025 and 2026 cohorts are excluded as not enough time has elapsed to measure their one-year retention."

---

## EXAMPLE 3 (Brief Question 3)
**Question:** What is the number of Pell Grant-eligible students by semester in Master's level programs?

**SQL:**
```sql
SELECT
    term_code,
    term_year,
    term_season,
    COUNT(DISTINCT student_id) AS pell_eligible_masters_students
FROM REPORT.fct_enrollment_term
WHERE u_g = 'G'
  AND pell = 'Y'
GROUP BY term_code, term_year, term_season
ORDER BY term_code;
```

**Answer:** "Pell-eligible Master's students have ranged from approximately 230–292 students per semester. Spring semesters consistently have slightly fewer than Fall. The count has grown modestly from ~230 in Spring 2016 to ~292 in Fall 2025."

---

## EXAMPLE 4
**Question:** Compare graduation rates by school for the 2018 cohort

**SQL:**
```sql
SELECT
    school,
    SUM(cohort_size)     AS cohort_size,
    SUM(graduated_count) AS graduated_count,
    ROUND(100.0 * SUM(graduated_count) / NULLIF(SUM(cohort_size), 0), 2) AS graduation_rate_pct
FROM REPORT.fct_graduation_rate
WHERE cohort_year = 2018
GROUP BY school
ORDER BY graduation_rate_pct DESC;
```

**Answer:** "For the 2018 entry cohort, graduation rates by college are: [table]. The College of Computing (CC) and Martin Tuchman School of Management (SM) tend to have higher rates while Architecture (AD) varies by cohort size."

---

## EXAMPLE 5
**Question:** What is the 2-year retention rate for female Master's students?

**SQL:**
```sql
SELECT
    cohort_year,
    SUM(two_year_eligible_cohort_size) AS eligible,
    SUM(two_year_retained_count)       AS retained,
    ROUND(100.0 * SUM(two_year_retained_count) / NULLIF(SUM(two_year_eligible_cohort_size), 0), 2) AS second_year_retention_rate_pct
FROM REPORT.fct_retention_rate_cohort
WHERE u_g = 'G'
  AND gender = 'Female'
GROUP BY cohort_year
ORDER BY cohort_year;
```

---

## EXAMPLE 6
**Question:** How has enrollment changed term over term in Engineering?

**SQL:**
```sql
SELECT
    term_code,
    term_season,
    term_year,
    COUNT(DISTINCT student_id) AS total_enrolled
FROM REPORT.fct_enrollment_term
WHERE school = 'EN'
GROUP BY term_code, term_season, term_year
ORDER BY term_code;
```

---

## EXAMPLE 7
**Question:** What was the attrition rate in Fall 2023 for undergraduate students?

**SQL:**
```sql
SELECT
    current_term,
    SUM(prior_students)          AS prior_students,
    SUM(graduates_excluded)      AS graduates_excluded,
    SUM(eligible_prior_students) AS eligible_prior,
    SUM(continuing_students)     AS continuing,
    ROUND(100.0 * (SUM(eligible_prior_students) - SUM(continuing_students)) / NULLIF(SUM(eligible_prior_students), 0), 2) AS attrition_rate_pct
FROM REPORT.fct_retention_rate_term
WHERE current_term = '202390'
  AND u_g = 'U'
GROUP BY current_term;
```

---

## EXAMPLE 8
**Question:** How many students started a PhD program in the College of Computing in 2019?

**SQL:**
```sql
SELECT COUNT(*) AS new_phd_students
FROM REPORT.dim_program_episode
WHERE u_g = 'D'
  AND school = 'CC'
  AND cohort_year = 2019
  AND is_first_time_cohort = 1;
```

---

## EXAMPLE 9
**Question:** What is the average GPA for Pell-eligible Engineering students in Fall 2023?

**SQL:**
```sql
SELECT
    ROUND(AVG(accumgpa), 2) AS avg_gpa
FROM REPORT.fct_enrollment_term
WHERE school = 'EN'
  AND pell = 'Y'
  AND term_code = '202390';
```

---

## EXAMPLE 10
**Question:** Which cohort year had the best graduation rate for Pell-eligible undergrads?

**SQL:**
```sql
SELECT
    cohort_year,
    SUM(cohort_size)     AS cohort_size,
    SUM(graduated_count) AS graduated_count,
    ROUND(100.0 * SUM(graduated_count) / NULLIF(SUM(cohort_size), 0), 2) AS graduation_rate_pct
FROM REPORT.fct_graduation_rate
WHERE pell = 'Y'
  AND u_g = 'U'
GROUP BY cohort_year
ORDER BY graduation_rate_pct DESC
LIMIT 1;
```

---

## EXAMPLE 11
**Question:** How many students graduated in Spring 2024 across all programs?

**SQL:**
```sql
SELECT
    SUM(graduated_students) AS total_graduates
FROM REPORT.fct_graduation_rate_term
WHERE current_term = '202410';
```

---

## EXAMPLE 12
**Question:** What is the Pell gap in graduation rates — do Pell students graduate at a lower rate than non-Pell?

**SQL:**
```sql
SELECT
    pell,
    SUM(cohort_size)     AS cohort_size,
    SUM(graduated_count) AS graduated_count,
    ROUND(100.0 * SUM(graduated_count) / NULLIF(SUM(cohort_size), 0), 2) AS graduation_rate_pct
FROM REPORT.fct_graduation_rate
WHERE pell IN ('Y', 'N')
GROUP BY pell
ORDER BY pell;
```

**Answer:** "The graduation rate for Pell-eligible students (Y) is approximately 49% vs 51% for non-Pell (N), suggesting a small but meaningful equity gap of ~2 percentage points. Non-Pell students graduate at a slightly higher rate across all cohort years combined."

---

## EXAMPLE 13
**Question:** Which cohort year had the highest 1-year retention rate for doctoral students?

**SQL:**
```sql
SELECT
    cohort_year,
    SUM(one_year_eligible_cohort_size) AS eligible,
    SUM(one_year_retained_count)       AS retained,
    ROUND(100.0 * SUM(one_year_retained_count) / NULLIF(SUM(one_year_eligible_cohort_size), 0), 2) AS first_year_retention_rate_pct
FROM REPORT.fct_retention_rate_cohort
WHERE u_g = 'D'
GROUP BY cohort_year
HAVING SUM(one_year_eligible_cohort_size) > 0
ORDER BY first_year_retention_rate_pct DESC
LIMIT 1;
```

**Answer:** "The 2020 doctoral cohort had the highest 1-year retention rate at 91.10% (174 of 191 eligible students retained)."

**Why the HAVING clause matters:** fct_retention_rate_cohort keeps a row for every cohort_year even when a cohort is too recent to be eligible yet (one_year_eligible_cohort_size = 0, e.g. the 2026 doctoral cohort). Dividing by NULLIF(0, 0) makes the rate NULL for that row, and NULL sorts FIRST even under ORDER BY ... DESC in Snowflake -- so without the HAVING filter, the ineligible 2026 row would wrongly win the LIMIT 1 instead of the real answer (2020). Always exclude zero/NULL denominators before ORDER BY ... LIMIT on any computed rate.

---

## COMMON MISTAKES TO AVOID

1. **WRONG:** `AVG(graduation_rate_pct)` — never average pre-computed rates
   **RIGHT:** `SUM(graduated_count) / SUM(cohort_size) * 100`

2. **WRONG:** `WHERE school = 'Engineering'`
   **RIGHT:** `WHERE school = 'EN'`

3. **WRONG:** `WHERE u_g = 'Graduate'`
   **RIGHT:** `WHERE u_g = 'G'`

4. **WRONG:** `WHERE term_code = 2024`
   **RIGHT:** `WHERE term_code = '202490'` (Fall 2024) or `'202410'` (Spring 2024)

5. **WRONG:** `WHERE pell != 'N'` (this accidentally includes Unknown)
   **RIGHT:** `WHERE pell = 'Y'` (explicitly only Pell-eligible)

6. **WRONG:** Adding a WHERE clause to filter out recent cohorts in fct_graduation_rate
   **RIGHT:** The maturity filter is already baked in — just query the table directly

7. **WRONG:** `ORDER BY <computed_rate> DESC LIMIT 1` on fct_retention_rate_cohort/
   fct_retention_rate_term without excluding zero-denominator rows first —
   NULL rates (from ineligible/immature cohorts) sort FIRST even with DESC
   and will wrongly win the LIMIT 1
   **RIGHT:** Add `HAVING SUM(<eligible_size_or_denominator_column>) > 0`
   before `ORDER BY <computed_rate> DESC LIMIT 1` (see Example 13)
