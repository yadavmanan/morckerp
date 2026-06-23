"""
db.py — lightweight in-memory data layer for the mock ERP.

Loads the 10 sample CSV tables at startup into pandas-free, pure-Python
list-of-dict tables. No real database needed for a hackathon demo, but the
shape mirrors what a real ERP/Traceability repository would return.

State is mutated in memory only (e.g. quarantine flags). It resets on
container restart, which is fine for a demo API.
"""
import csv
import json
import os
import threading
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_lock = threading.Lock()


def _load_csv(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path) as f:
        return json.load(f)


class Database:
    """Holds all sample tables in memory and exposes simple query helpers."""

    def __init__(self):
        self.reload()

    def reload(self):
        with _lock:
            self.products = _load_csv("product_master.csv")
            self.suppliers = _load_csv("supplier_master.csv")
            self.facilities = _load_csv("facility_master.csv")
            self.customers = _load_csv("customer_master.csv")
            self.lots = _load_csv("lot_master.csv")
            self.cte_events = _load_csv("critical_tracking_events.csv")
            self.raw_material_links = _load_csv("raw_material_links.csv")
            self.inventory = _load_csv("warehouse_inventory.csv")
            self.orders = _load_csv("order_management.csv")
            self.lims_results = _load_csv("lims_results.csv")
            self.quality_alert_template = _load_json("lims_quality_alert.json")

    # ---------- generic lookups ----------
    @staticmethod
    def _find_one(rows, key, value):
        return next((r for r in rows if r.get(key) == value), None)

    @staticmethod
    def _find_many(rows, key, value):
        return [r for r in rows if r.get(key) == value]

    # ---------- master data ----------
    def get_product(self, product_id):
        return self._find_one(self.products, "product_id", product_id)

    def get_supplier(self, supplier_id):
        return self._find_one(self.suppliers, "supplier_id", supplier_id)

    def get_facility(self, facility_id):
        return self._find_one(self.facilities, "facility_id", facility_id)

    def get_customer(self, customer_id):
        return self._find_one(self.customers, "customer_id", customer_id)

    def get_lot(self, lot_code):
        return self._find_one(self.lots, "traceability_lot_code", lot_code)

    # ---------- traceability ----------
    def get_cte_for_lot(self, lot_code):
        return self._find_many(self.cte_events, "traceability_lot_code", lot_code)

    def get_raw_materials_for_lot(self, lot_code):
        return self._find_many(self.raw_material_links, "finished_lot_code", lot_code)

    def get_inventory_for_lot(self, lot_code):
        return self._find_many(self.inventory, "traceability_lot_code", lot_code)

    def get_orders_for_lot(self, lot_code):
        return self._find_many(self.orders, "traceability_lot_code", lot_code)

    def get_lims_results_for_lot(self, lot_code):
        return self._find_many(self.lims_results, "traceability_lot_code", lot_code)

    # ---------- mutations (quarantine actions used by Agent 4) ----------
    def quarantine_inventory(self, inventory_id, quantity=None):
        with _lock:
            row = self._find_one(self.inventory, "inventory_id", inventory_id)
            if row is None:
                return None
            on_hand = int(row.get("quantity_on_hand", 0) or 0)
            qty = on_hand if quantity is None else min(int(quantity), on_hand)
            row["quantity_quarantined"] = str(qty)
            row["status"] = "QUARANTINE_HOLD"
            row["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return row

    def confirm_order_quarantine(self, order_id):
        with _lock:
            row = self._find_one(self.orders, "order_id", order_id)
            if row is None:
                return None
            row["order_status"] = "QUARANTINE_CONFIRMED"
            return row


db = Database()
