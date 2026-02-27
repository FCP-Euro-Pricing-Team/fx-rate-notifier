# FX Rate Notifier Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a daily EUR/USD rate notifier that posts to Google Chat with threshold alerts.

**Architecture:** Single-run Python container mirroring weather-revenue-tracker. `fx_fetcher.py` calls frankfurter.app for today's and yesterday's rates, `main.py` computes change/threshold, `notifier.py` formats and sends a Google Chat card.

**Tech Stack:** Python 3.12, requests, pytest, Docker, Cloud Build, Cloud Run

**Design doc:** `docs/plans/2026-02-26-fx-rate-notifier-design.md`

---

### Task 1: Project Scaffolding

**Files:**
- Create: `config.py`
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `Dockerfile`
- Create: `cloudbuild.yaml`
- Create: `tests/__init__.py`

**Step 1: Create `config.py`**

```python
"""
Configuration for FX Rate Notifier.
Override any value via environment variables.
"""
import os

# --- Google Chat Webhook ---
WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL",
    "https://chat.googleapis.com/v1/spaces/AAQAZsynuaA/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=HecuA2q08_xgutW_12elSvDhgfCU7p4r9lPLWe2nEN4",
)

# --- Currency pair ---
BASE_CURRENCY = os.getenv("BASE_CURRENCY", "EUR")
QUOTE_CURRENCY = os.getenv("QUOTE_CURRENCY", "USD")

# --- Alert threshold (percent daily swing to trigger alert styling) ---
ALERT_THRESHOLD_PCT = float(os.getenv("ALERT_THRESHOLD_PCT", "1.0"))

# --- frankfurter.app API ---
FRANKFURTER_BASE_URL = os.getenv("FRANKFURTER_BASE_URL", "https://api.frankfurter.app")
```

**Step 2: Create `requirements.txt`**

```
requests>=2.31.0
pytest>=7.0.0
```

**Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
*.egg-info/
dist/
build/
*.log
logs/
.pytest_cache/
```

**Step 4: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Single execution mode - triggered by Cloud Scheduler
CMD ["python", "main.py"]
```

**Step 5: Create `cloudbuild.yaml`**

```yaml
# Cloud Build config for deploying to Cloud Run
steps:
  # Build the container image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/fx-rate-notifier', '.']

  # Push to Container Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/fx-rate-notifier']

  # Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'fx-rate-notifier'
      - '--image'
      - 'gcr.io/$PROJECT_ID/fx-rate-notifier'
      - '--region'
      - 'us-central1'
      - '--platform'
      - 'managed'
      - '--no-allow-unauthenticated'
      - '--memory'
      - '256Mi'
      - '--min-instances'
      - '0'
      - '--max-instances'
      - '1'

images:
  - 'gcr.io/$PROJECT_ID/fx-rate-notifier'
```

**Step 6: Create empty `tests/__init__.py`**

Empty file.

**Step 7: Commit**

```bash
git add config.py requirements.txt .gitignore Dockerfile cloudbuild.yaml tests/__init__.py
git commit -m "feat: add project scaffolding

Config, Dockerfile, Cloud Build, requirements mirroring weather-revenue-tracker."
```

---

### Task 2: FX Fetcher — Tests

**Files:**
- Create: `tests/test_fx_fetcher.py`

**Step 1: Write failing tests**

```python
"""Tests for fx_fetcher module."""
from datetime import date
from unittest.mock import patch, MagicMock

import pytest


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status.side_effect = (
        None if status_code == 200 else Exception(f"HTTP {status_code}")
    )
    return mock


class TestFetchRate:
    """Tests for fetch_rate()."""

    @patch("fx_fetcher.requests.get")
    def test_returns_rate_and_date(self, mock_get):
        from fx_fetcher import fetch_rate

        mock_get.return_value = _mock_response({
            "amount": 1.0,
            "base": "EUR",
            "date": "2026-02-26",
            "rates": {"USD": 1.0842},
        })

        result = fetch_rate("latest")
        assert result["rate"] == 1.0842
        assert result["date"] == "2026-02-26"

    @patch("fx_fetcher.requests.get")
    def test_calls_correct_url(self, mock_get):
        from fx_fetcher import fetch_rate
        import config

        mock_get.return_value = _mock_response({
            "amount": 1.0, "base": "EUR", "date": "2026-02-26",
            "rates": {"USD": 1.0842},
        })

        fetch_rate("2026-02-25")
        mock_get.assert_called_once_with(
            f"{config.FRANKFURTER_BASE_URL}/2026-02-25",
            params={"from": config.BASE_CURRENCY, "to": config.QUOTE_CURRENCY},
            timeout=15,
        )

    @patch("fx_fetcher.requests.get")
    def test_raises_on_http_error(self, mock_get):
        from fx_fetcher import fetch_rate

        mock_get.return_value = _mock_response({}, status_code=500)
        mock_get.return_value.raise_for_status.side_effect = Exception("HTTP 500")

        with pytest.raises(Exception, match="HTTP 500"):
            fetch_rate("latest")


class TestGetTodayAndYesterday:
    """Tests for get_today_and_yesterday_rates()."""

    @patch("fx_fetcher.fetch_rate")
    def test_returns_both_rates(self, mock_fetch):
        from fx_fetcher import get_today_and_yesterday_rates

        mock_fetch.side_effect = [
            {"rate": 1.0842, "date": "2026-02-26"},
            {"rate": 1.0819, "date": "2026-02-25"},
        ]

        today, yesterday = get_today_and_yesterday_rates()
        assert today["rate"] == 1.0842
        assert yesterday["rate"] == 1.0819

    @patch("fx_fetcher.fetch_rate")
    def test_detects_weekend_same_date(self, mock_fetch):
        from fx_fetcher import get_today_and_yesterday_rates

        mock_fetch.side_effect = [
            {"rate": 1.0842, "date": "2026-02-20"},  # Friday's rate
            {"rate": 1.0842, "date": "2026-02-20"},  # Same date = no new data
        ]

        today, yesterday = get_today_and_yesterday_rates()
        assert today["date"] == yesterday["date"]  # Caller checks this
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/damienadams/Claude\ Project\ Folder/fx-rate-notifier && python -m pytest tests/test_fx_fetcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fx_fetcher'`

**Step 3: Commit test file**

```bash
git add tests/test_fx_fetcher.py
git commit -m "test: add fx_fetcher tests (red phase)"
```

---

### Task 3: FX Fetcher — Implementation

**Files:**
- Create: `fx_fetcher.py`

**Step 1: Implement fx_fetcher.py**

```python
"""
Fetches EUR/USD exchange rates from frankfurter.app (ECB data).
"""
import logging
from datetime import date, timedelta

import requests

from config import BASE_CURRENCY, QUOTE_CURRENCY, FRANKFURTER_BASE_URL

logger = logging.getLogger(__name__)


def fetch_rate(endpoint: str) -> dict:
    """
    Fetch a single FX rate from frankfurter.app.

    Args:
        endpoint: "latest" or a date string like "2026-02-25".

    Returns:
        {"rate": float, "date": str} e.g. {"rate": 1.0842, "date": "2026-02-26"}

    Raises:
        requests.RequestException on network/HTTP errors.
    """
    url = f"{FRANKFURTER_BASE_URL}/{endpoint}"
    resp = requests.get(
        url,
        params={"from": BASE_CURRENCY, "to": QUOTE_CURRENCY},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    rate = data["rates"][QUOTE_CURRENCY]
    return {"rate": rate, "date": data["date"]}


def get_today_and_yesterday_rates() -> tuple[dict, dict]:
    """
    Fetch today's rate and the previous business day's rate.

    Returns:
        (today_data, yesterday_data) — each is {"rate": float, "date": str}.
        If both dates are the same, it means no new rate was published (weekend/holiday).
    """
    today = fetch_rate("latest")
    yesterday_date = (date.today() - timedelta(days=1)).isoformat()
    yesterday = fetch_rate(yesterday_date)
    return today, yesterday
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/damienadams/Claude\ Project\ Folder/fx-rate-notifier && python -m pytest tests/test_fx_fetcher.py -v`
Expected: All 5 tests PASS

**Step 3: Commit**

```bash
git add fx_fetcher.py
git commit -m "feat: implement fx_fetcher with frankfurter.app client"
```

---

### Task 4: Notifier — Tests

**Files:**
- Create: `tests/test_notifier.py`

**Step 1: Write failing tests**

```python
"""Tests for notifier module."""
from unittest.mock import patch, MagicMock

import pytest


class TestBuildRateCard:
    """Tests for _build_rate_card()."""

    def test_normal_card_has_daily_rate_header(self):
        from notifier import _build_rate_card

        card = _build_rate_card(
            rate=1.0842,
            change=0.0023,
            change_pct=0.21,
            rate_date="2026-02-26",
            is_alert=False,
        )
        header = card["cardsV2"][0]["card"]["header"]
        assert "EUR/USD Daily Rate" in header["title"]
        assert "ALERT" not in header["title"]

    def test_alert_card_has_alert_header(self):
        from notifier import _build_rate_card

        card = _build_rate_card(
            rate=1.0742,
            change=-0.0123,
            change_pct=-1.13,
            rate_date="2026-02-26",
            is_alert=True,
        )
        header = card["cardsV2"][0]["card"]["header"]
        assert "ALERT" in header["title"]

    def test_card_contains_rate_value(self):
        from notifier import _build_rate_card

        card = _build_rate_card(
            rate=1.0842,
            change=0.0023,
            change_pct=0.21,
            rate_date="2026-02-26",
            is_alert=False,
        )
        # Rate should appear somewhere in the card sections
        card_text = str(card)
        assert "1.0842" in card_text

    def test_card_contains_change_info(self):
        from notifier import _build_rate_card

        card = _build_rate_card(
            rate=1.0842,
            change=0.0023,
            change_pct=0.21,
            rate_date="2026-02-26",
            is_alert=False,
        )
        card_text = str(card)
        assert "+0.0023" in card_text
        assert "+0.21%" in card_text


class TestBuildNoUpdateCard:
    """Tests for _build_no_update_card()."""

    def test_no_update_card_mentions_weekend_or_holiday(self):
        from notifier import _build_no_update_card

        card = _build_no_update_card("2026-02-20")
        card_text = str(card).lower()
        assert "no new rate" in card_text or "weekend" in card_text or "holiday" in card_text


class TestSendNotification:
    """Tests for send_notification()."""

    @patch("notifier.requests.post")
    def test_posts_to_webhook(self, mock_post):
        from notifier import send_notification

        mock_post.return_value = MagicMock(status_code=200)

        result = send_notification({"cardsV2": []})
        assert result is True
        mock_post.assert_called_once()

    @patch("notifier.requests.post")
    def test_returns_false_on_http_error(self, mock_post):
        from notifier import send_notification

        mock_post.return_value = MagicMock(status_code=500, text="Server Error")

        result = send_notification({"cardsV2": []})
        assert result is False

    @patch("notifier.WEBHOOK_URL", "")
    def test_returns_false_when_no_webhook(self):
        from notifier import send_notification

        result = send_notification({"cardsV2": []})
        assert result is False
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/damienadams/Claude\ Project\ Folder/fx-rate-notifier && python -m pytest tests/test_notifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'notifier'`

**Step 3: Commit test file**

```bash
git add tests/test_notifier.py
git commit -m "test: add notifier tests (red phase)"
```

---

### Task 5: Notifier — Implementation

**Files:**
- Create: `notifier.py`

**Step 1: Implement notifier.py**

```python
"""
Sends FX rate notifications to a Google Chat webhook.
"""
import logging

import requests

from config import WEBHOOK_URL, BASE_CURRENCY, QUOTE_CURRENCY, ALERT_THRESHOLD_PCT

logger = logging.getLogger(__name__)


def _build_rate_card(
    rate: float,
    change: float,
    change_pct: float,
    rate_date: str,
    is_alert: bool,
) -> dict:
    """Build a Google Chat card for the daily FX rate."""
    pair = f"{BASE_CURRENCY}/{QUOTE_CURRENCY}"
    sign = "+" if change >= 0 else ""

    if is_alert:
        title = f"\U000026A0\uFE0F {pair} ALERT: Large Move Detected"
    else:
        title = f"\U0001F4B1 {pair} Daily Rate"

    sections = [
        {
            "widgets": [
                {"decoratedText": {"topLabel": "Rate", "text": f"<b>{rate:.4f}</b>"}},
                {"decoratedText": {"topLabel": "Change", "text": f"{sign}{change:.4f} ({sign}{change_pct:.2f}%)"}},
            ],
        },
    ]

    if is_alert:
        sections.append({
            "widgets": [
                {"decoratedText": {
                    "topLabel": "Threshold Breached",
                    "text": f"\U0001F6A8 Daily move of {abs(change_pct):.2f}% exceeds {ALERT_THRESHOLD_PCT}% threshold",
                }},
            ],
        })

    sections.append({
        "widgets": [
            {"textParagraph": {"text": f"<i>Source: ECB via frankfurter.app | {rate_date}</i>"}},
        ],
    })

    return {
        "cardsV2": [
            {
                "cardId": "fx-daily-rate",
                "card": {
                    "header": {"title": title, "subtitle": rate_date},
                    "sections": sections,
                },
            }
        ]
    }


def _build_no_update_card(rate_date: str) -> dict:
    """Card sent when no new rate is published (weekend/holiday)."""
    pair = f"{BASE_CURRENCY}/{QUOTE_CURRENCY}"
    return {
        "cardsV2": [
            {
                "cardId": "fx-no-update",
                "card": {
                    "header": {
                        "title": f"\U0001F4B1 {pair} Daily Rate",
                        "subtitle": rate_date,
                    },
                    "sections": [
                        {
                            "widgets": [
                                {"textParagraph": {
                                    "text": f"No new rate published (weekend/holiday). Last rate date: {rate_date}.",
                                }},
                            ],
                        },
                    ],
                },
            }
        ]
    }


def send_notification(payload: dict) -> bool:
    """POST a JSON payload to the Google Chat webhook."""
    if not WEBHOOK_URL:
        logger.error("No WEBHOOK_URL configured. Cannot send notification.")
        return False

    try:
        resp = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200:
            logger.info("Webhook message sent successfully.")
            return True
        else:
            logger.error("Webhook returned %d: %s", resp.status_code, resp.text[:300])
            return False
    except requests.RequestException as exc:
        logger.error("Failed to post to webhook: %s", exc)
        return False
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/damienadams/Claude\ Project\ Folder/fx-rate-notifier && python -m pytest tests/test_notifier.py -v`
Expected: All 7 tests PASS

**Step 3: Commit**

```bash
git add notifier.py
git commit -m "feat: implement notifier with Google Chat card formatting"
```

---

### Task 6: Main Orchestrator — Tests

**Files:**
- Create: `tests/test_main.py`

**Step 1: Write failing tests**

```python
"""Tests for main orchestrator."""
from unittest.mock import patch, MagicMock

import pytest


class TestRunOnce:
    """Tests for run_once()."""

    @patch("main.send_notification", return_value=True)
    @patch("main.get_today_and_yesterday_rates")
    def test_normal_day_sends_rate_card(self, mock_rates, mock_send):
        from main import run_once

        mock_rates.return_value = (
            {"rate": 1.0842, "date": "2026-02-26"},
            {"rate": 1.0819, "date": "2026-02-25"},
        )

        result = run_once()
        assert result is True
        mock_send.assert_called_once()

        # Verify the card was built (not the no-update card)
        payload = mock_send.call_args[0][0]
        assert "ALERT" not in str(payload["cardsV2"][0]["card"]["header"]["title"])

    @patch("main.send_notification", return_value=True)
    @patch("main.get_today_and_yesterday_rates")
    def test_alert_day_sends_alert_card(self, mock_rates, mock_send):
        from main import run_once

        mock_rates.return_value = (
            {"rate": 1.0742, "date": "2026-02-26"},
            {"rate": 1.0865, "date": "2026-02-25"},
        )

        result = run_once()
        assert result is True
        payload = mock_send.call_args[0][0]
        assert "ALERT" in str(payload["cardsV2"][0]["card"]["header"]["title"])

    @patch("main.send_notification", return_value=True)
    @patch("main.get_today_and_yesterday_rates")
    def test_weekend_sends_no_update_card(self, mock_rates, mock_send):
        from main import run_once

        mock_rates.return_value = (
            {"rate": 1.0842, "date": "2026-02-20"},
            {"rate": 1.0842, "date": "2026-02-20"},  # Same date = weekend
        )

        result = run_once()
        assert result is True
        payload = mock_send.call_args[0][0]
        card_text = str(payload).lower()
        assert "no new rate" in card_text

    @patch("main.send_notification")
    @patch("main.get_today_and_yesterday_rates")
    def test_fetch_error_sends_error_and_returns_false(self, mock_rates, mock_send):
        from main import run_once

        mock_rates.side_effect = Exception("API timeout")
        mock_send.return_value = True

        result = run_once()
        assert result is False

    @patch("main.send_notification", return_value=True)
    @patch("main.get_today_and_yesterday_rates")
    def test_dry_run_does_not_send(self, mock_rates, mock_send):
        from main import run_once

        mock_rates.return_value = (
            {"rate": 1.0842, "date": "2026-02-26"},
            {"rate": 1.0819, "date": "2026-02-25"},
        )

        result = run_once(dry_run=True)
        assert result is True
        mock_send.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/damienadams/Claude\ Project\ Folder/fx-rate-notifier && python -m pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'main'` or `ImportError`

**Step 3: Commit test file**

```bash
git add tests/test_main.py
git commit -m "test: add main orchestrator tests (red phase)"
```

---

### Task 7: Main Orchestrator — Implementation

**Files:**
- Create: `main.py`

**Step 1: Implement main.py**

```python
"""
FX Rate Notifier - Main Entry Point

Runs once daily via Cloud Scheduler. Fetches EUR/USD rate from frankfurter.app,
compares to previous day, and sends a report to Google Chat.

Usage:
    python main.py              # Run once and send report
    python main.py --dry-run    # Fetch and print without sending
"""
import argparse
import json
import logging
import sys

from fx_fetcher import get_today_and_yesterday_rates
from notifier import _build_rate_card, _build_no_update_card, send_notification
from config import ALERT_THRESHOLD_PCT, BASE_CURRENCY, QUOTE_CURRENCY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fx-rate-notifier")


def run_once(dry_run: bool = False) -> bool:
    """
    Single execution:
    1. Fetch today's and yesterday's FX rates
    2. Compute change and check threshold
    3. Build and send Google Chat card

    Returns True on success.
    """
    pair = f"{BASE_CURRENCY}/{QUOTE_CURRENCY}"
    logger.info("--- Daily %s Rate Check ---", pair)

    try:
        today, yesterday = get_today_and_yesterday_rates()
    except Exception as exc:
        logger.error("Failed to fetch FX rates: %s (%s)", exc, type(exc).__name__)
        return False

    # Weekend/holiday: same date means no new rate published
    if today["date"] == yesterday["date"]:
        logger.info("No new rate published (weekend/holiday). Last date: %s", today["date"])
        payload = _build_no_update_card(today["date"])
    else:
        change = today["rate"] - yesterday["rate"]
        change_pct = (change / yesterday["rate"]) * 100
        is_alert = abs(change_pct) >= ALERT_THRESHOLD_PCT

        logger.info(
            "%s rate: %.4f | Change: %+.4f (%+.2f%%) | Alert: %s",
            pair, today["rate"], change, change_pct, is_alert,
        )

        payload = _build_rate_card(
            rate=today["rate"],
            change=change,
            change_pct=change_pct,
            rate_date=today["date"],
            is_alert=is_alert,
        )

    if dry_run:
        logger.info("DRY RUN: Would send the following payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return True

    ok = send_notification(payload)
    if ok:
        logger.info("Daily %s report sent successfully.", pair)
    else:
        logger.error("Failed to send daily %s report.", pair)
    return ok


def main():
    parser = argparse.ArgumentParser(description="FX Rate Notifier - Daily Report")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print without sending")
    args = parser.parse_args()

    success = run_once(dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
```

**Step 2: Run ALL tests to verify they pass**

Run: `cd /Users/damienadams/Claude\ Project\ Folder/fx-rate-notifier && python -m pytest tests/ -v`
Expected: All 17 tests PASS

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: implement main orchestrator with threshold alerting"
```

---

### Task 8: README

**Files:**
- Create: `README.md`

**Step 1: Write README.md**

```markdown
# FX Rate Notifier

Daily EUR/USD exchange rate notifier for the FCP Euro Pricing Team. Posts to Google Chat with threshold-based alerts.

## How It Works

1. Fetches today's EUR/USD rate from [frankfurter.app](https://www.frankfurter.app/) (ECB data)
2. Compares to previous business day's rate
3. Sends a Google Chat card with rate, change, and percentage
4. Highlights large moves (>= 1.0% by default) with alert styling

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `WEBHOOK_URL` | Pricing Team webhook | Google Chat webhook URL |
| `BASE_CURRENCY` | `EUR` | From currency |
| `QUOTE_CURRENCY` | `USD` | To currency |
| `ALERT_THRESHOLD_PCT` | `1.0` | % swing to trigger alert |

## Usage

```bash
# Run once (sends to Google Chat)
python main.py

# Dry run (prints payload, doesn't send)
python main.py --dry-run
```

## Development

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Deployment

Deployed to Cloud Run via Cloud Build, triggered daily by Cloud Scheduler.

```bash
gcloud builds submit --config cloudbuild.yaml
```
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with usage and config docs"
```

---

### Task 9: Final Verification & Push

**Step 1: Run full test suite**

Run: `cd /Users/damienadams/Claude\ Project\ Folder/fx-rate-notifier && python -m pytest tests/ -v`
Expected: All 17 tests PASS

**Step 2: Run dry-run smoke test**

Run: `cd /Users/damienadams/Claude\ Project\ Folder/fx-rate-notifier && python main.py --dry-run`
Expected: Prints JSON payload with today's EUR/USD rate to stdout, exit 0

**Step 3: Push feature branch and create PR**

```bash
git push -u origin feature/initial-implementation
```

Then create PR from `feature/initial-implementation` → `main` with:
- Summary of all components
- Link to design doc
- `Closes` any tracking issues
- Test plan checklist
