"""
evaluate.py — Generate evaluation plots and feature importance for best model.

Outputs:
  outputs/roc_curve.png
  outputs/confusion_matrix.png
  outputs/feature_importance.png
  outputs/shap_summary.png  (if model supports SHAP)
"""

import os
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import seaborn as sns
from pathlib import Path
from dotenv import load_dotenv
from sklearn.metrics import (
    roc_auc_score, roc_curve,
    confusion_matrix, ConfusionMatrixDisplay,
)

matplotlib.use("Agg")  # non-interactive backend

load_dotenv(Path(__file__).parent / ".env")

OUTPUT_DIR = Path(__file__).parent / os.getenv("OUTPUT_DIR", "outputs")


def load_artifacts():
    model       = joblib.load(OUTPUT_DIR / "best_model.pkl")
    model_name  = joblib.load(OUTPUT_DIR / "best_model_name.pkl")
    X_test      = joblib.load(OUTPUT_DIR / "X_test.pkl")
    y_test      = joblib.load(OUTPUT_DIR / "y_test.pkl")
    feat_names  = joblib.load(OUTPUT_DIR / "feature_names.pkl")
    return model, model_name, X_test, y_test, feat_names


def plot_roc_curve(model, model_name, X_test, y_test):
    y_prob = model.predict_proba(X_test)[:, 1]
    auc    = roc_auc_score(y_test, y_prob)
    fpr, tpr, _ = roc_curve(y_test, y_prob)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(fpr, tpr, color="#E74C3C", lw=2,
            label=f"{model_name} (AUC = {auc:.4f})")
    ax.plot([0, 1], [0, 1], color="gray", lw=1, linestyle="--", label="Random Classifier")
    ax.set_xlabel("False Positive Rate", fontsize=13)
    ax.set_ylabel("True Positive Rate", fontsize=13)
    ax.set_title("ROC Curve — Student Dropout Prediction", fontsize=14, fontweight="bold")
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "roc_curve.png", dpi=150)
    plt.close(fig)
    print(f"  Saved: roc_curve.png  (AUC = {auc:.4f})")


def plot_confusion_matrix(model, X_test, y_test):
    y_pred = model.predict(X_test)
    cm     = confusion_matrix(y_test, y_pred)

    fig, ax = plt.subplots(figsize=(7, 6))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm,
                                  display_labels=["Returned (0)", "At-Risk (1)"])
    disp.plot(ax=ax, colorbar=False, cmap="Blues")
    ax.set_title("Confusion Matrix — Student Dropout Prediction",
                 fontsize=13, fontweight="bold", pad=12)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "confusion_matrix.png", dpi=150)
    plt.close(fig)
    print("  Saved: confusion_matrix.png")


def plot_feature_importance(model, model_name, feat_names):
    # Try standard feature_importances_ first (tree-based models)
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        importances = np.abs(model.coef_[0])
    else:
        print("  Skipping feature importance: model type not supported.")
        return

    feat_df = pd.DataFrame({
        "Feature":    feat_names,
        "Importance": importances,
    }).sort_values("Importance", ascending=True).tail(20)

    fig, ax = plt.subplots(figsize=(10, 8))
    bars = ax.barh(feat_df["Feature"], feat_df["Importance"], color="#3498DB", alpha=0.85)
    ax.set_xlabel("Importance Score", fontsize=13)
    ax.set_title(f"Top 20 Feature Importances — {model_name}",
                 fontsize=14, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "feature_importance.png", dpi=150)
    plt.close(fig)
    print("  Saved: feature_importance.png")


def plot_shap(model, model_name, X_test, feat_names):
    try:
        import shap
        # Subsample for speed
        X_sample = X_test.iloc[:500] if len(X_test) > 500 else X_test

        if "XGBoost" in model_name or "LightGBM" in model_name or "Forest" in model_name:
            explainer  = shap.TreeExplainer(model)
            shap_vals  = explainer.shap_values(X_sample)
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[1]  # class 1 for binary
        else:
            explainer = shap.LinearExplainer(model, X_sample)
            shap_vals = explainer.shap_values(X_sample)

        fig, ax = plt.subplots(figsize=(10, 8))
        shap.summary_plot(shap_vals, X_sample,
                          feature_names=feat_names,
                          show=False, plot_size=(10, 8))
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / "shap_summary.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("  Saved: shap_summary.png")
    except Exception as e:
        print(f"  SHAP plot skipped: {e}")


def plot_model_comparison():
    comp_path = OUTPUT_DIR / "model_comparison.csv"
    if not comp_path.exists():
        return
    comp = pd.read_csv(comp_path).sort_values("Test AUC", ascending=True)

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = ["#3498DB", "#2ECC71", "#E67E22", "#E74C3C"]
    bars = ax.barh(comp["Model"], comp["Test AUC"],
                   color=colors[:len(comp)], alpha=0.85)
    for bar, val in zip(bars, comp["Test AUC"]):
        ax.text(bar.get_width() - 0.005, bar.get_y() + bar.get_height() / 2,
                f"{val:.4f}", va="center", ha="right", color="white",
                fontweight="bold", fontsize=12)
    ax.set_xlabel("Test AUC-ROC", fontsize=13)
    ax.set_title("Model Comparison — Test AUC-ROC", fontsize=14, fontweight="bold")
    ax.set_xlim(0.5, 1.0)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "model_comparison.png", dpi=150)
    plt.close(fig)
    print("  Saved: model_comparison.png")


def main():
    print("=" * 60)
    print("NJIT Student Dropout Prediction — Evaluation")
    print("=" * 60)

    model, model_name, X_test, y_test, feat_names = load_artifacts()
    print(f"Best model: {model_name}")
    print(f"Test set size: {len(X_test):,}")

    print("\nGenerating plots...")
    plot_roc_curve(model, model_name, X_test, y_test)
    plot_confusion_matrix(model, X_test, y_test)
    plot_feature_importance(model, model_name, feat_names)
    plot_shap(model, model_name, X_test, feat_names)
    plot_model_comparison()

    print("\nAll evaluation outputs saved to outputs/")


if __name__ == "__main__":
    main()
