"""Evaluate the trained model against the test set and Onside Arena baseline.

Usage:
    python -m ml.evaluate
    python -m ml.evaluate --competition wc2026
"""

import argparse
import os
import pickle
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sqlalchemy import create_engine, text

from ml.features import build_features

MODEL_PATH = Path(__file__).parent.parent / "models" / "model_winner_predictor.pkl"


def _get_engine():
    load_dotenv()
    url = (
        f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}/{os.environ['POSTGRES_DB']}?sslmode=require"
    )
    return create_engine(url, pool_pre_ping=True)


def _onside_accuracy(conn) -> float | None:
    """Accuracy of the Onside Arena model on completed WC2026 matches."""
    try:
        sql = text("SELECT AVG((prediction_correct)::int) FROM gold.mart_predictions")
        result = conn.execute(sql).scalar()
        return float(result) if result is not None else None
    except Exception:
        return None


def evaluate(competition: str | None = None) -> None:
    if not MODEL_PATH.exists():
        print(f"Model not found at {MODEL_PATH}. Run: python -m ml.train")
        return

    with open(MODEL_PATH, "rb") as f:
        artifact = pickle.load(f)

    clf = artifact["model"]
    print(f"Model loaded — trained on {artifact['train_size']} matches")
    print(f"CV accuracy: {artifact['cv_accuracy_mean']:.3f} ± {artifact['cv_accuracy_std']:.3f}")

    engine = _get_engine()
    with engine.connect() as conn:
        X, y, meta = build_features(conn)
        onside_acc = _onside_accuracy(conn)

    # Filter by competition if requested
    if competition:
        mask = meta["competition_slug"] == competition
        X = X[mask]
        y = y[mask]
        meta = meta[mask]
        print(f"\nEvaluating on competition: {competition} ({len(X)} matches)")
    else:
        print(f"\nEvaluating on full dataset ({len(X)} matches)")

    if len(X) == 0:
        print("No matches to evaluate.")
        return

    y_pred = clf.predict(X)
    acc = accuracy_score(y, y_pred)
    classes = artifact["classes"]

    print(f"\nOverall accuracy: {acc:.3f} ({int(acc * len(y))}/{len(y)} correct)")

    if onside_acc is not None:
        delta = acc - onside_acc
        print(f"Onside Arena baseline: {onside_acc:.3f}  |  Delta: {delta:+.3f}")

    print("\nClassification report:")
    print(classification_report(y, y_pred, labels=classes, zero_division=0))

    print("Confusion matrix:")
    cm = confusion_matrix(y, y_pred, labels=classes)
    cm_df = pd.DataFrame(
        cm, index=[f"actual_{c}" for c in classes], columns=[f"pred_{c}" for c in classes]
    )
    print(cm_df.to_string())

    # Per-competition breakdown
    if competition is None:
        print("\nAccuracy by competition:")
        for comp, grp in meta.groupby("competition_slug"):
            idx = grp.index
            comp_acc = accuracy_score(y.loc[idx], clf.predict(X.loc[idx]))
            print(f"  {comp:<25} {comp_acc:.3f}  ({len(idx)} matches)")

    # Confidence analysis: how accurate is the model when it's most confident?
    proba = clf.predict_proba(X)
    max_proba = proba.max(axis=1)
    correct = y_pred == y.values

    print("\nAccuracy by model confidence:")
    thresholds = [0.4, 0.5, 0.6, 0.7]
    for t in thresholds:
        mask_t = max_proba >= t
        n = mask_t.sum()
        if n == 0:
            continue
        acc_t = correct[mask_t].mean()
        print(f"  confidence >= {t:.0%}: {acc_t:.3f} ({n} matches, {n / len(X):.0%} of dataset)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--competition", help="Evaluate on a specific competition slug")
    args = parser.parse_args()
    evaluate(args.competition)
