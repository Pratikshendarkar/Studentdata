import pandas as pd

from chatbot import chart_helper


def test_wants_chart_detects_keywords():
    assert chart_helper.wants_chart("Can you plot the graduation rate trend?")
    assert chart_helper.wants_chart("Show me a chart of retention by school")
    assert chart_helper.wants_chart("Graph the Pell gap over the years")
    assert chart_helper.wants_chart("Visualize enrollment by term")


def test_wants_chart_false_for_plain_question():
    assert not chart_helper.wants_chart("What is the graduation rate for 2020?")
    assert not chart_helper.wants_chart("How many students graduated in Fall 2024?")


def test_wants_chart_excludes_non_visual_graph_usage():
    # "graph"/"chart" used as data-structure/lineage terms, not a
    # visualization request -- must NOT trigger chart mode even though
    # the word "graph" is literally present.
    assert not chart_helper.wants_chart("Is there a data lineage graph for this pipeline?")
    assert not chart_helper.wants_chart("What does the dependency graph look like for this dbt model?")
    assert not chart_helper.wants_chart("Do we use a graph database anywhere in this stack?")


def test_wants_chart_excludes_explain_the_chart_questions():
    # Asking what a chart/column measures is a definitional question,
    # not a request to render one.
    assert not chart_helper.wants_chart("What does the retention chart measure?")
    assert not chart_helper.wants_chart("What is the graduation graph supposed to mean?")


def test_wants_chart_trend_alone_without_time_cue_is_false():
    # "trend" without an explicit time/breakdown cue is too vague to
    # commit to a chart -- can be answered in prose just as well.
    assert not chart_helper.wants_chart("What's the trend here?")
    assert not chart_helper.wants_chart("Is there a trend?")


def test_wants_chart_trend_with_time_cue_is_true():
    assert chart_helper.wants_chart("Show the enrollment trend over time")
    assert chart_helper.wants_chart("What is the retention trend by year?")
    assert chart_helper.wants_chart("Graduation trend by cohort")


def test_single_scalar_row_not_chartable():
    df = pd.DataFrame([{"total_graduates": 648}])
    assert not chart_helper.has_chartable_shape(df)


def test_empty_df_not_chartable():
    df = pd.DataFrame()
    assert not chart_helper.has_chartable_shape(df)


def test_term_code_axis_plotted_as_categorical_not_numeric():
    # Regression: term_code (YYYYTT, e.g. 202590) is an encoded ID, not a
    # continuous quantity. Plotting it as a raw number makes Plotly
    # auto-scale the axis into meaningless "201.6k, 202k" tick labels.
    # It must be cast to string so it renders as an evenly-spaced
    # categorical axis in chronological order instead.
    df = pd.DataFrame({
        "TERM_CODE": [201510, 201590, 201610, 201690, 202590, 202610],
        "PELL_ELIGIBLE_MASTERS_STUDENTS": [228, 253, 231, 220, 289, 286],
    })
    fig = chart_helper.build_chart(df)
    assert fig is not None
    x_values = list(fig.data[0].x)
    assert all(isinstance(v, str) for v in x_values)
    assert x_values == ["201510", "201590", "201610", "201690", "202590", "202610"]
    # dtype alone isn't sufficient -- Plotly can still auto-coerce an
    # all-digit string axis back to numeric, so the layout's axis type
    # must be explicitly forced to "category" as well.
    assert fig.layout.xaxis.type == "category"


def test_numeric_cohort_year_axis_is_chartable():
    # Regression test: cohort_year is commonly stored as an int, not a
    # string -- a numeric year column must still be picked as the x-axis,
    # not skipped in favor of the numeric rate column.
    df = pd.DataFrame({
        "cohort_year": [2015, 2016, 2017, 2018, 2019, 2020],
        "graduation_rate_pct": [44.02, 45.1, 46.0, 48.2, 50.1, 55.3],
    })
    assert chart_helper._find_x_column(df) == "cohort_year"
    assert chart_helper.has_chartable_shape(df)
    fig = chart_helper.build_chart(df)
    assert fig is not None
    assert list(fig.data[0].x) == [2015, 2016, 2017, 2018, 2019, 2020]
    assert list(fig.data[0].y) == [44.02, 45.1, 46.0, 48.2, 50.1, 55.3]


def test_trend_over_terms_is_chartable():
    df = pd.DataFrame({
        "current_term": ["202410", "202490", "202510", "202590"],
        "term_graduation_rate_pct": [13.5, 18.9, 13.3, 18.4],
    })
    assert chart_helper.has_chartable_shape(df)
    fig = chart_helper.build_chart(df)
    assert fig is not None


def test_breakdown_by_school_is_chartable():
    df = pd.DataFrame({
        "school": ["AD", "CC", "EN", "SL", "SM"],
        "term_graduation_rate_pct": [21.3, 25.8, 22.0, 25.6, 26.3],
    })
    assert chart_helper.has_chartable_shape(df)
    fig = chart_helper.build_chart(df)
    assert fig is not None


def test_multi_series_by_group_is_chartable():
    df = pd.DataFrame({
        "current_term": ["202410", "202410", "202490", "202490"],
        "pell": ["Y", "N", "Y", "N"],
        "graduation_rate_pct": [10.0, 15.0, 12.0, 18.0],
    })
    assert chart_helper.has_chartable_shape(df)
    # Grouping only kicks in when the question references the dimension
    # (here, "pell") -- see test_group_column_requires_question_reference
    # for the case where it's correctly suppressed.
    fig = chart_helper.build_chart(df, question="chart graduation rate by pell over terms")
    assert fig is not None
    # Multi-series chart should have one trace per group (Y, N)
    assert len(fig.data) == 2


def test_group_column_requires_question_reference():
    # Regression: an incidental categorical column in the result (e.g.
    # degtype, present only because a join pulled it in) must NOT become
    # an unrequested grouping dimension just because it has low
    # cardinality. Only groups when the question actually references the
    # column name or one of its values.
    df = pd.DataFrame({
        "term_code": [201510, 201510, 201510, 201590, 201590, 201590],
        "degtype": ["BS", "MS", "PHD", "BS", "MS", "PHD"],
        "student_count": [100, 50, 10, 110, 55, 12],
    })
    fig_no_mention = chart_helper.build_chart(df, question="plot student count by term")
    assert fig_no_mention is not None
    assert len(fig_no_mention.data) == 1

    fig_with_mention = chart_helper.build_chart(df, question="plot student count by term and degtype")
    assert fig_with_mention is not None
    assert len(fig_with_mention.data) == 3


def test_all_string_columns_not_chartable():
    df = pd.DataFrame({
        "student_id": ["S1", "S2", "S3"],
        "school": ["AD", "CC", "EN"],
    })
    assert not chart_helper.has_chartable_shape(df)


def test_build_chart_returns_none_for_unchartable_df():
    df = pd.DataFrame([{"total": 5}])
    assert chart_helper.build_chart(df) is None


def test_single_row_multi_column_not_chartable():
    # Even with numeric + categorical columns, a single row has nothing to trend
    df = pd.DataFrame([{"school": "EN", "graduation_rate_pct": 22.0}])
    assert not chart_helper.has_chartable_shape(df)


def test_rate_question_prefers_rate_column_over_raw_count():
    # Regression: a result with both a raw count column and a rate column
    # (e.g. RETAINED_COUNT alongside RETENTION_RATE_PCT) must plot the
    # rate when the question asks for "rate" -- not just take the first
    # numeric column positionally, which previously plotted headcounts
    # (in the thousands) on a y-axis the user expected to show a
    # percentage (0-100).
    df = pd.DataFrame({
        "COHORT_YEAR": [2015, 2016, 2017, 2018],
        "RETAINED_COUNT": [2950, 3010, 3040, 3030],
        "RETENTION_RATE_PCT": [81.38, 81.99, 83.46, 81.06],
    })
    fig = chart_helper.build_chart(df, question="plot line graph for 1-year retention rate by cohort_year")
    assert fig is not None
    assert len(fig.data) == 1
    assert list(fig.data[0].y) == [81.38, 81.99, 83.46, 81.06]


def test_no_question_falls_back_to_first_column_positionally():
    # Without question context, behavior is unchanged from before --
    # multiple numeric columns are all plotted as separate series.
    df = pd.DataFrame({
        "COHORT_YEAR": [2015, 2016, 2017, 2018],
        "RETAINED_COUNT": [2950, 3010, 3040, 3030],
        "RETENTION_RATE_PCT": [81.38, 81.99, 83.46, 81.06],
    })
    fig = chart_helper.build_chart(df)
    assert fig is not None
    assert len(fig.data) == 2


def test_rate_column_returned_as_string_dtype_still_detected_numeric():
    # Regression: Snowflake's connector can return NUMBER/DECIMAL columns
    # as Python str/Decimal objects rather than pandas float dtype. Without
    # coercion, is_numeric_dtype() returns False for the rate column, so
    # it gets excluded from numeric_cols entirely and misidentified as a
    # low-cardinality categorical column instead -- producing a broken
    # chart where each rate VALUE (57.11, 58.81, ...) becomes its own
    # legend entry/color instead of one continuous line, and a raw count
    # column ends up as the y-axis instead.
    df = pd.DataFrame({
        "COHORT_YEAR": [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024],
        "TOTAL_RETAINED": [1780, 1790, 1800, 1770, 1810, 1820, 1830, 1840, 1780, 200],
        "TWO_YEAR_RETENTION_RATE_PCT": pd.array(
            ["57.11", "57.44", "58.81", "57.34", "56.80", "57.83", "58.08", "55.21", "56.95", "50.58"],
            dtype=object,
        ),
    })
    assert chart_helper.has_chartable_shape(df)
    fig = chart_helper.build_chart(df, question="plot the line graph for 2 year retention rate by cohort year")
    assert fig is not None
    assert len(fig.data) == 1
    assert list(fig.data[0].y) == [57.11, 57.44, 58.81, 57.34, 56.80, 57.83, 58.08, 55.21, 56.95, 50.58]


def test_genuinely_categorical_string_column_not_coerced():
    # A real categorical column (school codes) must NOT be forced into
    # numeric -- only columns whose values ALL parse cleanly as numbers
    # should be coerced.
    df = pd.DataFrame({
        "SCHOOL": ["AD", "CC", "EN", "SL", "SM"],
        "GRADUATION_RATE_PCT": [21.3, 25.8, 22.0, 25.6, 26.3],
    })
    coerced = chart_helper._coerce_numeric_looking_columns(df)
    assert not pd.api.types.is_numeric_dtype(coerced["SCHOOL"])
    assert list(coerced["SCHOOL"]) == ["AD", "CC", "EN", "SL", "SM"]


def test_secondary_time_column_not_picked_as_metric():
    # Regression: "Visualize enrollment by term" against a result with
    # both TERM_CODE (x-axis) and TERM_YEAR (a second time dimension,
    # also numeric) alongside the real metric STUDENT_COUNT. TERM_YEAR
    # must never be picked as the y-axis metric just because it's
    # numeric and isn't the chosen x_col -- it's still a time column, not
    # a measurement.
    df = pd.DataFrame({
        "TERM_CODE": [201510, 201590, 201610, 201690],
        "TERM_YEAR": [2015, 2015, 2016, 2016],
        "TERM_SEASON": ["Spring", "Fall", "Spring", "Fall"],
        "STUDENT_COUNT": [2279, 2350, 2300, 2400],
    })
    x_col = chart_helper._find_x_column(df)
    numeric_cols = chart_helper._find_numeric_columns(df, exclude=x_col)
    assert numeric_cols == ["STUDENT_COUNT"]

    fig = chart_helper.build_chart(df, question="Visualize enrollment by term for Master's students")
    assert fig is not None
    for trace in fig.data:
        assert list(trace.y) != [2015, 2015] and list(trace.y) != [2016, 2016]
    all_y_values = [v for trace in fig.data for v in trace.y]
    assert set(all_y_values).issubset({2279, 2350, 2300, 2400})


def test_multi_series_term_code_axis_uses_chronological_categoryarray():
    # Regression: grouping by a second categorical column (e.g.
    # TERM_SEASON: Spring/Fall) over a term_code x-axis previously let
    # Plotly infer the shared category axis order from per-trace
    # first-appearance, visually clustering all Spring terms before all
    # Fall terms instead of interleaving them chronologically. The axis
    # must be forced into the true chronological order via an explicit
    # categoryarray.
    df = pd.DataFrame({
        "TERM_CODE": [201510, 201590, 201610, 201690, 201710, 201790],
        "TERM_SEASON": ["Spring", "Fall", "Spring", "Fall", "Spring", "Fall"],
        "TOTAL_ENROLLED": [2279, 2300, 2290, 2310, 2295, 2320],
    })
    fig = chart_helper.build_chart(df, question="visualize enrollment by term")
    assert fig is not None
    assert fig.layout.xaxis.categoryorder == "array"
    assert list(fig.layout.xaxis.categoryarray) == [
        "201510", "201590", "201610", "201690", "201710", "201790",
    ]
