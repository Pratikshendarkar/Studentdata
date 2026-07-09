"""
Chart-worthiness detection and chart-type selection for SQL query results.

Rule-based, not LLM-driven, to keep chart selection deterministic and
fast -- same pattern already used by term_resolver.py and
query_classifier.py in this codebase. wants_chart() is called on every
single chat message regardless of route, so it deliberately avoids an
LLM call (that would add latency to every turn, not just chart-relevant
ones) in favor of phrase-pattern matching.

Only called when the user's question passes wants_chart(); even then, a
chart only renders if the result shape actually supports one
(has_chartable_shape()). A chart cue alone (e.g. "plot how many students
graduated in Fall 2024") is not sufficient if the result is a single
scalar row with nothing to visualize.
"""

import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Imperative visualization verbs -- "plot X", "graph X", "chart X",
# "visualize X". A plain substring match on these words alone is too
# blunt: "graph"/"chart" are also used non-visually in this domain (see
# _NON_VISUAL_EXCLUSIONS below), so this is combined with an exclusion
# pass rather than triggering on presence alone.
_POSITIVE_VERB_PATTERN = re.compile(r"\b(plot|chart|graph|visuali[sz]e)\b", re.IGNORECASE)

# "trend" alone is a weaker signal than an explicit chart verb -- "what's
# the trend" can be answered in prose just as well as a chart. Only treat
# it as chart-intent when paired with an explicit time/breakdown cue.
_TREND_WITH_TIME_CUE = re.compile(
    r"\btrend(s)?\b.*\b(over time|by year|by term|by semester|by cohort)\b"
    r"|\b(over time|by year|by term|by semester|by cohort)\b.*\btrend(s)?\b",
    re.IGNORECASE,
)

# Non-visual usages of "graph"/"chart" specific to this domain -- these
# suppress the chart trigger even if a positive verb also matched, since
# the word is being used as a data-structure/lineage term or the question
# is asking to explain a chart/column rather than render one.
_NON_VISUAL_EXCLUSIONS = re.compile(
    r"\bdata lineage\b|\bdependency graph\b|\bgraph database\b|\bknowledge graph\b"
    r"|\bwhat (is|does|are)\b.*\b(chart|graph)\b.*\b(mean|measure)\b",
    re.IGNORECASE,
)

# NOT YET IMPLEMENTED: a secondary positive signal from breakdown/
# comparison cues without an explicit chart verb ("break down graduation
# rate by school over the years") would close the remaining false-negative
# gap, but risks reintroducing false positives on plain lookups that
# happen to include "by school" while only wanting one number. Deferred
# until real usage shows the current heuristic still misses too much.

_TERM_COL_PATTERN = re.compile(r"\b(term|year|semester)\b|term_code|term_year|cohort_year|current_term", re.IGNORECASE)
_METRIC_SUFFIX_PATTERN = re.compile(r"rate|pct|percent|count|students|gpa|credit", re.IGNORECASE)

# term_code (YYYYTT, e.g. 202590) is an encoded ID, not a continuous
# quantity -- must be plotted as a categorical/string axis, or Plotly
# treats it as a number and auto-scales the axis into meaningless
# "201.6k, 201.8k, 202k" tick labels. cohort_year/term_year (plain
# 4-digit years) are genuinely continuous and fine to plot as numbers.
_CODE_LIKE_PATTERN = re.compile(r"term_code|^current_term$", re.IGNORECASE)


def _coerce_numeric_looking_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Snowflake's connector can return NUMBER/DECIMAL columns as Python
    Decimal or str objects rather than pandas float/int dtypes, depending
    on driver configuration -- pd.api.types.is_numeric_dtype() then
    returns False for a column that is actually numeric data. Without
    this normalization, such a column gets excluded from
    _find_numeric_columns() entirely and can be misidentified as a
    categorical _find_group_column() instead (visible symptom: a rate
    column's individual values, e.g. 57.11/58.81, appearing as separate
    legend entries instead of one continuous line). Must run before any
    other column-shape detection.
    """
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        coerced = pd.to_numeric(df[col], errors="coerce")
        # Only replace the column if EVERY non-null value converted
        # cleanly -- a genuinely categorical column (e.g. 'AD'/'CC'/'EN')
        # will fail to coerce and must be left alone.
        if coerced.notna().equals(df[col].notna()):
            df[col] = coerced
    return df


def _is_time_axis_column(col: str) -> bool:
    """A column counts as a time axis if its name looks like one AND it
    isn't itself a metric -- avoids false positives like
    "term_graduation_rate_pct" (contains "term" but is a rate metric,
    not a time axis) while still allowing purely numeric axes like
    cohort_year (an int column, but genuinely a time axis)."""
    return bool(_TERM_COL_PATTERN.search(col)) and not _METRIC_SUFFIX_PATTERN.search(col)


def wants_chart(question: str) -> bool:
    """
    True if the question is asking for a visualization, not just
    mentioning "chart"/"graph"/"trend" incidentally. An exclusion match
    (non-visual domain usage) always wins over a positive match.
    """
    if _NON_VISUAL_EXCLUSIONS.search(question):
        return False
    return bool(_POSITIVE_VERB_PATTERN.search(question) or _TREND_WITH_TIME_CUE.search(question))


def _find_x_column(df: pd.DataFrame) -> str | None:
    """Pick a natural x-axis: a term/year/semester-like column (numeric
    or not -- cohort_year is commonly an int), else the first
    low-cardinality non-numeric column."""
    for col in df.columns:
        if _is_time_axis_column(col):
            return col
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]) and df[col].nunique() <= 50:
            return col
    return None


def _find_numeric_columns(df: pd.DataFrame, exclude: str | None) -> list[str]:
    """
    Numeric columns eligible to be a y-axis metric. Excludes the chosen
    x_col AND any other time-shaped column (e.g. term_year alongside a
    term_code x-axis) -- a secondary time dimension is not a metric and
    must never be picked as "the" numeric value to plot, even
    positionally as numeric_cols[0].
    """
    return [
        col for col in df.columns
        if col != exclude
        and pd.api.types.is_numeric_dtype(df[col])
        and not _is_time_axis_column(col)
    ]


def _find_group_column(df: pd.DataFrame, x_col: str, numeric_cols: list[str]) -> str | None:
    """A second low-cardinality categorical column (besides x_col) to
    split multiple series by, e.g. pell/school/gender."""
    for col in df.columns:
        if col == x_col or col in numeric_cols:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]) and 1 < df[col].nunique() <= 12:
            return col
    return None


def has_chartable_shape(df: pd.DataFrame) -> bool:
    """
    True if df has enough structure to plot: at least 2 rows, at least
    one numeric column, and a usable x-axis column.
    """
    if df is None or df.empty or len(df) < 2:
        return False
    df = _coerce_numeric_looking_columns(df)
    x_col = _find_x_column(df)
    if x_col is None:
        return False
    if not _find_numeric_columns(df, exclude=x_col):
        return False
    return True


def _pick_primary_y_column(numeric_cols: list[str], question: str | None) -> str:
    """
    When a result has multiple numeric columns (e.g. a raw count column
    alongside a computed rate/pct column), prefer the one the user's
    question is actually about over just taking the first column
    positionally. Without this, "plot the retention RATE" could silently
    plot a raw headcount column instead, just because it happened to come
    first in the SELECT list.
    """
    if question:
        q_lower = question.lower()
        if "rate" in q_lower or "percent" in q_lower or "%" in q_lower:
            for col in numeric_cols:
                if re.search(r"rate|pct|percent", col, re.IGNORECASE):
                    return col
    return numeric_cols[0]


def build_chart(df: pd.DataFrame, question: str | None = None):
    """
    Build a Plotly figure from df, choosing line vs. bar and single vs.
    multi-series based on column shape. Returns None if no chartable
    shape is found (callers should check has_chartable_shape() first,
    but this is defensive in case it's called directly).

    `question` (the user's original question text) is optional context
    used only to disambiguate which numeric column is the primary metric
    when more than one is present -- it does not affect chart-worthiness.
    """
    if not has_chartable_shape(df):
        return None

    df = _coerce_numeric_looking_columns(df)
    x_col = _find_x_column(df)
    numeric_cols = _find_numeric_columns(df, exclude=x_col)
    group_col = _find_group_column(df, x_col, numeric_cols)

    is_ordered_axis = _is_time_axis_column(x_col)
    plot_df = df.sort_values(x_col) if is_ordered_axis else df.copy()

    is_code_like = bool(_CODE_LIKE_PATTERN.search(x_col))
    if is_code_like:
        # Cast to string so Plotly treats it as an evenly-spaced
        # categorical axis instead of auto-scaling it as a number.
        # dtype alone isn't always enough -- Plotly can still coerce an
        # all-digit string column back to numeric, so xaxis_type is also
        # forced explicitly below after the figure is built.
        plot_df = plot_df.copy()
        plot_df[x_col] = plot_df[x_col].astype(str)

    y_col = _pick_primary_y_column(numeric_cols, question)
    # Only plot every numeric column as its own series when the question
    # didn't single one out -- e.g. a raw count column and a rate column
    # are on incompatible scales and shouldn't share one y-axis just
    # because both happened to be in the SELECT list.
    plot_all_numeric = len(numeric_cols) > 1 and y_col == numeric_cols[0] and question is None

    if group_col:
        fig = px.line(plot_df, x=x_col, y=y_col, color=group_col, markers=True)
    elif is_ordered_axis:
        if plot_all_numeric:
            fig = go.Figure()
            for col in numeric_cols:
                fig.add_trace(go.Scatter(x=plot_df[x_col], y=plot_df[col], mode="lines+markers", name=col))
        else:
            fig = px.line(plot_df, x=x_col, y=y_col, markers=True)
    else:
        fig = px.bar(plot_df, x=x_col, y=y_col)

    layout_kwargs = dict(margin=dict(l=10, r=10, t=30, b=10), height=350)
    if is_code_like:
        layout_kwargs["xaxis_type"] = "category"
    fig.update_layout(**layout_kwargs)
    return fig
