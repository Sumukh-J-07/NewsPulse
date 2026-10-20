import pytest
from newspulse.formulas import pct_change, signal_label, forecast_errors, mae, directional_accuracy, evaluate

def test_pct_change():
    assert pct_change(100.0, 101.25) == pytest.approx(1.25)
    assert pct_change(100.0, 98.5) == pytest.approx(-1.5)
    assert pct_change(100.0, 100.0) == 0.0
    assert pct_change(None, 100.0) is None
    assert pct_change(100.0, None) is None
    assert pct_change(0.0, 100.0) is None

def test_signal_label_deadband():
    assert signal_label(0.25, threshold_pp=0.25) == "neutral"
    assert signal_label(-0.25, threshold_pp=0.25) == "neutral"
    assert signal_label(0.2501, threshold_pp=0.25) == "bullish"
    assert signal_label(-0.2501, threshold_pp=0.25) == "bearish"
    assert signal_label(None) is None

def test_forecast_errors():
    signed, absolute = forecast_errors(1.20, 0.80)
    assert signed == pytest.approx(0.40)
    assert absolute == pytest.approx(0.40)

    signed_neg, absolute_neg = forecast_errors(-1.20, -0.80)
    assert signed_neg == pytest.approx(-0.40)
    assert absolute_neg == pytest.approx(0.40)

    assert forecast_errors(1.20, None) == (None, None)

def test_metrics_evaluation():
    pairs = [(1.2, 0.8), (-1.5, -0.9), (0.2, -0.1)]
    assert mae(pairs) == pytest.approx((0.4 + 0.6 + 0.3) / 3.0)
    # Signs: (1, 1) -> match, (-1, -1) -> match, (1, -1) -> mismatch: 2/3
    assert directional_accuracy(pairs) == pytest.approx(2.0 / 3.0)
