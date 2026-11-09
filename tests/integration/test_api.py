"""
FastAPI Route Integration Tests.
Validates /health, /market/status, /agents, /signals, /paper/orders.
Uses the globally isolated test database environment.
"""

import pytest
from fastapi.testclient import TestClient

from indigo_quant.api.main import app
from indigo_quant.db.repository import init_db, seed_universe_and_accounts
from indigo_quant.db.session import SessionLocal


@pytest.fixture
def api_client(global_test_isolation):
    """Provide a TestClient connected to the isolated test database."""
    init_db()
    db = SessionLocal()
    seed_universe_and_accounts(db)
    db.close()
    return TestClient(app)


def test_api_health(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "INDIGO QUANT"
    assert data["active_strategy_accounts"] == 5


def test_api_market_status(api_client):
    response = api_client.get("/market/status")
    assert response.status_code == 200
    data = response.json()
    assert "regime" in data
    assert "is_market_open" in data


def test_api_agents_list(api_client):
    response = api_client.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 5
    ids = {a["id"] for a in agents}
    assert "trend_momentum" in ids
    assert "consensus" in ids


def test_api_signals_list(api_client):
    response = api_client.get("/signals")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_submit_paper_order(api_client):
    payload = {
        "account_id": "trend_momentum",
        "symbol": "INFY",
        "strategy_id": "trend_momentum",
        "order_side": "BUY",
        "order_type": "MARKET",
        "quantity": 10,
        "signal_price": 1600.0,
        "stop_price": 1540.0,
        "target_price": 1760.0,
        "signal_date": "2024-01-01",
        "validity_days": 2,
    }
    response = api_client.post("/paper/orders", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "order_id" in data
    assert data["symbol"] == "INFY"
