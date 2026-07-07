from chatbot.sql_generator import _violates_student_id_guard


def test_count_distinct_student_id_ok():
    sql = "SELECT COUNT(DISTINCT student_id) FROM REPORT.fct_enrollment_term"
    assert _violates_student_id_guard(sql) is False


def test_bare_student_id_violates():
    sql = "SELECT student_id FROM REPORT.fct_enrollment_term"
    assert _violates_student_id_guard(sql) is True


def test_aliased_bare_student_id_violates():
    sql = "SELECT s.student_id FROM REPORT.fct_enrollment_term s"
    assert _violates_student_id_guard(sql) is True


def test_student_id_in_select_and_group_by_violates():
    sql = (
        "SELECT student_id, COUNT(*) FROM REPORT.fct_enrollment_term "
        "GROUP BY student_id"
    )
    assert _violates_student_id_guard(sql) is True


def test_nested_subquery_bare_student_id_violates():
    sql = "SELECT * FROM (SELECT student_id FROM REPORT.fct_enrollment_term) sub"
    assert _violates_student_id_guard(sql) is True


def test_multiple_aggregates_ok():
    sql = (
        "SELECT COUNT(student_id) AS n, AVG(accumgpa) AS avg_gpa "
        "FROM REPORT.fct_enrollment_term"
    )
    assert _violates_student_id_guard(sql) is False


def test_sum_min_max_student_id_ok():
    for fn in ("SUM", "MIN", "MAX"):
        sql = f"SELECT {fn}(student_id) FROM REPORT.fct_enrollment_term"
        assert _violates_student_id_guard(sql) is False, fn


def test_malformed_sql_does_not_raise_and_defaults_to_false():
    sql = "SELECT student_id FROM ((("
    assert _violates_student_id_guard(sql) is False


def test_no_student_id_at_all_ok():
    sql = "SELECT COUNT(*) FROM REPORT.fct_graduation_rate WHERE cohort_year = 2020"
    assert _violates_student_id_guard(sql) is False


def test_student_id_in_where_in_subquery_ok():
    # Real case reported by user: student_id used as a semi-join filter
    # (WHERE ... IN (SELECT student_id FROM ...)) is filter plumbing, not
    # an output value -- must not be flagged.
    sql = """
        SELECT term_code, COUNT(DISTINCT student_id) AS new_student_count
        FROM REPORT.fct_enrollment_term
        WHERE student_id IN (
            SELECT student_id FROM REPORT.dim_program_episode
            WHERE is_first_time_cohort = 1
        )
        GROUP BY term_code
        ORDER BY term_code
    """
    assert _violates_student_id_guard(sql) is False


def test_student_id_in_join_on_ok():
    sql = """
        SELECT e.term_code, COUNT(DISTINCT e.student_id)
        FROM REPORT.fct_enrollment_term e
        JOIN REPORT.dim_program_episode d ON d.student_id = e.student_id
        WHERE d.is_first_time_cohort = 1
        GROUP BY e.term_code
    """
    assert _violates_student_id_guard(sql) is False


def test_student_id_in_exists_subquery_ok():
    sql = """
        SELECT term_code, COUNT(DISTINCT student_id)
        FROM REPORT.fct_enrollment_term e
        WHERE EXISTS (
            SELECT 1 FROM REPORT.dim_program_episode d
            WHERE d.student_id = e.student_id AND d.is_first_time_cohort = 1
        )
        GROUP BY term_code
    """
    assert _violates_student_id_guard(sql) is False


def test_cte_bare_select_then_select_star_violates():
    # student_id leaked via a CTE that bare-selects it, then propagated to
    # the user through SELECT * -- must still be caught even though the
    # outer query's own projection list has no direct student_id reference.
    sql = """
        WITH ids AS (SELECT student_id FROM REPORT.fct_enrollment_term)
        SELECT * FROM ids
    """
    assert _violates_student_id_guard(sql) is True
