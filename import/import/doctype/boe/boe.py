# # # # Copyright (c) 2025, Pragati Dike and contributors
# # # #  For license information, please see license.txt



import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.document import Document
from frappe.utils import nowdate


@frappe.whitelist()
def create_boe(payment_requisition):
    pr_doc = frappe.get_doc("Payment Requisition", payment_requisition)

    boe = frappe.new_doc("BOE")
    boe.cha = pr_doc.cha
    boe.boe_date = frappe.utils.nowdate()
    boe.payment_requisition = pr_doc.name

    # ✅ Calculate total_inr_value as sum of base_total from all linked Pickup Requests
    total_inr_value = 0

    if hasattr(pr_doc, "pickup_request"):
        for row in pr_doc.pickup_request:
            boe.append("pickup_request", {"pickup_request": row.pickup_request})
            try:
                pck_doc = frappe.get_doc("Pickup Request", row.pickup_request)
                total_inr_value += flt(getattr(pck_doc, "base_total", 0))
            except Exception:
                pass  # Skip if Pickup Request not found

    boe.total_inr_value = total_inr_value

    if hasattr(pr_doc, "po_wono"):
        for row in pr_doc.po_wono:
            boe.append("po_no", {"purchase_order": row.purchase_order})

    if hasattr(pr_doc, "supplier_name"):
        for row in pr_doc.supplier_name:
            boe.append("vendor", {"supplier": row.supplier})
    elif getattr(pr_doc, "supplier_name", None):
        boe.append("vendor", {"supplier": pr_doc.supplier_name})

    boe.insert(ignore_permissions=True)
    frappe.db.commit()

    return boe.name


@frappe.whitelist()
def sync_boe_to_payment_requisition(boe_name):
    boe = frappe.get_doc("BOE", boe_name)

    if not boe.payment_requisition:
        frappe.throw(_("No Payment Requisition linked to this BOE."))

    pr = frappe.get_doc("Payment Requisition", boe.payment_requisition)

    if pr.docstatus == 1:
        frappe.throw(_(
            "Payment Requisition {0} is already submitted. Cannot update BOE details."
        ).format(pr.name))

    # BOE reference fields
    pr.bill_of_entry_created = 1
    pr.boe_details           = boe.name
    pr.boe_date              = boe.boe_date
    pr.boe_number            = boe.boe_number

    # Duty breakdown fields
    pr.bcd                   = flt(boe.bcd_amount)
    pr.igst                  = flt(boe.igst_amount)
    pr.health_cess           = flt(boe.h_cess_amount)
    pr.sw_surcharge          = flt(boe.sws_amount)
    pr.penalty               = flt(boe.penalty)
    pr.assessable_value      = flt(boe.accessible_value)

    # Other BOE fields
    pr.cha                   = boe.cha
    pr.job_no                = boe.job_number

    # Recalculate duty_amount total
    pr.duty_amount = (
        flt(boe.bcd_amount)
        + flt(boe.igst_amount)
        + flt(boe.h_cess_amount)
        + flt(boe.sws_amount)
    )
    pr.total = pr.duty_amount

    # Attach BOE file to PR's attach_document child table if not already present
    if boe.attach_boe:
        already_attached = any(
            row.description == "BOE" and row.attach_file == boe.attach_boe
            for row in pr.attach_document
        )
        if not already_attached:
            pr.append("attach_document", {
                "description": "BOE",
                "attach_file": boe.attach_boe
            })

    pr.flags.ignore_permissions = True
    pr.flags.ignore_validate = True
    pr.save()
    frappe.db.commit()

    return {"success": True, "payment_requisition": pr.name}

class BOE(Document):
    pass
   