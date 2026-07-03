# NJIT Student Data — Complete Data Dictionary & Business Logic
# Used by the AI chatbot to understand the dataset, metrics, and institutional context.

## INSTITUTION CONTEXT
- Institution: New Jersey Institute of Technology (NJIT)
- Database: NJIT (Snowflake)
- Reporting Schema: REPORT (all chatbot queries go here)
- Data covers: Academic years 2015–2026, Fall and Spring semesters
- Source: Synthetic dataset with 265,668 enrollment records, 54,090 unique students

---

## ACADEMIC UNITS (school column)
| Code | Full Name |
|------|-----------|
| AD   | Hillier College of Architecture and Design (HCAD) |
| CC   | Ying Wu College of Computing (YWCC) |
| EN   | Newark College of Engineering (NCE) — also referred to as "College of Engineering" |
| SL   | College of Science and Liberal Arts (CSLA) |
| SM   | Martin Tuchman School of Management (MTSM) |

NOTE: When a user asks about "College of Engineering" or "Engineering school", use school='EN'.
When a user asks about "Computing" or "Computer Science", use school='CC'.

---

## STUDENT LEVEL (u_g column)
| Code | Meaning |
|------|---------|
| U    | Undergraduate student |
| G    | Graduate / Master's level student |
| D    | Doctoral student |

NOTE: "Master's level" = u_g='G'. "Undergrad" or "undergraduate" = u_g='U'. "PhD" or "doctoral" = u_g='D'.

---

## PELL GRANT ELIGIBILITY (pell column)
| Value   | Meaning |
|---------|---------|
| Y       | Pell Grant eligible (low-income students) |
| N       | Not Pell Grant eligible |
| Unknown | Data not available (blank in source, ~20% of records) |

NOTE: "Pell-eligible" or "Pell Grant students" = pell='Y'.
      Do NOT treat Unknown as N — they are genuinely missing data.

---

## DEGREE TYPE (degtype column)
| Code | Meaning |
|------|---------|
| BA   | Bachelor of Arts |
| BS   | Bachelor of Science |
| BAR  | Bachelor of Architecture |
| BET  | Bachelor of Engineering Technology |
| MS   | Master of Science |
| MBA  | Master of Business Administration |
| MAR  | Master of Architecture |
| PHD  | Doctor of Philosophy |
| CRT  | Certificate program |
| G    | General Graduate |
| U    | General Undergraduate |

---

## REGISTRATION STATUS (regstat column)
| Code | Meaning |
|------|---------|
| 1    | First-time (brand new student, never enrolled before) |
| 2    | Transfer student (entering with credits from another institution) |
| 3    | Stop-out / Readmit (returning after unapproved absence) |
| 4    | Continuing (active ongoing student) |

NOTE: "First-time students" = regstat='1' or is_first_time_cohort=1 in episode tables.
      Retention rate calculations use ONLY first-time cohorts (regstat=1).

---

## CITIZENSHIP STATUS (citizen column)
| Code | Meaning |
|------|---------|
| 1    | US Citizen |
| 2    | International student |
| 3    | US Permanent Resident |
| 4    | Information Not Available |

---

## ACADEMIC TERMS (term_code column)
Format: YYYYTT (6 digits)
- First 4 digits = calendar year
- Last 2 digits = term suffix

| Suffix | Term |
|--------|------|
| 10     | Spring Semester |
| 50     | Summer Term |
| 90     | Fall Semester |
| 95     | Winter Intersession |

Examples:
- 202490 = Fall 2024
- 202510 = Spring 2025
- 201590 = Fall 2015

NOTE: Only Fall (90) and Spring (10) are used for cohort/retention analysis.
      Summer and Winter are excluded from major term sequencing.
      "Last year same term" = current_term - 100 (e.g. 202490 - 100 = 202390)

---

## ACADEMIC STATE (academic_state column)
| Value                   | Meaning |
|-------------------------|---------|
| Enrolled                | Currently active student |
| Graduated               | Completed degree |
| Maintaining Registration| Registered but not taking courses (common for doctoral students) |

NOTE: There is NO "Withdrawn" or "Dropped" state. A student who left without graduating
      simply stops appearing in subsequent terms. The absence of records = attrition.

---

## FIRST GENERATION STUDENT (firstgen column)
| Value   | Meaning |
|---------|---------|
| Y       | First-generation college student (neither parent attended college) |
| N       | Not first-generation |
| Unknown | Data not available (~19% of records) |

---

## PROGRAM EPISODE (key concept)
A "program episode" is one continuous enrollment run of a student in ONE specific program.
Key: (student_id, u_g, degtype)

A single student_id can have MULTIPLE episodes if they completed one degree and enrolled
in another. Example: STU54835 has a BS episode (2015-2019) AND a PHD episode (2019-2024).

- program_episode_id format: student_id-u_g-degtype-cohort_term (e.g. STU54835-U-BS-201590)
- cohort_term = the term they STARTED that program (their entry term)
- cohort_year = the calendar year they started (e.g. 2015)

---

## MATURED COHORT FILTER (critical for graduation/retention accuracy)
Recent cohorts are EXCLUDED from graduation/retention rate calculations because they
haven't had enough time to complete their programs. This prevents a false "collapsing"
trend where recent years appear to have 0% graduation rates.

Maturity windows by program level:
- U (Undergraduate): 4 years (cohort_term + 400 in YYYYTT arithmetic)
- G (Master's): 2 years (cohort_term + 200)
- D (Doctoral): 5 years (cohort_term + 500)

This filter is ALREADY BAKED INTO fct_graduation_rate and fct_retention_rate_cohort.
You do NOT need to add WHERE clauses for maturity — just query those tables directly.

---

## METRIC FORMULAS

### Graduation Rate
```
Graduation Rate % = (graduated_count / cohort_size) × 100
```
- cohort_size = number of students who STARTED in that cohort year (entry year)
- graduated_count = how many of those starters eventually graduated (at any point)
- Source table: REPORT.fct_graduation_rate

### 1-Year Retention Rate
```
1-Year Retention Rate % = (one_year_retained_count / one_year_eligible_cohort_size) × 100
```
- one_year_eligible_cohort_size = first-time students whose cohort is mature enough for 1-year check
- one_year_retained_count = of those, how many enrolled 2 major terms later (1 year out)
- Early completers (graduated before 1-year mark) are EXCLUDED from denominator
- Source table: REPORT.fct_retention_rate_cohort

### 2-Year Retention Rate
```
2-Year Retention Rate % = (two_year_retained_count / two_year_eligible_cohort_size) × 100
```
- Same logic as 1-year but checks enrollment 4 major terms later (2 years out)
- Source table: REPORT.fct_retention_rate_cohort

### Term-over-Term Retention Rate (Adjusted Retention Rate / ARR)
```
ARR % = continuing_students / (prior_term_students - graduates_excluded) × 100
```
- continuing_students = enrolled in BOTH prior term AND current term
- prior_term_students = enrolled in the immediately preceding Fall/Spring term
- graduates_excluded = students who graduated between prior and current term
- Source table: REPORT.fct_retention_rate_term

### Attrition Rate
```
Attrition Rate % = 100 - ARR %
= (prior_students - graduates - continuing) / (prior_students - graduates) × 100
```
- Source table: REPORT.fct_retention_rate_term (attrition_rate_pct column)

### Term Graduation Rate
```
Term Graduation Rate % = (graduated_students / prior_students) × 100
```
- graduated_students = students who graduated BETWEEN prior term and current term
- prior_students = students enrolled in the prior major term
- Source table: REPORT.fct_graduation_rate_term

### Enrollment Headcount
```
Total Enrolled = COUNT(DISTINCT student_id) from fct_enrollment_term
```
- One row per (program_episode_id, term_code); a student with multiple
  program episodes in the same term has multiple rows, so always use
  COUNT(DISTINCT student_id), never COUNT(*) or COUNT(student_id)
- Source table: REPORT.fct_enrollment_term

---

## REPORT LAYER TABLES (all chatbot queries go here)

### 1. REPORT.fct_graduation_rate (COHORT LEVEL)
**Use when asked about:** graduation rates, completion rates, degree completion trends
**Grain:** one row per (degtype, u_g, gender, school, pell, cohort_year)
**Key columns:** cohort_size, graduated_count, graduation_rate_pct, cohort_year
**Filter already applied:** matured cohorts only — immature recent cohorts excluded
**Example questions:**
- "How have graduation rates for Pell-eligible students shifted over the last decade?"
- "What is the graduation rate for female Engineering students?"
- "Compare graduation rates by school for the 2018 cohort"

### 2. REPORT.fct_retention_rate_cohort (COHORT LEVEL)
**Use when asked about:** retention rates by entry year/cohort, first-year retention, second-year retention
**Grain:** one row per (degtype, u_g, gender, school, pell, cohort_year)
**Key columns:** one_year_eligible_cohort_size, one_year_retained_count, first_year_retention_rate_pct, two_year_eligible_cohort_size, two_year_retained_count, second_year_retention_rate_pct, cohort_year
**Filter already applied:** matured cohorts only, early completers excluded from denominator
**Example questions:**
- "What is the first-year retention rate for undergraduate students in the College of Engineering?"
- "Compare 1-year vs 2-year retention for Master's students"
- "Which school has the highest retention rate for the 2019 cohort?"

### 3. REPORT.fct_retention_rate_term (TERM LEVEL)
**Use when asked about:** term-by-term retention, semester retention trends, adjusted retention rate, attrition
**Grain:** one row per (current_term, degtype, u_g, school)
**Key columns:** current_term, prior_students, graduates_excluded, eligible_prior_students, continuing_students, adjusted_retention_rate, attrition_rate_pct
**Example questions:**
- "What was the retention rate in Fall 2024?"
- "How did attrition change between 2020 and 2024?"
- "What is the term-over-term retention trend for Engineering?"

### 4. REPORT.fct_graduation_rate_term (TERM LEVEL)
**Use when asked about:** graduation volume by semester, how many students graduated this term
**Grain:** one row per (current_term, degtype, u_g, gender, school, pell)
**Key columns:** current_term, prior_students, graduated_students, term_graduation_rate_pct
**Example questions:**
- "How many students graduated in Spring 2024?"
- "What percentage of students graduated in Fall 2023?"

### 5. REPORT.fct_enrollment_term (STUDENT-LEVEL LONGITUDINAL / TERM SNAPSHOT)
**Use when asked about:** enrollment headcounts by term, Pell-eligible enrollment, how many students enrolled, individual student details, GPA analysis, credit hours, full-time vs part-time
**Grain:** one row per program episode per term (a student with two concurrent programs has two rows in the same term)
**Key columns:** student_id, program_episode_id, term_code, term_year, term_season, school, pell, creditenr, accumgpa, academic_state, u_g, degtype
**For headcounts:** use COUNT(DISTINCT student_id), never COUNT(*) or COUNT(student_id)
**Example questions:**
- "What is the number of Pell Grant-eligible students by semester in Master's level programs?"
- "How has enrollment in the College of Engineering changed over time?"
- "How many female students were enrolled in Fall 2023?"
- "What is the average GPA for Pell-eligible students?"
- "What is the average credit load for Engineering undergrads?"

### 6. REPORT.dim_program_episode (DIMENSION)
**Use when asked about:** student episode attributes, cohort membership, program details
**Grain:** one row per program episode (student_id, u_g, degtype)
**Key columns:** program_episode_id, student_id, u_g, degtype, cohort_term, cohort_year, school, pell, gender, firstgen, is_first_time_cohort
**Example questions:**
- "How many students started a Master's program in 2020?"
- "How many first-time PhD students enrolled in the College of Computing?"

---

## COMMON QUESTION ROUTING GUIDE
| User asks about | Use this table |
|----------------|----------------|
| Graduation RATE over years | fct_graduation_rate |
| How many GRADUATED this term/semester | fct_graduation_rate_term |
| Retention rate by COHORT year | fct_retention_rate_cohort |
| Retention rate by TERM/SEMESTER | fct_retention_rate_term |
| Attrition rate | fct_retention_rate_term |
| Enrollment headcount by term | fct_enrollment_term (COUNT DISTINCT student_id) |
| Pell enrollment by semester | fct_enrollment_term (COUNT DISTINCT student_id) |
| Average GPA / credit hours | fct_enrollment_term |
| Student demographics / cohort attributes | dim_program_episode |

---

## IMPORTANT BUSINESS RULES FOR SQL GENERATION

1. **Never aggregate graduation_rate_pct by averaging** — always SUM(graduated_count) / SUM(cohort_size) * 100
2. **Never aggregate first_year_retention_rate_pct by averaging** — always SUM(one_year_retained_count) / SUM(one_year_eligible_cohort_size) * 100
3. **cohort_year is the ENTRY year**, not graduation year — "2015 cohort" = students who STARTED in 2015
4. **current_term is YYYYTT format** — to filter Fall 2024 use current_term = '202490'
5. **Pell Unknown ≠ N** — always handle pell IN ('Y', 'N', 'Unknown') separately, never lump Unknown with N
6. **No withdrawal state exists** — absence from subsequent terms implies attrition
7. **school='EN' = College of Engineering** — not school='Engineering'
8. **All rate tables already exclude immature cohorts** — no extra WHERE clause needed for maturity
9. **term_code arithmetic**: same season last year = term_code - 100 (e.g. 202490 → 202390)
10. **Multiple episodes**: one student can have both a BS episode and a PHD episode — use program_episode_id not student_id when counting unique programs
