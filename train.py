"""
train.py — Train and compare multiple models for student dropout prediction.

Models:
  1. Logistic Regression (baseline, interpretable)
  2. Random Forest
  3. XGBoost
  4. LightGBM

Primary metric: AUC-ROC (handles class imbalance).
All models use class_weight='balanced' or equivalent.
Best model saved to outputs/best_model.pkl.
"""

import os
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import roc_auc_score, classification_report
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

load_dotenv(Path(__file__).parent / ".env")

OUTPUT_DIR   = Path(__file__).parent / os.getenv("OUTPUT_DIR", "outputs")
RANDOM_STATE = int(os.getenv("RANDOM_STATE", 42))
CV_FOLDS     = int(os.getenv("CV_FOLDS", 5))


def load_data():
    X_train = joblib.load(OUTPUT_DIR / "X_train.pkl")
    X_test  = joblib.load(OUTPUT_DIR / "X_test.pkl")
    y_train = joblib.load(OUTPUT_DIR / "y_train.pkl")
    y_test  = joblib.load(OUTPUT_DIR / "y_test.pkl")
    return X_train, X_test, y_train, y_test


def get_models():
    pos_weight = 10  # ~8% positive class → ~12x imbalance, use 10 as conservative weight

    return {
        "Logistic Regression": LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=RANDOM_STATE,
            solver="lbfgs",
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced",
            max_depth=10,
            min_samples_leaf=20,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
        "XGBoost": XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            scale_pos_weight=pos_weight,
            eval_metric="auc",
            random_state=RANDOM_STATE,
            verbosity=0,
        ),
        "LightGBM": LGBMClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            scale_pos_weight=pos_weight,
            random_state=RANDOM_STATE,
            verbose=-1,
        ),
    }


def train_and_evaluate(models, X_train, X_test, y_train, y_test):
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    results = []

    for name, model in models.items():
        print(f"\nTraining: {name}")

        # Cross-validation AUC on train set
        cv_scores = cross_val_score(
            model, X_train, y_train,
            cv=cv, scoring="roc_auc", n_jobs=-1
        )
        print(f"  CV AUC: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

        # Fit on full train, evaluate on test
        model.fit(X_train, y_train)
        y_prob = model.predict_proba(X_test)[:, 1]
        test_auc = roc_auc_score(y_test, y_prob)
        print(f"  Test AUC: {test_auc:.4f}")

        results.append({
            "Model": name,
            "CV AUC (mean)": round(cv_scores.mean(), 4),
            "CV AUC (std)":  round(cv_scores.std(),  4),
            "Test AUC":      round(test_auc, 4),
            "model_obj":     model,
        })

    return results


def main():
    print("=" * 60)
    print("NJIT Student Dropout Prediction — Model Training")
    print("=" * 60)

    X_train, X_test, y_train, y_test = load_data()
    print(f"Train: {X_train.shape} | Test: {X_test.shape}")
    print(f"Positive rate — Train: {y_train.mean():.4f} | Test: {y_test.mean():.4f}")

    models  = get_models()
    results = train_and_evaluate(models, X_train, X_test, y_train, y_test)

    # Comparison table
    comparison = pd.DataFrame([
        {k: v for k, v in r.items() if k != "model_obj"}
        for r in results
    ]).sort_values("Test AUC", ascending=False)

    print("\n" + "=" * 60)
    print("MODEL COMPARISON")
    print("=" * 60)
    print(comparison.to_string(index=False))

    # Save comparison table
    comparison.to_csv(OUTPUT_DIR / "model_comparison.csv", index=False)

    # Best model by test AUC
    best = max(results, key=lambda r: r["Test AUC"])
    best_model = best["model_obj"]
    best_name  = best["Model"]

    print(f"\nBest model: {best_name} (Test AUC = {best['Test AUC']:.4f})")

    # Full classification report for best model
    y_pred = best_model.predict(X_test)
    print("\nClassification Report (best model):")
    print(classification_report(y_test, y_pred, target_names=["Returned (0)", "At-Risk (1)"]))

    # Save all fitted models and best
    for r in results:
        safe_name = r["Model"].lower().replace(" ", "_")
        joblib.dump(r["model_obj"], OUTPUT_DIR / f"model_{safe_name}.pkl")

    joblib.dump(best_model, OUTPUT_DIR / "best_model.pkl")
    joblib.dump(best_name,  OUTPUT_DIR / "best_model_name.pkl")

    with open(OUTPUT_DIR / "classification_report.txt", "w") as f:
        f.write(f"Best Model: {best_name}\n")
        f.write(f"Test AUC: {best['Test AUC']:.4f}\n\n")
        f.write(classification_report(y_test, y_pred, target_names=["Returned (0)", "At-Risk (1)"]))

    print(f"\nSaved: best_model.pkl, model_comparison.csv, classification_report.txt")
    print("Run evaluate.py next.")


if __name__ == "__main__":
    main()
