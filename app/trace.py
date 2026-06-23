"""
trace.py — builds the supply-chain trace responses consumed by Agent 2
(Lot Tracing Agent) and Agent 3 (KDE Report Agent).

Two shapes are provided:
  - build_simple_trace(): matches the exact JSON shape from the build plan's
    mock_erp.py example (product/forward/rawMaterials/totalUnits/recallClass).
    Use this if the Agent Builder prompt was written against that shape.
  - build_full_trace(): a richer version that also includes CTE events,
    LIMS results, inventory, and per-node contact/status info — closer to
    what Agent 2's system prompt asks for (supplyChainNodes with status and
    contactEmail, incompleteKDENodes, etc).
"""
from db import db

# Mirrors the contamination -> classification rules from the sample data spec
CLASSIFICATION_RULES = {
    "E_coli_O157H7": {"recallClass": "I", "urgency": "IMMEDIATE"},
    "E_coli": {"recallClass": "I", "urgency": "IMMEDIATE"},
    "Listeria": {"recallClass": "I", "urgency": "IMMEDIATE"},
    "Salmonella": {"recallClass": "I", "urgency": "IMMEDIATE"},
    "Allergen": {"recallClass": "I", "urgency": "IMMEDIATE"},
    "Foreign_Object": {"recallClass": "II", "urgency": "URGENT"},
}
DEFAULT_CLASSIFICATION = {"recallClass": "III", "urgency": "ROUTINE"}

REQUIRED_KDE_FIELDS = [
    "traceability_lot_code", "product_description", "quantity", "unit_of_measure",
    "cte_type", "cte_date_time", "location_id", "reference_document_number",
]


def _classification_for_lot(lot_code):
    results = db.get_lims_results_for_lot(lot_code)
    failing = next((r for r in results if r.get("result") in ("POSITIVE", "FAIL")), None)
    test_type = failing.get("test_type") if failing else None
    return CLASSIFICATION_RULES.get(test_type, DEFAULT_CLASSIFICATION), test_type


def build_simple_trace(lot_code):
    """Shape matches the build plan's mock_erp.py example exactly."""
    lot = db.get_lot(lot_code)
    if lot is None:
        return None

    product = db.get_product(lot["product_id"]) or {}
    facility = db.get_facility(lot["origin_facility_id"]) or {}
    raw_links = db.get_raw_materials_for_lot(lot_code)
    orders = db.get_orders_for_lot(lot_code)

    raw_materials = []
    for link in raw_links:
        supplier = db.get_supplier(link["supplier_id"]) or {}
        raw_materials.append({
            "supplier": supplier.get("supplier_name", link["supplier_id"]),
            "lotCode": link["raw_material_lot_code"],
        })

    forward = []
    for order in orders:
        customer = db.get_customer(order["ship_to_customer_id"]) or {}
        forward.append({
            "node": customer.get("customer_name", order["ship_to_customer_id"]),
            "units": int(order["quantity_shipped"]),
            "shippedDate": order["ship_date"],
        })

    classification, contamination_type = _classification_for_lot(lot_code)
    total_units = sum(f["units"] for f in forward) or int(lot.get("quantity_produced", 0) or 0)

    return {
        "product": product.get("product_name", lot["product_id"]),
        "productionDate": lot["production_date"],
        "facility": f"{facility.get('facility_name','')}, {facility.get('state','')}".strip(", "),
        "rawMaterials": raw_materials,
        "forward": forward,
        "totalUnits": total_units,
        "recallClass": classification["recallClass"],
        "contaminationType": contamination_type,
    }


def build_full_trace(lot_code):
    """Richer trace: adds CTEs, LIMS, inventory, node status/contact, KDE completeness."""
    lot = db.get_lot(lot_code)
    if lot is None:
        return None

    product = db.get_product(lot["product_id"]) or {}
    facility = db.get_facility(lot["origin_facility_id"]) or {}
    raw_links = db.get_raw_materials_for_lot(lot_code)
    orders = db.get_orders_for_lot(lot_code)
    cte_events = db.get_cte_for_lot(lot_code)
    lims_results = db.get_lims_results_for_lot(lot_code)
    inventory = db.get_inventory_for_lot(lot_code)
    classification, contamination_type = _classification_for_lot(lot_code)

    raw_materials = []
    for link in raw_links:
        supplier = db.get_supplier(link["supplier_id"]) or {}
        raw_materials.append({
            "supplierId": link["supplier_id"],
            "supplierName": supplier.get("supplier_name"),
            "rawMaterialLotCode": link["raw_material_lot_code"],
            "ingredientName": link["ingredient_name"],
            "tierLevel": int(link["tier_level"]) if link.get("tier_level") else None,
            "quantityUsed": link["quantity_used"],
            "unitOfMeasure": link["unit_of_measure"],
        })

    supply_chain_nodes = []
    states_affected = set()
    if facility.get("state"):
        states_affected.add(facility["state"])

    for order in orders:
        customer = db.get_customer(order["ship_to_customer_id"]) or {}
        if customer.get("state"):
            states_affected.add(customer["state"])
        supply_chain_nodes.append({
            "nodeId": customer.get("customer_id", order["ship_to_customer_id"]),
            "name": customer.get("customer_name"),
            "type": customer.get("customer_type", "DISTRIBUTOR"),
            "units": int(order["quantity_shipped"]),
            "shippedDate": order["ship_date"],
            "status": order.get("order_status"),
            "contactEmail": customer.get("contact_email"),
            "apiAvailable": customer.get("api_available_flag") == "TRUE",
            "ediApiEndpoint": customer.get("edi_api_endpoint") or None,
            "referenceDocumentNumber": order.get("reference_document_number"),
        })

    total_units_affected = sum(n["units"] for n in supply_chain_nodes) or int(lot.get("quantity_produced", 0) or 0)

    # KDE completeness check per CTE event
    incomplete_kde_nodes = []
    for evt in cte_events:
        missing = [f for f in REQUIRED_KDE_FIELDS if not (evt.get(f) or (f == "product_description"))]
        if missing:
            incomplete_kde_nodes.append({"cteId": evt["cte_id"], "missingFields": missing})

    return {
        "traceabilityLotCode": lot_code,
        "product": {
            "productId": product.get("product_id"),
            "name": product.get("product_name"),
            "description": product.get("product_description"),
            "unitOfMeasure": lot.get("unit_of_measure"),
        },
        "productionDate": lot.get("production_date"),
        "expiryDate": lot.get("expiry_date"),
        "originFacility": {
            "facilityId": facility.get("facility_id"),
            "name": facility.get("facility_name"),
            "state": facility.get("state"),
        },
        "rawMaterials": raw_materials,
        "criticalTrackingEvents": [
            {
                "cteId": e["cte_id"],
                "cteType": e["cte_type"],
                "dateTime": e["cte_date_time"],
                "locationType": e["location_type"],
                "locationId": e["location_id"],
                "fromEntity": e["from_entity"],
                "toEntity": e["to_entity"],
                "quantity": int(e["quantity"]) if e.get("quantity") else None,
                "unitOfMeasure": e["unit_of_measure"],
                "referenceDocumentNumber": e["reference_document_number"],
            } for e in cte_events
        ],
        "supplyChainNodes": supply_chain_nodes,
        "warehouseInventory": [
            {
                "inventoryId": i["inventory_id"],
                "facilityId": i["facility_id"],
                "quantityOnHand": int(i["quantity_on_hand"]) if i.get("quantity_on_hand") else 0,
                "quantityQuarantined": int(i["quantity_quarantined"]) if i.get("quantity_quarantined") else 0,
                "status": i["status"],
            } for i in inventory
        ],
        "limsResults": [
            {
                "testId": r["test_id"],
                "testType": r["test_type"],
                "result": r["result"],
                "resultValue": r["result_value"],
                "criticalLimit": r["critical_limit"],
                "testDate": r["test_date"],
                "coaDocumentRef": r["coa_document_ref"],
            } for r in lims_results
        ],
        "totalUnitsAffected": total_units_affected,
        "statesAffected": sorted(states_affected),
        "contaminationType": contamination_type,
        "recallClassEstimate": classification["recallClass"],
        "urgency": classification["urgency"],
        "incompleteKDENodes": incomplete_kde_nodes,
        "kdeCompletenessPercent": 100 if not incomplete_kde_nodes else round(
            (1 - len(incomplete_kde_nodes) / max(len(cte_events), 1)) * 100
        ),
    }
