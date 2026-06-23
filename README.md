# etsy-printify-autobot

Fully automated Etsy + Printify t-shirt dropshipping bot with zero human involvement.

## What it does

| Step | Module | Description |
|------|--------|-------------|
| 1 | `trend_scout` | Scrapes Etsy search pages daily to surface trending t-shirt keywords |
| 2 | `design_generator` | Calls DALL-E 3 to generate print-ready artwork for each keyword |
| 3 | `printify_agent` | Uploads the design and creates a product on Printify |
| 4 | Printify publish | Pushes the product to your connected Etsy store as an active listing |
| 5 | `fulfillment` | When an Etsy order webhook arrives, submits the order to Printify |
| 6 | `scheduler` | APScheduler cron triggers the pipeline every day at 06:00 UTC |
| 7 | `webhook_server` | FastAPI server that receives Etsy webhooks and exposes an admin endpoint |

## Quick start

### 1. Clone & install

```bash
git clone https://github.com/carterferachi/etsy-auto.git
cd etsy-auto
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Fill in all values in .env
```

Key values you need:

| Variable | Where to get it |
|----------|----------------|
| `OPENAI_API_KEY` | platform.openai.com |
| `PRINTIFY_API_KEY` | printify.com → My Profile → Connections |
| `PRINTIFY_SHOP_ID` | Printify API `/v1/shops.json` |
| `PRINTIFY_BLUEPRINT_ID` | Printify catalog (default 5 = Gildan 64000 tee) |
| `PRINTIFY_PRINT_PROVIDER_ID` | Printify catalog (depends on blueprint) |
| `ETSY_API_KEY` / `ETSY_API_SECRET` | etsy.com/developers |
| `ETSY_ACCESS_TOKEN` / `ETSY_REFRESH_TOKEN` | OAuth2 flow (see below) |
| `ETSY_SHOP_ID` | Your Etsy shop ID |
| `ETSY_WEBHOOK_SECRET` | Set when registering the webhook with Etsy |

### 3. Etsy OAuth2

Etsy uses OAuth2 with PKCE. Use any OAuth2 client to exchange your credentials for an access + refresh token and paste them into `.env`. The bot refreshes the token automatically at runtime.

### 4. Register the Etsy webhook

Point Etsy's order webhook at your server:

```
POST https://openapi.etsy.com/v3/application/shops/{shop_id}/receipts/webhooks
{
  "event_type": "receipt.created",
  "url": "https://your-public-url/webhooks/etsy"
}
```

Use `ngrok` or a VPS to expose the local server publicly during development.

### 5. Run

**Server + scheduler (production):**

```bash
python main.py
```

**Run the pipeline once (testing):**

```bash
python run_pipeline_once.py
```

**Trigger manually via HTTP:**

```bash
curl -X POST http://localhost:8000/admin/run-now \
  -H "X-Admin-Key: <your ETSY_WEBHOOK_SECRET>"
```

## Project structure

```
etsy-auto/
├── autobot/
│   ├── config.py           # Settings from .env
│   ├── trend_scout.py      # Scrape Etsy for trending keywords
│   ├── design_generator.py # DALL-E 3 image generation
│   ├── printify_agent.py   # Printify API: upload, create, publish, order
│   ├── etsy_agent.py       # Etsy API: OAuth2, listing activation, order fetch
│   ├── fulfillment.py      # Map Etsy order → Printify fulfillment order
│   ├── pipeline.py         # Orchestrates steps 1–4
│   ├── scheduler.py        # APScheduler daily cron
│   └── webhook_server.py   # FastAPI app
├── main.py                 # Entry point (uvicorn)
├── run_pipeline_once.py    # One-shot pipeline runner
├── requirements.txt
├── .env.example
└── .gitignore
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/webhooks/etsy` | Etsy order webhook receiver |
| POST | `/admin/run-now` | Manually trigger the pipeline |

## Notes

- Variant IDs in `printify_agent.py` are defaults for Gildan 64000. Check the Printify catalog API for your blueprint's actual variant IDs.
- The trend scraper is best-effort; Etsy may rate-limit or change its HTML. If scraping fails the pipeline logs a warning and skips.
- All generated design images are saved to `designs/` (git-ignored).
