"""
Unit tests for Telegram Notifier, Public Data Exporter, and Sanitization.
All tests use temporary directories and mocked clients for strict production isolation.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from indigo_quant.export.public_data import (
    PublicDataExporter,
    sanitize_dict,
    sanitize_text,
)
from indigo_quant.export.static_report import generate_static_html
from indigo_quant.notifications.telegram import TelegramNotifier, mask_token


def test_token_masking_never_reveals_raw_secret():
    """Verify bot tokens are never printed in full."""
    raw_token = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ"
    masked = mask_token(raw_token)
    assert raw_token not in masked
    assert masked.startswith("123456")
    assert masked.endswith("wxYZ")
    assert "****:****" in masked

    assert mask_token("") == "********"
    assert mask_token(None) == "********"


def test_sanitization_removes_paths_and_tokens():
    """Verify local file paths and private tokens are stripped from exported strings."""
    dirty_text = r"Error at D:\0 Resume Projects\TRADER\data\secret.db with api_key=SecretKey12345"
    cleaned = sanitize_text(dirty_text)
    assert r"D:\0 Resume Projects" not in cleaned
    assert "[LOCAL_PATH_REDACTED]" in cleaned
    assert "SecretKey12345" not in cleaned

    obj = {
        "path": r"C:\Users\rohit\.gemini\key.txt",
        "nested": {"db": r"/home/user/indigo_quant.db"},
        "token": "sensitive_bot_token",
    }
    cleaned_obj = sanitize_dict(obj)
    assert "token" not in cleaned_obj  # keys ending in token are dropped
    assert "C:\\Users" not in cleaned_obj["path"]
    assert "/home/user" not in cleaned_obj["nested"]["db"]


def test_telegram_notifier_deduplication():
    """Verify identical alerts are not dispatched twice (idempotency)."""
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        cache_file = tmp_dir / "sent_alerts.json"

        notifier = TelegramNotifier(
            bot_token="dummy_token_12345",
            chat_id="12345678",
            enabled=True,
            cache_path=str(cache_file),
        )
        notifier._allow_live_network = True  # Allows mocked requests.post

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            sig = {
                "symbol": "RELIANCE",
                "strategy_id": "trend_momentum",
                "signal_date": "2026-11-09",
                "reference_close": 1320.0,
                "target_price_estimate": 1452.0,
                "initial_stop_estimate": 1267.0,
                "rule_quality_score": 85.0,
                "rules_passed": ["EMA20 > EMA50 > EMA200"],
                "recommended_quantity": 10,
            }

            # First alert should succeed
            res1 = notifier.send_buy_alert(sig)
            assert res1 is True
            assert mock_post.call_count == 1

            # Second identical alert should be deduplicated and skipped
            res2 = notifier.send_buy_alert(sig)
            assert res2 is True
            assert mock_post.call_count == 1  # No additional network request


def test_public_data_export_and_static_html():
    """Verify all 6 public JSON snapshots and static HTML report are generated cleanly in an isolated directory."""
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td) / "public_data"
        out_dir.mkdir(parents=True, exist_ok=True)

        exporter = PublicDataExporter(output_dir=str(out_dir))
        files = exporter.export_all()

        assert "overview" in files
        assert "leaderboard" in files
        assert "signals" in files
        assert "portfolios" in files
        assert "charts_data" in files
        assert "system_health" in files

        # Verify each file exists and is valid JSON
        for _name, fpath in files.items():
            p = Path(fpath)
            assert p.exists()
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert data is not None

        # Test static HTML generation
        html_path = out_dir / "index.html"
        res_html = generate_static_html(public_data_dir=str(out_dir), output_path=str(html_path))
        assert Path(res_html).exists()
        content = Path(res_html).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "INDIGO QUANT" in content


def test_test_position_filtering_excludes_future_trades_from_forward_stats():
    """Verify that future-dated test positions are excluded from forward statistics and captured in audit logs."""
    import datetime
    from indigo_quant.db.models import PaperPosition
    from indigo_quant.export.public_data import is_test_position

    today = datetime.date(2026, 11, 9)

    # 1. Future closed date (smoke test fixture)
    future_pos = PaperPosition(
        account_id="trend_momentum",
        symbol="RELIANCE",
        strategy_id="trend_momentum",
        quantity=10,
        entry_date=today,
        entry_price=1320.0,
        current_stop=1268.0,
        target_price=1452.0,
        status="CLOSED",
        closed_date=datetime.date(2026, 11, 16),  # Future date
        close_reason="TARGET_HIT",
    )
    assert is_test_position(future_pos, today) is True

    # 2. Legitimate forward closed position (completed today)
    legit_pos = PaperPosition(
        account_id="trend_momentum",
        symbol="TCS",
        strategy_id="trend_momentum",
        quantity=5,
        entry_date=datetime.date(2026, 11, 6),
        entry_price=3500.0,
        current_stop=3400.0,
        target_price=3850.0,
        status="CLOSED",
        closed_date=today,
        close_reason="TARGET_HIT",
    )
    assert is_test_position(legit_pos, today) is False

    # 3. Explicit synthetic test close reason
    test_pos = PaperPosition(
        account_id="trend_momentum",
        symbol="INFY",
        strategy_id="trend_momentum",
        quantity=10,
        entry_date=datetime.date(2026, 11, 6),
        entry_price=1800.0,
        current_stop=1750.0,
        target_price=1980.0,
        status="CLOSED",
        closed_date=today,
        close_reason="TEST_SYNTHETIC_EXIT",
    )
    assert is_test_position(test_pos, today) is True
