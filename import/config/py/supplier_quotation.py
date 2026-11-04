import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from erpnext.setup.utils import get_exchange_rate

LINK_FIELDS = {
    "Supplier": ["name", "supplier_name", "default_currency"],
    "Company": ["name"],
    "Item": ["name", "item_name", "stock_uom"],
    "UOM": ["name"],
    "Warehouse": ["name"],
    "Mode of Shipment": ["name"],
    "Type Of Shipments": ["name"],
    "Country": ["name"],
    "Incoterm": ["name"],
    "Port": ["name", "port_code"],
    "Pickup Request": [
        "name", "company", "mode_of_shipment", "port_of_loading_pol",
        "port_of_destination_pod", "type_of_shipments", "country_origin",
        "pickup_date_by", "no_of_package", "gross_weight", "dimensions", "incoterm",
    ],
}

# A guest only sees these doctypes if the record belongs to the RFQ in the link
RFQ_SCOPED = {"Supplier", "Company", "Item", "Pickup Request"}


def _get_rfq(rfq):
    if not rfq or not frappe.db.exists("Request for Quotation", rfq):
        frappe.throw(_("Invalid Request for Quotation"), frappe.PermissionError)
    doc = frappe.get_doc("Request for Quotation", rfq)
    if doc.docstatus != 1:
        frappe.throw(_("This Request for Quotation is not open"), frappe.PermissionError)
    return doc


def _transport_item():
    for filters in (
        [["item_group", "=", "General services"], ["item_name", "like", "%Transport%"]],
        [["item_group", "=", "Services"]],
    ):
        rows = frappe.get_all(
            "Item",
            filters=filters,
            fields=["name", "item_name", "stock_uom"],
            limit_page_length=1,
        )
        if rows:
            return rows[0]
    return None


def _allowed_names(doctype, rfq_doc):
    if doctype == "Supplier":
        return [s.supplier for s in rfq_doc.suppliers if s.supplier]
    if doctype == "Company":
        return [rfq_doc.company]
    if doctype == "Pickup Request":
        pr = rfq_doc.get("custom_pickup_request")
        return [pr] if pr else []
    if doctype == "Item":
        names = [i.item_code for i in rfq_doc.items if i.item_code]
        t = _transport_item()
        if t:
            names.append(t["name"])
        return names
    return []


@frappe.whitelist(allow_guest=True)
def search_link(doctype, txt="", rfq=None):
    if doctype not in LINK_FIELDS:
        frappe.throw(_("Not allowed"), frappe.PermissionError)

    filters = {}
    if doctype in RFQ_SCOPED:
        names = _allowed_names(doctype, _get_rfq(rfq))
        filters["name"] = ["in", names or [""]]

    or_filters = [["name", "like", f"%{txt}%"]] if txt else []

    return frappe.get_all(
        doctype,
        fields=LINK_FIELDS[doctype],
        filters=filters,
        or_filters=or_filters,
        limit_page_length=20,
    )


@frappe.whitelist(allow_guest=True)
def get_link_record(doctype, name, rfq=None):
    if doctype not in LINK_FIELDS:
        frappe.throw(_("Not allowed"), frappe.PermissionError)

    if doctype in RFQ_SCOPED and name not in _allowed_names(doctype, _get_rfq(rfq)):
        return None

    if not frappe.db.exists(doctype, name):
        return None

    fields = [f for f in LINK_FIELDS[doctype] if f != "name"]
    rec = frappe.db.get_value(doctype, name, fields, as_dict=True) if fields else {}
    rec = rec or {}
    rec["name"] = name
    return rec


@frappe.whitelist(allow_guest=True)
def get_rfq(rfq):
    doc = _get_rfq(rfq)
    return {
        "name": doc.name,
        "company": doc.company,
        "schedule_date": doc.get("schedule_date"),
        "custom_type": doc.get("custom_type"),
        "custom_pickup_request": doc.get("custom_pickup_request"),
        "suppliers": [
            {"supplier": s.supplier, "email_id": s.email_id} for s in doc.suppliers
        ],
        "items": [
            {
                "name": i.name,
                "item_code": i.item_code,
                "item_name": i.item_name,
                "qty": i.qty,
                "uom": i.uom,
                "stock_uom": i.stock_uom,
                "conversion_factor": i.conversion_factor,
                "warehouse": i.warehouse,
                "schedule_date": i.schedule_date,
                "description": i.description,
            }
            for i in doc.items
        ],
    }


@frappe.whitelist(allow_guest=True)
def get_transport_item():
    return _transport_item()



@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def submit_quotation(data):
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = frappe._dict(data)

    rfq_doc = _get_rfq(data.get("custom_request_for_quotation"))

    supplier = data.get("supplier")
    if supplier not in [s.supplier for s in rfq_doc.suppliers]:
        frappe.throw(
            _("This supplier is not part of the Request for Quotation"),
            frappe.PermissionError,
        )

    for key in ("name", "owner", "amended_from", "docstatus", "status", "creation", "modified"):
        data.pop(key, None)

    allowed_items = set(_allowed_names("Item", rfq_doc))
    if not data.get("items"):
        frappe.throw(_("Items table is mandatory"))
    for row in data.get("items") or []:
        if row.get("item_code") not in allowed_items:
            frappe.throw(
                _("Item {0} is not part of this Request for Quotation").format(row.get("item_code"))
            )
        row["request_for_quotation"] = rfq_doc.name

    rfq_pickup = rfq_doc.get("custom_pickup_request")
    rfq_item_codes = {i.item_code for i in rfq_doc.items}
    for row in data.get("custom_pickup_details") or []:
        if row.get("pickup_request") and row.get("pickup_request") != rfq_pickup:
            frappe.throw(_("Invalid Pickup Request {0}").format(row.get("pickup_request")))
        if row.get("item_code") and row.get("item_code") not in rfq_item_codes:
            frappe.throw(
                _("Item {0} is not part of this Request for Quotation").format(row.get("item_code"))
            )

    data["doctype"] = "Supplier Quotation"
    data["company"] = rfq_doc.company
    data["custom_request_for_quotation"] = rfq_doc.name

    company_cur = frappe.get_cached_value("Company", data["company"], "default_currency")
    supplier_cur = frappe.db.get_value("Supplier", supplier, "default_currency")
    data["currency"] = supplier_cur or company_cur

    if data["currency"] == company_cur:
        data["conversion_rate"] = 1
    else:
        data["conversion_rate"] = (
            get_exchange_rate(data["currency"], company_cur, data.get("transaction_date")) or 1
        )

    original_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        doc = frappe.get_doc(data)
        doc.flags.ignore_permissions = True
        doc.insert()
        name = doc.name
    finally:
        frappe.set_user(original_user)

    return {"name": name}



def set_quotation_number(doc, method):
    if not doc.items:
        return

    # Get unique RFQs from child items
    rfqs = list({d.request_for_quotation for d in doc.items if d.request_for_quotation})

    if rfqs:
        # Join multiple RFQs with comma
        doc.quotation_number = ", ".join(rfqs)
        
        # Fetch transaction_date from the first RFQ
        first_rfq = rfqs[0]
        rfq_doc = frappe.get_doc("Request for Quotation", first_rfq)
        doc.custom_quotation_date = rfq_doc.transaction_date
    else:
        doc.quotation_number = None
        doc.custom_quotation_date = None
    
    # Fetch suppliers from Pickup Request
    if doc.custom_pickup_request:
        pickup_request = frappe.get_doc("Pickup Request", doc.custom_pickup_request)
        
        # Clear existing entries
        doc.custom_shipper_name = []
        
        # Get all suppliers from the child table (name_of_supplier)
        if pickup_request.name_of_supplier:
            for row in pickup_request.name_of_supplier:
                if row.supplier:
                    # Append as a child table row
                    doc.append("custom_shipper_name", {
                        "supplier": row.supplier  # Adjust field name if different in your child table
                    })




@frappe.whitelist(allow_guest=True)
def get_pickup_shipping_document(pickup_request, rfq):
    if not pickup_request or not rfq:
        return None

    rfq_pickup = frappe.db.get_value("Request for Quotation", rfq, "custom_pickup_request")
    if not rfq_pickup or rfq_pickup != pickup_request:
        return None

    return frappe.db.get_value("Pickup Request", pickup_request, "shipping_document")



@frappe.whitelist(allow_guest=True)
def download_shipping_document(pickup_request, rfq):
    rfq_pickup = frappe.db.get_value("Request for Quotation", rfq, "custom_pickup_request")
    if not rfq_pickup or rfq_pickup != pickup_request:
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    file_url = frappe.db.get_value("Pickup Request", pickup_request, "shipping_document")
    if not file_url:
        frappe.throw(_("No shipping document found"), frappe.DoesNotExistError)

    file_doc = frappe.get_doc("File", {"file_url": file_url})
    frappe.local.response.filename = file_doc.file_name
    frappe.local.response.filecontent = file_doc.get_content()
    frappe.local.response.type = "download"