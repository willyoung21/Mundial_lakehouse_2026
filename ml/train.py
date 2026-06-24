"""Train the WC2026 match outcome predictor.

Model: Random Forest classifier (3 classes: home_win, draw, away_win).
Baseline — the value is in the end-to-end pipeline, not the accuracy.

Temporal split:
  - Train: StatsBomb historical (WC2022, Copa América, Euro 2020/2024)
           + WC2026 group stage completed matches
  - Test:  WC2026 knockout stage (empty until late June 2026)
  - Cross-val: 5-fold StratifiedKFold on training set for hyperparameter tuning

Output: models/model_winner_predictor.pkl  (RandomForestClassifier + metadata)

Usage:
    python -m ml.train
"""

import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sqlalchemy import create_engine

from ml.features import FEATURE_COLS, build_features

MODEL_DIR = Path(__file__).parent.parent / "models"
MODEL_PATH = MODEL_DIR / "model_winner_predictor.pkl"

CLASSES = ["home_win", "draw", "away_win"]


def _get_engine():
    load_dotenv()
    url = (
        f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}/{os.environ['POSTGRES_DB']}?sslmode=require"
    )
    return create_engine(url, pool_pre_ping=True)


def train() -> None:
    print("Loading features from Gold layer...")
    engine = _get_engine()
    with engine.connect() as conn:
        X, y, meta = build_features(conn)

    print(f"Dataset: {len(X)} matches, {len(FEATURE_COLS)} features")
    print(f"Class distribution:\n{y.value_counts().to_string()}")

    # Temporal split: WC2026 knockout as test (empty until late June)
    is_wc2026_knockout = (meta["competition_slug"] == "wc2026") & (meta["stage"] != "") & \
                         ~meta["stage"].str.startswith("Group", na=False)

    X_test  = X[is_wc2026_knockout]
    y_test  = y[is_wc2026_knockout]
    X_train = X[~is_wc2026_knockout]
    y_train = y[~is_wc2026_knockout]

    print(f"\nSplit — train: {len(X_train)}, test (WC2026 knockouts): {len(X_test)}")

    # Cross-validation on training set
    clf = RandomForestClassifier(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=5,
        class_weight="balanced",   # compensates for fewer draw samples
        random_state=42,
        n_jobs=-1,
    )

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(clf, X_train, y_train, cv=cv, scoring="accuracy")
    print(f"\n5-fold CV accuracy: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
    print(f"  per fold: {[round(s, 3) for s in cv_scores]}")

    # Train on full training set
    clf.fit(X_train, y_train)

    train_acc = accuracy_score(y_train, clf.predict(X_train))
    print(f"Train accuracy: {train_acc:.3f}")

    if len(X_test) > 0:
        test_acc = accuracy_score(y_test, clf.predict(X_test))
        print(f"Test accuracy  (WC2026 knockouts): {test_acc:.3f}")
        print("\nClassification report (test):")
        print(classification_report(y_test, clf.predict(X_test), labels=CLASSES, zero_division=0))
    else:
        print("No WC2026 knockout matches yet — test set is empty.")

    # Feature importance
    importance = pd.Series(clf.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
    print("\nTop feature importances:")
    print(importance.head(8).to_string())

    # Save model + metadata
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": clf,
        "feature_cols": FEATURE_COLS,
        "classes": clf.classes_.tolist(),
        "train_size": len(X_train),
        "cv_accuracy_mean": float(cv_scores.mean()),
        "cv_accuracy_std": float(cv_scores.std()),
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(artifact, f)

    print(f"\nModel saved to {MODEL_PATH}")


if __name__ == "__main__":
    train()
