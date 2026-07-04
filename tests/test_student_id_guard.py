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
