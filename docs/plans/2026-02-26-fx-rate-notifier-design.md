# FX Rate Notifier — Design Doc

**Date:** 2026-02-26
**Author:** Claude (with Damie Adams)
**Status:** Approved

## Purpose

Daily EUR/USD exchange rate notifier that posts to the Pricing Team's Google Chat space. Alerts when daily swing exceeds a configurable threshold (default 1.0%).

## Data Source

[frankfurter.app](https://www.frankfurter.app/) — free, open-source API backed by European Central Bank reference rates. No API key required.

## Architecture

Single-run Python 3.12 container on Cloud Run, triggered daily by Cloud Scheduler. Mirrors `weather-revenue-tracker` project structure.

```
fx-rate-notifier/
├── config.py            # env-var-driven configuration
├── fx_fetcher.py        # frankfurter.app API client
├── notifier.py          # Google Chat webhook sender
├── main.py              # orchestrator: fetch → compare → notify
├── requirements.txt     # requests
├── Dockerfile           # python:3.12-slim
├── cloudbuild.yaml      # Cloud Build → Cloud Run deploy
├── .gitignore
├── README.md
├── tests/
│   ├── test_fx_fetcher.py
│   ├── test_notifier.py
│   └── test_main.py
└── docs/plans/
```

## Data Flow

1. `main.py` runs once per invocation
2. `fx_fetcher.py` calls `GET https://api.frankfurter.app/latest?from=EUR&to=USD` for today's rate
3. `fx_fetcher.py` calls `GET https://api.frankfurter.app/{yesterday}?from=EUR&to=USD` for previous rate
4. `main.py` computes absolute change, percent change, checks threshold
5. `notifier.py` formats a Google Chat card and POSTs to webhook
6. Exit 0

## Configuration

| Env Var | Default | Purpose |
|---------|---------|---------|
| `WEBHOOK_URL` | Pricing Team webhook | Google Chat destination |
| `BASE_CURRENCY` | `EUR` | From currency |
| `QUOTE_CURRENCY` | `USD` | To currency |
| `ALERT_THRESHOLD_PCT` | `1.0` | Daily swing % that triggers alert styling |

## Google Chat Message Format

**Normal day (< 1.0% move):**

> **EUR/USD Daily Rate**
> Rate: 1.0842
> Change: +0.0023 (+0.21%)
> Source: ECB via frankfurter.app

**Alert day (>= 1.0% move):**

> **EUR/USD ALERT: Large Move Detected**
> Rate: 1.0742
> Change: -0.0123 (-1.13%)
> Threshold: 1.0% breached
> Source: ECB via frankfurter.app

Both use Google Chat card format (structured JSON) for clean rendering.

## Error Handling

- **API down/timeout:** Log error, send error notification to webhook ("FX rate fetch failed"), exit 1.
- **Weekend/holiday (no new rate):** frankfurter.app returns last available rate. Detect "same date as yesterday" and send a short "No new rate published (weekend/holiday)" message.
- **Webhook failure:** Log error, exit 1.

## Testing

- `test_fx_fetcher.py` — mock HTTP responses, verify rate parsing, verify error handling
- `test_notifier.py` — verify card formatting for normal/alert cases, mock webhook POST
- `test_main.py` — integration test with mocked fetcher + notifier

## Deployment

Same stack as `weather-revenue-tracker`:
- Docker container (python:3.12-slim)
- Cloud Build for CI/CD
- Cloud Run (single instance, no public access)
- Cloud Scheduler for daily trigger

## Decisions

- **frankfurter.app over ECB XML directly:** Simpler JSON API, same underlying data.
- **1.0% alert threshold:** Configurable via `ALERT_THRESHOLD_PCT` env var. 1.0% is rare enough for EUR/USD to avoid noise.
- **Mirror weather-revenue-tracker structure:** Consistent conventions across pricing team repos.
