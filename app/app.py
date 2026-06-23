"""
mock_erp.py — Mock ERP / Traceability / WMS / LIMS API for the
FDA Food Recall Traceability Agent (UiPath AgentHack 2026).

Simulates the systems Agent 2 (Lot Tracing), Agent 3 (KDE Report), and
Agent 4 (Quarantine & Notification) would normally call via SAP/Oracle/WMS
Integration Service connectors. Backed by in-memory sample data seeded from
the project's sample_data CSVs — no real database required.

Run locally:
    pip install -r requirements.txt
    python app.py            # http://localhost:8080

Run with gunicorn (production / Render):
    gunicorn -b 0.0.0.0:8080 app:app
"""
import os
from flask import Flask, jsonify, request, abort
from flask_cors import CORS

from db import db
import trace as trace_module

app = Flask(__name__)
CORS(app)  # Agent Builder / Integration Service calls cross-origin

API_KEY = os.environ.get("MOCK_ERP_API_KEY")  # optional; unset = no auth, fine for a demo


@app.before_request
def _check_api_key():
    """Optional shared-secret auth. Set MOCK_ERP_API_KEY env var to enable.
    Health check and root are always open so Render's health probe passes."""
    if not API_KEY:
        return
    if request.path in ("/", "/healthz"):
        return
    supplied = request.headers.get("X-API-Key")
    if supplied != API_KEY:
        abort(401, description="Missing or invalid X-API-Key header")


def ok(payload, status=200):
    return jsonify(payload), status


def not_found(entity, key):
    return jsonify({"error": f"{entity} not found", "key": key}), 404


# ---------------------------------------------------------------------------
# Root / health
# ---------------------------------------------------------------------------
@app.route("/")
def root():
    return ok({
        "service": "FDA Recall Agent — Mock ERP API",
        "status": "ok",
        "goldenScenarioLot": "LOT-2026-0437",
        "endpoints": [
            "GET  /lot/<lot_code>/trace",
            "GET  /lot/<lot_code>/trace/full",
            "GET  /api/products", "GET /api/products/<product_id>",
            "GET  /api/suppliers", "GET /api/suppliers/<supplier_id>",
            "GET  /api/facilities", "GET /api/facilities/<facility_id>",
            "GET  /api/customers", "GET /api/customers/<customer_id>",
            "GET  /api/lots", "GET /api/lots/<lot_code>",
            "GET  /api/lots/<lot_code>/cte",
            "GET  /api/lots/<lot_code>/raw-materials",
            "GET  /api/inventory", "POST /api/inventory/<inventory_id>/quarantine",
            "GET  /api/orders", "POST /api/orders/<order_id>/confirm-quarantine",
            "GET  /api/lims-results",
            "GET  /api/quality-alerts/latest",
            "POST /api/reload",
        ],
    })


@app.route("/healthz")
def healthz():
    return ok({"status": "healthy"})


# ---------------------------------------------------------------------------
# THE MONEY-SHOT ENDPOINT — matches the build plan's mock_erp.py shape
# ---------------------------------------------------------------------------
@app.route("/lot/<lot_code>/trace")
def trace_lot_simple(lot_code):
    result = trace_module.build_simple_trace(lot_code)
    if result is None:
        return ok({"error": "Lot not found"}, 404)
    return ok(result)


@app.route("/lot/<lot_code>/trace/full")
def trace_lot_full(lot_code):
    """Richer trace for Agent 2's actual system prompt (nodes w/ status,
    contact info, KDE completeness, LIMS results, CTEs)."""
    result = trace_module.build_full_trace(lot_code)
    if result is None:
        return ok({"error": "Lot not found"}, 404)
    return ok(result)


# ---------------------------------------------------------------------------
# Master data — Product / Supplier / Facility / Customer
# ---------------------------------------------------------------------------
@app.route("/api/products")
def list_products():
    return ok(db.products)


@app.route("/api/products/<product_id>")
def get_product(product_id):
    row = db.get_product(product_id)
    return ok(row) if row else not_found("product", product_id)


@app.route("/api/suppliers")
def list_suppliers():
    return ok(db.suppliers)


@app.route("/api/suppliers/<supplier_id>")
def get_supplier(supplier_id):
    row = db.get_supplier(supplier_id)
    return ok(row) if row else not_found("supplier", supplier_id)


@app.route("/api/facilities")
def list_facilities():
    return ok(db.facilities)


@app.route("/api/facilities/<facility_id>")
def get_facility(facility_id):
    row = db.get_facility(facility_id)
    return ok(row) if row else not_found("facility", facility_id)


@app.route("/api/customers")
def list_customers():
    return ok(db.customers)


@app.route("/api/customers/<customer_id>")
def get_customer(customer_id):
    row = db.get_customer(customer_id)
    return ok(row) if row else not_found("customer", customer_id)


# ---------------------------------------------------------------------------
# Traceability repository — Lots / CTE / Raw materials
# ---------------------------------------------------------------------------
@app.route("/api/lots")
def list_lots():
    status = request.args.get("status")
    rows = db.lots
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return ok(rows)


@app.route("/api/lots/<lot_code>")
def get_lot(lot_code):
    row = db.get_lot(lot_code)
    return ok(row) if row else not_found("lot", lot_code)


@app.route("/api/lots/<lot_code>/cte")
def get_lot_cte(lot_code):
    if db.get_lot(lot_code) is None:
        return not_found("lot", lot_code)
    return ok(db.get_cte_for_lot(lot_code))


@app.route("/api/lots/<lot_code>/raw-materials")
def get_lot_raw_materials(lot_code):
    if db.get_lot(lot_code) is None:
        return not_found("lot", lot_code)
    return ok(db.get_raw_materials_for_lot(lot_code))


# ---------------------------------------------------------------------------
# Warehouse inventory — list / filter / quarantine action
# ---------------------------------------------------------------------------
@app.route("/api/inventory")
def list_inventory():
    lot_code = request.args.get("lot_code")
    facility_id = request.args.get("facility_id")
    rows = db.inventory
    if lot_code:
        rows = [r for r in rows if r.get("traceability_lot_code") == lot_code]
    if facility_id:
        rows = [r for r in rows if r.get("facility_id") == facility_id]
    return ok(rows)


@app.route("/api/inventory/<inventory_id>/quarantine", methods=["POST"])
def quarantine_inventory(inventory_id):
    """Simulates the WMS quarantine-hold action Agent 4 (RPA bot) performs."""
    body = request.get_json(silent=True) or {}
    quantity = body.get("quantity")
    row = db.quarantine_inventory(inventory_id, quantity)
    if row is None:
        return not_found("inventory_id", inventory_id)
    return ok({"message": "Inventory marked QUARANTINE_HOLD", "inventory": row})


# ---------------------------------------------------------------------------
# Order management — list / filter / quarantine confirmation
# ---------------------------------------------------------------------------
@app.route("/api/orders")
def list_orders():
    lot_code = request.args.get("lot_code")
    customer_id = request.args.get("customer_id")
    rows = db.orders
    if lot_code:
        rows = [r for r in rows if r.get("traceability_lot_code") == lot_code]
    if customer_id:
        rows = [r for r in rows if r.get("ship_to_customer_id") == customer_id]
    return ok(rows)


@app.route("/api/orders/<order_id>/confirm-quarantine", methods=["POST"])
def confirm_order_quarantine(order_id):
    """Simulates a retailer/distributor confirming quarantine receipt —
    used by Agent 4's Action Center tracking loop."""
    row = db.confirm_order_quarantine(order_id)
    if row is None:
        return not_found("order_id", order_id)
    return ok({"message": "Quarantine confirmed for order", "order": row})


# ---------------------------------------------------------------------------
# LIMS results
# ---------------------------------------------------------------------------
@app.route("/api/lims-results")
def list_lims_results():
    lot_code = request.args.get("lot_code")
    result = request.args.get("result")
    rows = db.lims_results
    if lot_code:
        rows = [r for r in rows if r.get("traceability_lot_code") == lot_code]
    if result:
        rows = [r for r in rows if r.get("result") == result]
    return ok(rows)


# ---------------------------------------------------------------------------
# Simulated LIMS webhook payload — lets the Trigger Agent poll instead of
# requiring a real webhook push during the demo.
# ---------------------------------------------------------------------------
@app.route("/api/quality-alerts/latest")
def latest_quality_alert():
    return ok(db.quality_alert_template)


# ---------------------------------------------------------------------------
# Admin — reload sample data from disk without restarting the container
# ---------------------------------------------------------------------------
@app.route("/api/reload", methods=["POST"])
def reload_data():
    db.reload()
    return ok({"message": "Sample data reloaded"})


@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": "Not found", "path": request.path}), 404


@app.errorhandler(401)
def handle_401(e):
    return jsonify({"error": "Unauthorized", "detail": str(e.description)}), 401


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
