from fastapi.testclient import TestClient
from newspulse.api import app

def test_api_overview():
    with TestClient(app) as client:
        resp = client.get("/api/v1/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "index" in data
        assert "horizon" in data
        assert "threshold_pp" in data
        assert data["threshold_pp"] == 0.25

def test_api_stocks():
    with TestClient(app) as client:
        resp = client.get("/api/v1/stocks")
        assert resp.status_code == 200
        stocks = resp.json()
        assert isinstance(stocks, list)
        if stocks:
            # Check descending absolute estimate ranking
            estimates = [abs(s["estimate"]) for s in stocks if s["estimate"] is not None]
            assert estimates == sorted(estimates, reverse=True)

def test_api_metrics():
    with TestClient(app) as client:
        resp = client.get("/api/v1/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert len(data["metrics"]) == 2  # baseline and news_aware

def test_api_status():
    with TestClient(app) as client:
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "counts" in data
        assert "freshness" in data

def test_api_mode_switching():
    with TestClient(app) as client:
        # Sample mode check
        sample_resp = client.get("/api/v1/overview?mode=sample")
        assert sample_resp.status_code == 200
        sample_data = sample_resp.json()
        assert sample_data["data_origin"] == "sample"
        assert sample_data["index"]["ticker"] == "DM100"

        # Live mode check
        live_resp = client.get("/api/v1/overview?mode=live")
        assert live_resp.status_code == 200
        live_data = live_resp.json()
        assert live_data["data_origin"] == "live"
        assert live_data["index"]["ticker"] == "^NSEI"

def test_api_refresh_security():
    with TestClient(app) as client:
        # Missing token -> 401
        bad_resp = client.post("/api/v1/jobs/refresh", headers={"X-Operator-Token": "wrong-token"})
        assert bad_resp.status_code == 401

        # Valid dev token -> 200
        good_resp = client.post("/api/v1/jobs/refresh?mode=sample", headers={"X-Operator-Token": "newspulse-dev-token"})
        assert good_resp.status_code == 200
        res = good_resp.json()
        assert res["message"] == "Pipeline executed successfully"
        assert "results" in res
