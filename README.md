# Mock ERP / Traceability API — FDA Recall Agent

A mock REST API that stands in for the ERP, WMS, Traceability Repository, and
LIMS systems the FDA Food Recall Traceability Agent (UiPath AgentHack 2026)
would normally reach via SAP/Oracle/Integration Service connectors. Backed by
the project's sample data — no real database needed.

Matches **Step 2** of the build plan (`mock_erp.py`), extended with the full
10-table schema from the sample-data spec so Agents 2, 3, and 4 all have real
endpoints to call instead of just the single `/lot/<code>/trace` stub.

## Golden scenario

Everything is wired to one consistent test case:

- Lot: `LOT-2026-0437` — Romaine Lettuce Hearts 3-pack
- Contamination: E. coli O157:H7 (positive LIMS result)
- 16,100 units shipped to 3 distributors across AZ, CA, TX
- Recall class: I · Urgency: IMMEDIATE

## Run locally

```bash
pip install -r requirements.txt
python app/app.py
# → http://localhost:8080
```

## Run with Docker

```bash
docker build -t mock-erp .
docker run -p 8080:8080 mock-erp
```

## Deploy to Render

**Option A — Blueprint (one click):**
1. Push this folder to a GitHub repo.
2. Render Dashboard → New → Blueprint → point at the repo (uses `render.yaml`).
3. Deploy. Render builds the Dockerfile automatically.

**Option B — Manual web service:**
1. Render Dashboard → New → Web Service → connect your repo.
2. Runtime: **Docker**. Leave build/start commands blank (Dockerfile handles it).
3. Health check path: `/healthz`.
4. Deploy. Your API will be live at `https://<your-service>.onrender.com`.

Optional: set `MOCK_ERP_API_KEY` in the Render dashboard's Environment tab to
require an `X-API-Key` header on every `/api/*` and `/lot/*` call. Leave unset
for an open demo API — one less thing that can break live during judging.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/lot/<lot_code>/trace` | **The build-plan endpoint.** Forward/backward trace in the exact shape from Step 2 — use this if your Agent Builder prompt was written against that shape. |
| GET | `/lot/<lot_code>/trace/full` | Richer trace: adds CTE events, LIMS results, inventory, per-node status/contact/API info, KDE completeness — matches Agent 2's actual system prompt fields. |
| GET | `/api/products`, `/api/products/<id>` | Product Master |
| GET | `/api/suppliers`, `/api/suppliers/<id>` | Supplier Master |
| GET | `/api/facilities`, `/api/facilities/<id>` | Facility Master (farms, plants, warehouses) |
| GET | `/api/customers`, `/api/customers/<id>` | Customer Master (distributors, retailers) |
| GET | `/api/lots`, `/api/lots/<lot_code>` | Lot Master. `?status=` filter |
| GET | `/api/lots/<lot_code>/cte` | Critical Tracking Events for a lot |
| GET | `/api/lots/<lot_code>/raw-materials` | Backward trace (raw material links) |
| GET | `/api/inventory` | Warehouse inventory. `?lot_code=` / `?facility_id=` filters |
| POST | `/api/inventory/<id>/quarantine` | Marks inventory `QUARANTINE_HOLD` — what Agent 4's RPA bot calls |
| GET | `/api/orders` | Order Management (shipments). `?lot_code=` / `?customer_id=` filters |
| POST | `/api/orders/<id>/confirm-quarantine` | Simulates a retailer confirming quarantine receipt |
| GET | `/api/lims-results` | Lab test results. `?lot_code=` / `?result=` filters |
| GET | `/api/quality-alerts/latest` | Returns the sample LIMS webhook payload — useful if your Trigger Agent polls instead of receiving a push |
| POST | `/api/reload` | Reloads sample CSVs from disk without restarting the container |
| GET | `/healthz` | Health check (always open, no auth) |

## Example calls

```bash
# the money-shot endpoint for the demo
curl https://<your-app>.onrender.com/lot/LOT-2026-0437/trace

# full trace with CTEs, LIMS, node contacts
curl https://<your-app>.onrender.com/lot/LOT-2026-0437/trace/full

# quarantine a warehouse inventory record
curl -X POST https://<your-app>.onrender.com/api/inventory/INV-0001/quarantine \
  -H "Content-Type: application/json" -d '{}'
```

## Project structure

```
mock_erp/
├── Dockerfile
├── .dockerignore
├── render.yaml          ← Render blueprint
├── requirements.txt
├── .env.example
└── app/
    ├── app.py           ← Flask routes
    ├── db.py            ← in-memory data layer (loads CSVs)
    ├── trace.py          ← trace-building logic + classification rules
    └── data/             ← sample data (10 CSVs + 1 JSON)
```

## Notes

- Data is in-memory and resets on container restart — fine for a demo. If you
  need durable state across restarts, swap `db.py` for a real database
  (Postgres on Render's free tier works well) without touching `app.py`.
- Render's free tier spins down after inactivity; the first request after
  idle takes a few seconds to wake up. Hit `/healthz` a minute before your
  demo to warm it up.
