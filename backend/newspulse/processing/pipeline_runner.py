"""Pipeline runner: coordinates training, prediction generation, outcome reconciliation, and pipeline runs."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from ..calendar import MarketCalendar, UTC, to_iso
from ..db import dumps, loads, session
from ..formulas import forecast_errors, pct_change, signal_label
from ..modeling.models import LinearModel, train_models
from ..processing.features import (
    assert_no_look_ahead,
    build_rows,
    load_eligible_news,
    load_price_frames,
    truncate_frames,
)
from ..processing.ingestion_service import (
    ingest_financial_news,
    ingest_market_prices,
    process_unscored_articles,
)
from ..settings import Settings, Watchlist

logger = logging.getLogger(__name__)


def record_pipeline_run(conn, stage: str, status: str, input_count: int = 0, output_count: int = 0, error: str | None = None, details: dict | None = None) -> int:
    now_utc = datetime.now(UTC).isoformat()
    cursor = conn.execute(
        """INSERT INTO pipeline_runs (
            stage, started_at, finished_at, wall_started_at, wall_finished_at,
            status, input_count, output_count, error_summary, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING run_id""",
        (stage, now_utc, now_utc, now_utc, now_utc, status, input_count, output_count, error, dumps(details or {}))
    )
    return cursor.fetchone()[0]


def run_full_pipeline(settings: Settings, watchlist: Watchlist) -> dict[str, Any]:
    """Execute end-to-end data pipeline: ingest -> deduplicate & link -> score -> train -> predict -> reconcile."""
    start_time = datetime.now(UTC)
    calendar = MarketCalendar(
        watchlist.market.timezone,
        watchlist.market.cutoff_local,
        watchlist.market.holidays
    )
    results: dict[str, Any] = {
        "status": "running",
        "mode": settings.mode,
        "started_at": start_time.isoformat(),
        "stages": {},
    }

    with session(settings.db_path) as conn:
        run_id = record_pipeline_run(conn, "pipeline_start", "running")

    # 1. Price ingestion
    p_res = ingest_market_prices(settings, watchlist)
    if isinstance(p_res, dict):
        p_count = p_res.get("inserted", p_res.get("count", 0))
        success_symbols = p_res.get("success_symbols", [])
        failed_symbols = p_res.get("failed_symbols", {})
    else:
        p_count = int(p_res)
        success_symbols = [a.ticker for a in watchlist.assets]
        failed_symbols = {}

    results["stages"]["prices"] = {
        "count": p_count,
        "successful_symbols": success_symbols,
        "failed_symbols": failed_symbols,
    }

    # 2. News ingestion
    n_count = ingest_financial_news(settings, watchlist)
    results["stages"]["news"] = {"count": n_count}

    # 3. Sentiment scoring
    s_count = process_unscored_articles(settings)
    results["stages"]["sentiment"] = {"count": s_count}

    # 4. Feature generation & Model Training
    with session(settings.db_path) as conn:
        price_frames = load_price_frames(conn)
        news_frames = load_eligible_news(conn)
        asset_types = {a.asset_id: a.asset_type for a in watchlist.assets}

        # News coverage start
        earliest_news_row = conn.execute("SELECT MIN(published_at_utc) FROM articles WHERE is_duplicate=0").fetchone()
        earliest_news = earliest_news_row[0] if earliest_news_row and earliest_news_row[0] else None
        news_cov_start = datetime.fromisoformat(earliest_news.replace("Z", "+00:00")) if earliest_news else None

        # Build training rows across history
        hist_rows, exclusions = build_rows(
            price_frames, news_frames, watchlist.index.asset_id, asset_types,
            calendar, settings.recency_half_life_hours, news_cov_start,
            require_target=True
        )

        logger.info("Built %d historical feature rows for training (%d exclusions)", len(hist_rows), len(exclusions))

        uniq_sessions = sorted({r.reference_session for r in hist_rows if r.target_pct is not None})
        n_sessions = len(uniq_sessions)
        min_train = min(settings.min_train_sessions, max(5, int(n_sessions * 0.5)))
        min_test = min(settings.min_test_sessions, max(2, int(n_sessions * 0.15)))

        train_res = None
        if n_sessions >= (min_train + min_test + 1):
            # Train models
            train_res = train_models(hist_rows, min_train, min_test)
            results["stages"]["training"] = {
                "train_rows": train_res.row_counts["train"],
                "validation_rows": train_res.row_counts["validation"],
                "test_rows": train_res.row_counts["test"],
            }

            now_utc = datetime.now(UTC).isoformat()
            # Deactivate previous active models
            conn.execute("UPDATE model_runs SET active = 0")

            # Store models in model_runs
            for role, model in train_res.models.items():
                cur = conn.execute(
                    """INSERT INTO model_runs (
                        model_name, model_version, role, algorithm, data_origin,
                        features, params, split, exclusions, validation, trained_at, active
                    ) VALUES (?, ?, ?, 'Ridge', ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(model_name, model_version) DO UPDATE SET active = 1
                    RETURNING model_id""",
                    (
                        model.name, model.version, role, settings.mode,
                        dumps(model.features), dumps(model.params()),
                        dumps(train_res.split.describe()), dumps({"count": len(exclusions)}),
                        dumps(train_res.validation[role]), now_utc
                    )
                )
                m_row = cur.fetchone()
                model.model_id = m_row[0]

            # Populate holdout backtest predictions and outcomes
            for r in train_res.test_rows:
                for role, model in train_res.models.items():
                    est = model.predict_row(r.values)
                    lbl = signal_label(est, settings.threshold_pp)
                    pred_cur = conn.execute(
                        """INSERT INTO predictions (
                            asset_id, model_id, model_name, model_version, model_role,
                            origin, reference_session, prediction_session, cutoff_at,
                            reference_close, estimated_change_pct, label, threshold_pp,
                            feature_snapshot, input_freshness, data_status, data_origin, created_at
                        ) VALUES (?, ?, ?, ?, ?, 'holdout_backtest', ?, ?, ?, ?, ?, ?, ?, ?, '{}', 'resolved', ?, ?)
                        ON CONFLICT(asset_id, reference_session, model_name, model_version, origin) DO UPDATE SET
                            estimated_change_pct = excluded.estimated_change_pct
                        RETURNING prediction_id""",
                        (
                            r.asset_id, model.model_id, model.name, model.version, role,
                            r.reference_session.isoformat(), r.target_session.isoformat(),
                            to_iso(r.cutoff_at), r.reference_close, round(est, 4), lbl,
                            settings.threshold_pp, dumps(r.snapshot), settings.mode, now_utc
                        )
                    )
                    pred_id = pred_cur.fetchone()[0]

                    # Actual reconciliation
                    actual_pct = r.target_pct
                    signed_err, abs_err = forecast_errors(est, actual_pct)
                    conn.execute(
                        """INSERT INTO outcomes (
                            prediction_id, actual_session, actual_close, actual_change_pct,
                            signed_error_pct_points, absolute_error_pct_points, resolved_at, resolution_kind
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'holdout_backtest')
                        ON CONFLICT(prediction_id) DO UPDATE SET
                            actual_close = excluded.actual_close,
                            actual_change_pct = excluded.actual_change_pct,
                            signed_error_pct_points = excluded.signed_error_pct_points,
                            absolute_error_pct_points = excluded.absolute_error_pct_points,
                            resolved_at = excluded.resolved_at""",
                        (
                            pred_id, r.target_session.isoformat(), r.target_close or r.reference_close,
                            round(actual_pct, 4), round(signed_err, 4), round(abs_err, 4), now_utc
                        )
                    )

        # 5. Generate Current Live / Next-Session Predictions
        latest_session_row = conn.execute("SELECT MAX(session_date) FROM daily_prices").fetchone()
        latest_sess = date.fromisoformat(latest_session_row[0]) if latest_session_row and latest_session_row[0] else None

        if latest_sess:
            next_sess = calendar.next_session(latest_sess)
            cutoff_dt = calendar.cutoff_at(latest_sess)
            now_utc = datetime.now(UTC).isoformat()

            # Freshness / stale input detection
            today_local = datetime.now(calendar.tz).date()
            is_stale = (today_local - latest_sess).days > settings.price_max_age_days
            data_status = "stale" if is_stale else "ready"

            # Load active models
            active_models = {}
            for row in conn.execute("SELECT * FROM model_runs WHERE active = 1").fetchall():
                active_models[row["role"]] = LinearModel.from_record(row)

            if active_models:
                # Build rows for the latest reference session only
                current_rows, _ = build_rows(
                    price_frames, news_frames, watchlist.index.asset_id, asset_types,
                    calendar, settings.recency_half_life_hours, news_cov_start,
                    sessions={latest_sess}, require_target=False
                )

                # Store forecast run
                fr_cur = conn.execute(
                    """INSERT INTO forecast_runs (
                        reference_session, prediction_session, cutoff_at, generated_at,
                        status, data_origin
                    ) VALUES (?, ?, ?, ?, 'published', ?) RETURNING forecast_run_id""",
                    (latest_sess.isoformat(), next_sess.isoformat(), to_iso(cutoff_dt), now_utc, settings.mode)
                )
                forecast_run_id = fr_cur.fetchone()[0]

                pred_count = 0
                for cr in current_rows:
                    for role, model in active_models.items():
                        if is_stale:
                            est = None
                            lbl = "Unavailable"
                        else:
                            est = model.predict_row(cr.values)
                            lbl = signal_label(est, settings.threshold_pp)

                        conn.execute(
                            """INSERT INTO predictions (
                                forecast_run_id, asset_id, model_id, model_name, model_version,
                                model_role, origin, reference_session, prediction_session,
                                cutoff_at, reference_close, estimated_change_pct, label,
                                threshold_pp, feature_snapshot, input_freshness, data_status,
                                data_origin, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, 'forecast', ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?, ?)
                            ON CONFLICT(asset_id, reference_session, model_name, model_version, origin) DO UPDATE SET
                                estimated_change_pct = excluded.estimated_change_pct,
                                label = excluded.label,
                                feature_snapshot = excluded.feature_snapshot,
                                data_status = excluded.data_status,
                                created_at = excluded.created_at""",
                            (
                                forecast_run_id, cr.asset_id, model.model_id, model.name,
                                model.version, role, latest_sess.isoformat(), next_sess.isoformat(),
                                to_iso(cr.cutoff_at), cr.reference_close, round(est, 4) if est is not None else None, lbl,
                                settings.threshold_pp, dumps(cr.snapshot), data_status, settings.mode, now_utc
                            )
                        )
                        pred_count += 1
                results["stages"]["predictions"] = {"count": pred_count, "session": next_sess.isoformat(), "status": data_status}

        # 6. Reconcile any pending predictions
        reconciled_count = reconcile_pending_predictions(settings)
        results["stages"]["reconciled"] = {"count": reconciled_count}

        end_time = datetime.now(UTC)
        duration = round((end_time - start_time).total_seconds(), 2)
        overall_status = "success" if not failed_symbols else ("partial_success" if success_symbols else "failed")
        results["status"] = overall_status
        results["finished_at"] = end_time.isoformat()
        results["duration_seconds"] = duration

        record_pipeline_run(conn, "full_pipeline", overall_status, input_count=p_count + n_count, output_count=results.get("stages", {}).get("predictions", {}).get("count", 0), details=results)

    logger.info("Pipeline completed with status %s in %.2fs: %s", overall_status, duration, results)
    return results


def reconcile_pending_predictions(settings: Settings) -> int:
    """Reconcile pending forecast predictions once actual next-session prices arrive in the database."""
    reconciled = 0
    now_utc = datetime.now(UTC).isoformat()
    with session(settings.db_path) as conn:
        pending = conn.execute(
            """SELECT p.prediction_id, p.asset_id, p.reference_close, p.estimated_change_pct,
                      p.prediction_session, dp.close as actual_close
               FROM predictions p
               JOIN daily_prices dp ON dp.asset_id = p.asset_id AND dp.session_date = p.prediction_session
               LEFT JOIN outcomes o ON o.prediction_id = p.prediction_id
               WHERE o.prediction_id IS NULL AND p.origin = 'forecast' AND dp.close IS NOT NULL"""
        ).fetchall()

        for r in pending:
            ref_c = r["reference_close"]
            act_c = r["actual_close"]
            act_pct = pct_change(ref_c, act_c)
            if act_pct is not None:
                signed_err, abs_err = forecast_errors(r["estimated_change_pct"], act_pct)
                conn.execute(
                    """INSERT INTO outcomes (
                        prediction_id, actual_session, actual_close, actual_change_pct,
                        signed_error_pct_points, absolute_error_pct_points, resolved_at, resolution_kind
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'observed')""",
                    (
                        r["prediction_id"], r["prediction_session"], act_c,
                        round(act_pct, 4), round(signed_err, 4), round(abs_err, 4), now_utc
                    )
                )
                reconciled += 1

    logger.info("Reconciled %d pending predictions", reconciled)
    return reconciled
