"""Modeling: price-only baseline and news-aware model (FR-09, FR-10, SRS 4.3).

Both models are ridge regressions (scikit-learn ``StandardScaler`` + ``Ridge``)
predicting the next-session percent change directly. They share:
  * the same target and the same eligible rows,
  * the same chronological split by reference session (60 % train, 20 % validation,
    20 % held-out test; never shuffled),
  * the same tuning protocol: ``alpha`` chosen by validation MAE using a model fit on
    the training period only (scaler fit on training rows only). The chosen model is
    refit on train + validation and only then applied once to the frozen test period.

The baseline uses price-history features only; the news-aware model adds the news
features. Learned parameters (scaler mean/scale, coefficients, intercept) are stored
as JSON in ``model_runs`` so forecasts are reproducible without pickles.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .. import formulas
from ..processing.features import NEWS_FEATURES, PRICE_FEATURES, FeatureRow

ALPHA_GRID = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
SPLIT_FRACTIONS = (0.6, 0.2, 0.2)
MODEL_SPECS = {
    "baseline": {"name": "baseline_price_ridge", "features": PRICE_FEATURES},
    "news_aware": {"name": "news_aware_ridge", "features": PRICE_FEATURES + NEWS_FEATURES},
}
CODE_VERSION = "1.0.0"


class InsufficientDataError(RuntimeError):
    """Not enough chronological data for a valid train/validation/test split."""


@dataclass
class LinearModel:
    name: str
    role: str
    features: list[str]
    mean: list[float]
    scale: list[float]
    coef: list[float]
    intercept: float
    alpha: float
    version: str = ""
    model_id: int | None = None

    def predict(self, X: np.ndarray) -> np.ndarray:
        Z = (np.asarray(X, dtype=float) - np.asarray(self.mean)) / np.asarray(self.scale)
        return Z @ np.asarray(self.coef) + self.intercept

    def predict_row(self, values: dict[str, float]) -> float:
        return float(self.predict(np.array([[values[f] for f in self.features]]))[0])

    def params(self) -> dict:
        return {"mean": self.mean, "scale": self.scale, "coef": self.coef, "intercept": self.intercept,
                "alpha": self.alpha}

    @classmethod
    def from_record(cls, rec) -> "LinearModel":
        p = json.loads(rec["params"])
        return cls(name=rec["model_name"], role=rec["role"], features=json.loads(rec["features"]),
                   mean=p["mean"], scale=p["scale"], coef=p["coef"], intercept=p["intercept"], alpha=p["alpha"],
                   version=rec["model_version"], model_id=rec["model_id"])


@dataclass
class Split:
    train: list[date]
    validation: list[date]
    test: list[date]

    def describe(self) -> dict:
        def rng(s):
            return {"start": s[0].isoformat(), "end": s[-1].isoformat(), "sessions": len(s)} if s else None
        return {"method": "chronological by reference session; no shuffling",
                "fractions": SPLIT_FRACTIONS, "train": rng(self.train), "validation": rng(self.validation),
                "test": rng(self.test)}


def chronological_split(sessions: Sequence[date], min_train: int, min_test: int) -> Split:
    uniq = sorted(set(sessions))
    n = len(uniq)
    n_train = int(n * SPLIT_FRACTIONS[0])
    n_val = int(n * SPLIT_FRACTIONS[1])
    n_test = n - n_train - n_val
    if n_train < min_train or n_test < min_test or n_val < 1:
        raise InsufficientDataError(
            f"{n} eligible sessions give train={n_train}, validation={n_val}, test={n_test}; "
            f"need train>={min_train}, validation>=1, test>={min_test}")
    split = Split(uniq[:n_train], uniq[n_train:n_train + n_val], uniq[n_train + n_val:])
    assert split.train[-1] < split.validation[0] <= split.validation[-1] < split.test[0]
    return split


def _matrix(rows: Sequence[FeatureRow], features: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    X = np.array([[r.values[f] for f in features] for r in rows], dtype=float)
    y = np.array([r.target_pct for r in rows], dtype=float)
    if not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ValueError("non-finite feature or target values reached the model")
    return X, y


def fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float, name: str, role: str, features: list[str]) -> LinearModel:
    scaler = StandardScaler().fit(X)
    scale = np.where(scaler.scale_ == 0, 1.0, scaler.scale_)
    reg = Ridge(alpha=alpha).fit((X - scaler.mean_) / scale, y)
    model = LinearModel(name=name, role=role, features=list(features), mean=scaler.mean_.tolist(),
                        scale=scale.tolist(), coef=reg.coef_.tolist(), intercept=float(reg.intercept_), alpha=alpha)
    digest = hashlib.sha256(json.dumps(model.params(), sort_keys=True).encode()).hexdigest()[:8]
    model.version = f"{CODE_VERSION}+{digest}"
    return model


@dataclass
class TrainingResult:
    split: Split
    models: dict[str, LinearModel]
    validation: dict[str, dict]
    test_rows: list[FeatureRow]
    test_predictions: dict[str, list[float]]
    row_counts: dict[str, int] = field(default_factory=dict)


def train_models(rows: Sequence[FeatureRow], min_train: int, min_test: int) -> TrainingResult:
    rows = [r for r in rows if r.target_pct is not None]
    split = chronological_split([r.reference_session for r in rows], min_train, min_test)
    train_s, val_s, test_s = set(split.train), set(split.validation), set(split.test)
    train = [r for r in rows if r.reference_session in train_s]
    val = [r for r in rows if r.reference_session in val_s]
    test = sorted((r for r in rows if r.reference_session in test_s), key=lambda r: (r.reference_session, r.asset_id))

    models, validation, preds = {}, {}, {}
    for role, spec in MODEL_SPECS.items():
        feats = spec["features"]
        Xtr, ytr = _matrix(train, feats)
        Xva, yva = _matrix(val, feats)
        scores = {}
        for alpha in ALPHA_GRID:
            m = fit_ridge(Xtr, ytr, alpha, spec["name"], role, feats)
            scores[alpha] = formulas.mae(zip(m.predict(Xva).tolist(), yva.tolist()))
        best = min(ALPHA_GRID, key=lambda a: (scores[a], a))
        Xtv = np.vstack([Xtr, Xva])
        ytv = np.concatenate([ytr, yva])
        final = fit_ridge(Xtv, ytv, best, spec["name"], role, feats)
        models[role] = final
        validation[role] = {"alpha_grid": list(ALPHA_GRID), "validation_mae_pp": {str(a): scores[a] for a in ALPHA_GRID},
                            "selected_alpha": best, "refit_on": "train+validation"}
        Xte, _ = _matrix(test, feats)
        preds[role] = final.predict(Xte).tolist()
    return TrainingResult(split=split, models=models, validation=validation, test_rows=test,
                          test_predictions=preds,
                          row_counts={"train": len(train), "validation": len(val), "test": len(test)})
