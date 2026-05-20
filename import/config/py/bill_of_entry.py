import frappe

def update_payment_request(doc, method):
    # Step 1: Extract PO numbers from BOE child table
    po_nos = [po_row.purchase_order for po_row in doc.po_no if po_row.purchase_order]
    if not po_nos:
        frappe.msgprint("No Purchase Orders found in BOE")
        return

    # Step 2: Extract Pickup Request numbers from BOE child table
    pck_nos = [pck_row.pickup_request for pck_row in doc.pickup_request if pck_row.pickup_request]
    if not pck_nos:
        frappe.msgprint("No Pickup Requests found in BOE")
        return

    # Step 3: Find Payment Requisitions linked via PO CT child table
    linked_prs_by_po = frappe.get_all(
        "PO CT",
        filters={
            "purchase_order": ["in", po_nos],
            "parenttype": "Payment Requisition"
        },
        fields=["parent"],
        ignore_permissions=True
    )

    if not linked_prs_by_po:
        frappe.msgprint("No Payment Requisitions found for linked POs")
        return

    po_pr_names = set([r.parent for r in linked_prs_by_po])

    # Step 4: Find Payment Requisitions linked via Pickup Request CT child table
    linked_prs_by_pck = frappe.get_all(
        "Pickup Request CT",
        filters={
            "pickup_request": ["in", pck_nos],
            "parenttype": "Payment Requisition"
        },
        fields=["parent"],
        ignore_permissions=True
    )

    if not linked_prs_by_pck:
        frappe.msgprint("No Payment Requisitions found for linked Pickup Requests")
        return

    pck_pr_names = set([r.parent for r in linked_prs_by_pck])

    # Step 5: Only process PRFs that match BOTH PO and Pickup Request
    # This avoids updating old submitted PRFs linked to same PO but different pickup
    pr_names = list(po_pr_names.intersection(pck_pr_names))

    if not pr_names:
        frappe.msgprint("No matching Payment Requisitions found for both PO and Pickup Request")
        return

    for pr_name in pr_names:
        pr_doc = frappe.get_doc("Payment Requisition", pr_name)

        # Calculate duty amount
        duty_amount = (
            doc.igst_amount +
            doc.bcd_amount +
            doc.h_cess_amount +
            doc.sws_amount
        )

        # Set all fields directly on the doc
        pr_doc.bill_of_entry_created = 1
        pr_doc.boe_details = doc.name
        pr_doc.boe_date = doc.boe_date
        pr_doc.bcd = doc.bcd_amount
        pr_doc.igst = doc.igst_amount
        pr_doc.cha = doc.cha
        pr_doc.total = duty_amount
        pr_doc.assessable_value = doc.accessible_value
        pr_doc.health_cess = doc.h_cess_amount
        pr_doc.penalty = doc.penalty
        pr_doc.sw_surcharge = doc.sws_amount
        pr_doc.job_no = doc.job_number
        pr_doc.duty_amount = duty_amount
        pr_doc.boe_number = doc.boe_number

        # Attach BOE file if not already attached
        if doc.attach_boe:
            already_attached = any(
                row.description == "BOE" and row.attach_file == doc.attach_boe
                for row in pr_doc.attach_document
            )
            if not already_attached:
                pr_doc.append("attach_document", {
                    "description": "BOE",
                    "attach_file": doc.attach_boe
                })

        # Save the doc
        pr_doc.flags.ignore_permissions = True
        pr_doc.flags.ignore_validate = True
        pr_doc.save()

        frappe.db.commit()

    # Store PR name for client-side redirect
    frappe.db.set_value("BOE", doc.name, "payment_requisition", pr_names[0])
    doc.payment_requisition = pr_names[0]



# import frappe

# def update_payment_request(doc, method):
#     # Step 1: Extract PO numbers from BOE child table
#     po_nos = [po_row.purchase_order for po_row in doc.po_no if po_row.purchase_order]
#     if not po_nos:
#         frappe.msgprint("No Purchase Orders found in BOE")
#         return

#     # Step 2: Find Payment Requisitions linked via child table 'PO CT'
#     linked_prs = frappe.get_all(
#         "PO CT",
#         filters={
#             "purchase_order": ["in", po_nos],
#             "parenttype": "Payment Requisition"
#         },
#         fields=["parent"],
#         ignore_permissions=True
#     )

#     if not linked_prs:
#         frappe.msgprint("No Payment Requisitions found for linked POs")
#         return

#     pr_names = list(set([r.parent for r in linked_prs]))

#     for pr_name in pr_names:
#         pr_doc = frappe.get_doc("Payment Requisition", pr_name)

#         # Set all fields directly on the doc
#         pr_doc.bill_of_entry_created = 1
#         pr_doc.boe_details = doc.name
#         pr_doc.boe_date = doc.boe_date
#         pr_doc.bcd = doc.bcd_amount
#         pr_doc.igst = doc.igst_amount
#         pr_doc.cha = doc.cha
#         pr_doc.total = doc.igst_amount + doc.bcd_amount + doc.h_cess_amount + doc.sws_amount
#         pr_doc.assessable_value = doc.accessible_value
#         pr_doc.health_cess = doc.h_cess_amount
#         pr_doc.penalty = doc.penalty
#         pr_doc.sw_surcharge = doc.sws_amount
#         pr_doc.job_no = doc.job_number
#         pr_doc.duty_amount = doc.igst_amount + doc.bcd_amount + doc.h_cess_amount + doc.sws_amount
#         pr_doc.boe_number = doc.boe_number

#         # Attach BOE file if not already attached
#         if doc.attach_boe:
#             already_attached = any(
#                 row.description == "BOE" and row.attach_file == doc.attach_boe
#                 for row in pr_doc.attach_document
#             )
#             if not already_attached:
#                 pr_doc.append("attach_document", {
#                     "description": "BOE",
#                     "attach_file": doc.attach_boe
#                 })

#         # ✅ Save the full doc — commits everything to DB properly
#         pr_doc.flags.ignore_permissions = True
#         pr_doc.flags.ignore_validate = True  # skip unnecessary validations
#         pr_doc.save()

#         frappe.db.commit()  # ensure changes are committed before redirect

#     # Store PR name for client-side redirect
#     frappe.db.set_value("BOE", doc.name, "payment_requisition", pr_names[0])
#     doc.payment_requisition = pr_names[0]

