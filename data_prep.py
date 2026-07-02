"""
data_prep.py — Feature engineering for the NJIT student dropout prediction model.

Source: randomdata_annotated.csv (265,668 rows, target column: at_risk)
  at_risk = 1  -> student did NOT return next major term (dropout)
  at_risk = 0  -> student returned next major term
  at_risk = NaN -> most-recent-term rows with no ground truth (dropped)

TEMPORAL SPLIT — NOT random 80/20:
  A random split would leak future information into training (e.g. train on
  Fall 2023 and test on Fall 2015), producing overoptimistic AUC estimates
  that won't hold in real deployment. Instead we use a time-based cutoff:
  - Train: all terms with term_year < CUTOFF_YEAR
  - Test:  all terms with term_year >= CUTOFF_YEAR
  This simulates real usage: model trained on historical data predicts
  on future cohorts it has never seen.

Output: outputs/X_train.pkl, outputs/X_test.pkl,
        outputs/y_train.pkl, outputs/y_test.pkl,
        outputs/feature_names.pkl
"""

import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from sklearn.preprocessing import LabelEncoder

DATA_PATH    = Path(__file__).parent / "randomdata_annotated.csv"
OUTPUT_DIR   = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# Train on terms before 2023, test on 2023+ (last ~2 years held out)
CUTOFF_YEAR  = 2023
RANDOM_STATE = 42


def load_and_clean(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)

    # Drop rows with no ground truth (most recent term — no forward term to check)
    df = df[df["at_risk"].notna()].copy()

    # Cast numeric columns
    df["at_risk"]    = df["at_risk"].astype(float).astype(int)
    df["accumgpa"]   = pd.to_numeric(df["accumgpa"], errors="coerce")
    df["creditenr"]  = pd.to_numeric(df["creditenr"], errors="coerce")
    df["term_year"]  = pd.to_numeric(df["term_year"], errors="coerce")
    df["regstat"]    = pd.to_numeric(df["regstat"], errors="coerce")
    df["year"]       = pd.to_numeric(df["year"], errors="coerce")

    # Standardize blank/missing pell and firstgen -> 'Unknown'
    df["pell"]     = df["pell"].fillna("").replace("", "Unknown")
    df["firstgen"] = df["firstgen"].fillna("").replace("", "Unknown")

    # Exclude graduated rows — they are successful completers, not at-risk
    df = df[df["academic_state"] != "Graduated"].copy()

    print(f"Rows after cleaning: {len(df):,}")
    print(f"Target distribution:\n{df['at_risk'].value_counts(normalize=True).round(4)}")

    return df


def engineer_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Build feature matrix X and target y."""

    # ── Encode pell: Y=1, N=0, Unknown=0.5
    pell_map = {"Y": 1.0, "N": 0.0, "Unknown": 0.5}
    df["pell_encoded"] = df["pell"].map(pell_map).fillna(0.5)

    # ── Encode firstgen: Y=1, N=0, Unknown=0.5
    fg_map = {"Y": 1.0, "N": 0.0, "Unknown": 0.5}
    df["firstgen_encoded"] = df["firstgen"].map(fg_map).fillna(0.5)

    # ── Encode gender: Female=1, Male=0
    df["gender_encoded"] = (df["gender"] == "Female").astype(int)

    # ── Encode term_season: Spring=1, Fall=0
    df["term_season_encoded"] = (df["term_type"] == "Spring").astype(int)

    # ── regstat ordinal (already numeric 1-4)
    df["regstat_encoded"] = df["regstat"].fillna(4)  # 4=Continuing as default

    # ── One-hot encode school (AD, CC, EN, SL, SM)
    school_dummies = pd.get_dummies(df["school"], prefix="school", dtype=int)

    # ── One-hot encode u_g (U, G, D)
    ug_dummies = pd.get_dummies(df["u_g"], prefix="ug", dtype=int)

    # ── One-hot encode degtype
    degtype_dummies = pd.get_dummies(df["degtype"], prefix="deg", dtype=int)

    # ── Derived: terms_enrolled_so_far per episode (student, u_g, degtype)
    # Rank of current term within episode — proxy for seniority/persistence
    df = df.sort_values(["student_id", "u_g", "degtype", "term_code"])
    df["terms_enrolled_so_far"] = df.groupby(
        ["student_id", "u_g", "degtype"]
    ).cumcount() + 1

    # ── Derived: gpa_change — difference from prior term's GPA per episode
    df["prior_gpa"] = df.groupby(
        ["student_id", "u_g", "degtype"]
    )["accumgpa"].shift(1)
    df["gpa_change"] = df["accumgpa"] - df["prior_gpa"]
    df["gpa_change"] = df["gpa_change"].fillna(0)  # first term of episode -> 0

    # ── Derived: citizen_encoded (1=US Citizen, 2=International, 3=Perm Resident, 4=Unknown)
    df["citizen_encoded"] = pd.to_numeric(df["citizen"], errors="coerce").fillna(4)

    # ── Derived: ethnicity_encoded (numeric 1-27, keep as-is)
    df["ethnicity_encoded"] = pd.to_numeric(df["ethnicmultirace"], errors="coerce").fillna(0)

    # ── Assemble feature matrix
    feature_cols = [
        "pell_encoded",
        "firstgen_encoded",
        "gender_encoded",
        "term_season_encoded",
        "regstat_encoded",
        "accumgpa",
        "creditenr",
        "term_year",
        "terms_enrolled_so_far",
        "gpa_change",
        "citizen_encoded",
        "ethnicity_encoded",
    ]

    X = pd.concat([
        df[feature_cols].reset_index(drop=True),
        school_dummies.reset_index(drop=True),
        ug_dummies.reset_index(drop=True),
        degtype_dummies.reset_index(drop=True),
    ], axis=1)

    # Fill any remaining NaNs in numeric features with column median
    X = X.fillna(X.median(numeric_only=True))

    y = df["at_risk"].reset_index(drop=True)

    print(f"\nFeature matrix shape: {X.shape}")
    print(f"Features: {X.columns.tolist()}")

    return X, y


def main():
    print("=" * 60)
    print("NJIT Student Dropout Prediction — Data Preparation")
    print("=" * 60)

    df = load_and_clean(DATA_PATH)
    X, y = engineer_features(df)

    # TEMPORAL SPLIT by term_year — train on past, test on future
    # Preserve term_year in df alongside X for splitting
    term_year_series = df["term_year"].reset_index(drop=True)

    train_mask = term_year_series < CUTOFF_YEAR
    test_mask  = term_year_series >= CUTOFF_YEAR

    X_train, y_train = X[train_mask], y[train_mask]
    X_test,  y_test  = X[test_mask],  y[test_mask]

    train_years = term_year_series[train_mask].unique()
    test_years  = term_year_series[test_mask].unique()
    print(f"\nTemporal split (cutoff year = {CUTOFF_YEAR}):")
    print(f"  Train years: {sorted(train_years)} -> {len(X_train):,} rows")
    print(f"  Test years:  {sorted(test_years)} -> {len(X_test):,} rows")
    print(f"  Train positive rate: {y_train.mean():.4f}")
    print(f"  Test positive rate:  {y_test.mean():.4f}")

    # Save splits
    joblib.dump(X_train, OUTPUT_DIR / "X_train.pkl")
    joblib.dump(X_test,  OUTPUT_DIR / "X_test.pkl")
    joblib.dump(y_train, OUTPUT_DIR / "y_train.pkl")
    joblib.dump(y_test,  OUTPUT_DIR / "y_test.pkl")
    joblib.dump(X.columns.tolist(), OUTPUT_DIR / "feature_names.pkl")

    print("\nSaved to outputs/: X_train, X_test, y_train, y_test, feature_names")
    print("Run train.py next.")


if __name__ == "__main__":
    main()
