"""
predict.py — Score a new student record using the best trained model.

Usage:
  python predict.py  (runs a demo with sample student data)

Or import and call predict_student() from another script.
"""

import joblib
import pandas as pd
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "outputs"


def load_model():
    model      = joblib.load(OUTPUT_DIR / "best_model.pkl")
    model_name = joblib.load(OUTPUT_DIR / "best_model_name.pkl")
    feat_names = joblib.load(OUTPUT_DIR / "feature_names.pkl")
    return model, model_name, feat_names


def build_feature_row(student: dict, feat_names: list) -> pd.DataFrame:
    """
    Convert a student dict into a feature row matching the training schema.

    Expected student dict keys:
      pell           : 'Y', 'N', or 'Unknown'
      firstgen       : 'Y', 'N', or 'Unknown'
      gender         : 'Female' or 'Male'
      term_type      : 'Spring' or 'Fall'
      regstat        : 1, 2, 3, or 4
      accumgpa       : float
      creditenr      : int
      term_year      : int
      terms_enrolled_so_far : int  (how many terms the student has been enrolled)
      gpa_change     : float (GPA change from prior term, 0 for first term)
      citizen        : 1, 2, 3, or 4
      ethnicmultirace: int (1-27)
      school         : 'AD', 'CC', 'EN', 'SL', or 'SM'
      u_g            : 'U', 'G', or 'D'
      degtype        : 'BA', 'BS', 'MS', 'MBA', 'PHD', 'CRT', etc.
    """
    row = {}

    # Scalar features
    row["pell_encoded"]          = {"Y": 1.0, "N": 0.0, "Unknown": 0.5}.get(student.get("pell", "Unknown"), 0.5)
    row["firstgen_encoded"]      = {"Y": 1.0, "N": 0.0, "Unknown": 0.5}.get(student.get("firstgen", "Unknown"), 0.5)
    row["gender_encoded"]        = 1 if student.get("gender") == "Female" else 0
    row["term_season_encoded"]   = 1 if student.get("term_type") == "Spring" else 0
    row["regstat_encoded"]       = float(student.get("regstat", 4))
    row["accumgpa"]              = float(student.get("accumgpa", 0.0))
    row["creditenr"]             = float(student.get("creditenr", 12))
    row["term_year"]             = float(student.get("term_year", 2020))
    row["terms_enrolled_so_far"] = float(student.get("terms_enrolled_so_far", 1))
    row["gpa_change"]            = float(student.get("gpa_change", 0.0))
    row["citizen_encoded"]       = float(student.get("citizen", 4))
    row["ethnicity_encoded"]     = float(student.get("ethnicmultirace", 0))

    # One-hot: school
    for s in ["AD", "CC", "EN", "SL", "SM"]:
        row[f"school_{s}"] = 1 if student.get("school") == s else 0

    # One-hot: u_g
    for ug in ["D", "G", "U"]:
        row[f"ug_{ug}"] = 1 if student.get("u_g") == ug else 0

    # One-hot: degtype (use all that appear in feat_names)
    deg_cols = [f for f in feat_names if f.startswith("deg_")]
    for col in deg_cols:
        deg_val = col.replace("deg_", "")
        row[col] = 1 if student.get("degtype") == deg_val else 0

    # Build DataFrame aligned to training features
    df = pd.DataFrame([row])
    for col in feat_names:
        if col not in df.columns:
            df[col] = 0
    df = df[feat_names]

    return df


def predict_student(student: dict) -> dict:
    """
    Predict dropout risk for a single student record.
    Returns: {model, dropout_probability, at_risk, risk_level}
    """
    model, model_name, feat_names = load_model()
    X = build_feature_row(student, feat_names)
    prob = model.predict_proba(X)[0, 1]
    pred = int(prob >= 0.5)

    risk_level = (
        "High"   if prob >= 0.70 else
        "Medium" if prob >= 0.40 else
        "Low"
    )

    return {
        "model":               model_name,
        "dropout_probability": round(float(prob), 4),
        "at_risk":             pred,
        "risk_level":          risk_level,
    }


def main():
    print("=" * 60)
    print("NJIT Student Dropout Prediction — Demo")
    print("=" * 60)

    # Sample student 1: low-risk profile
    student_low_risk = {
        "pell": "N", "firstgen": "N", "gender": "Male",
        "term_type": "Fall", "regstat": 4, "accumgpa": 3.5,
        "creditenr": 15, "term_year": 2022, "terms_enrolled_so_far": 6,
        "gpa_change": 0.1, "citizen": 1, "ethnicmultirace": 26,
        "school": "EN", "u_g": "U", "degtype": "BS",
    }

    # Sample student 2: high-risk profile
    student_high_risk = {
        "pell": "Y", "firstgen": "Y", "gender": "Female",
        "term_type": "Spring", "regstat": 3, "accumgpa": 1.8,
        "creditenr": 6, "term_year": 2023, "terms_enrolled_so_far": 2,
        "gpa_change": -0.4, "citizen": 2, "ethnicmultirace": 6,
        "school": "SL", "u_g": "G", "degtype": "MS",
    }

    for label, student in [("Low-Risk Student", student_low_risk),
                             ("High-Risk Student", student_high_risk)]:
        result = predict_student(student)
        print(f"\n{label}:")
        print(f"  Model:               {result['model']}")
        print(f"  Dropout Probability: {result['dropout_probability']:.1%}")
        print(f"  At-Risk:             {'YES' if result['at_risk'] else 'NO'}")
        print(f"  Risk Level:          {result['risk_level']}")


if __name__ == "__main__":
    main()
