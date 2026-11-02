# Copyright (c) 2025, Pragati Dike
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import money_in_words
from frappe.utils import formatdate


def get_supplier_email(supplier):
	"""Resolve a usable email for the supplier: Supplier.email_id -> primary Contact -> primary Address."""
	if supplier.email_id:
		return supplier.email_id

	if supplier.supplier_primary_contact:
		contact_email = frappe.db.get_value("Contact", supplier.supplier_primary_contact, "email_id")
		if contact_email:
			return contact_email

	if supplier.supplier_primary_address:
		address_email = frappe.db.get_value("Address", supplier.supplier_primary_address, "email_id")
		if address_email:
			return address_email

	return None


# @frappe.whitelist()
# def send_payment_requisition_vendor_mail(payment_requisition_name=None):
# 	payment_requisition_name = payment_requisition_name or frappe.form_dict.get("payment_requisition_name")

# 	if not payment_requisition_name:
# 		frappe.throw(_("Payment Requisition name is required"))

# 	doc = frappe.get_doc("Payment Requisition", payment_requisition_name)

# 	if not doc.supplier_name:
# 		frappe.throw(_("Supplier is not set on this Payment Requisition"))

# 	supplier_id = doc.supplier_name[0].supplier

# 	if not supplier_id:
# 		frappe.throw(_("Supplier is not set on this Payment Requisition"))

# 	supplier = frappe.get_doc("Supplier", supplier_id)

# 	email_id = get_supplier_email(supplier)

# 	if not email_id:
# 		frappe.throw(_("No email found for supplier {0}. Please set an email on the Supplier, its primary Contact, or its primary Address.").format(supplier.supplier_name))

# 	vendor_form_link = frappe.utils.get_url() + "/vendor-payment-forms?supplier=" + str(supplier_id)

# 	message_body = """
# 		Dear <b>{supplier_name}</b>,<br><br>

# 		Greetings!<br><br>

# 		Please fill out the Vendor Payment Form using the link below so we can process your payment request. Your supplier details will already be filled in.<br><br>

# 		<a href="{link}">
# 			Fill Vendor Payment Form
# 		</a><br><br>

# 		Regards,<br>
# 		Accounts Team
# 	""".format(
# 		supplier_name=frappe.utils.escape_html(supplier.supplier_name or ""),
# 		link=vendor_form_link,
# 	)

# 	frappe.sendmail(
# 		recipients=[email_id],
# 		subject="Vendor Payment Form - Please Fill",
# 		message=message_body,
# 	)

# 	frappe.response["message"] = f"Mail sent successfully to {email_id}"


@frappe.whitelist()
def send_payment_requisition_vendor_mail(payment_requisition_name=None, send_to="Both"):
	from urllib.parse import urlencode

	payment_requisition_name = payment_requisition_name or frappe.form_dict.get("payment_requisition_name")
	send_to = send_to or frappe.form_dict.get("send_to") or "Both"

	if not payment_requisition_name:
		frappe.throw(_("Payment Requisition name is required"))

	if send_to not in ("CHA", "Forwarder", "Both"):
		frappe.throw(_("Send To must be CHA, Forwarder or Both"))

	doc = frappe.get_doc("Payment Requisition", payment_requisition_name)

	# Build the list of (vendor_type, supplier_id) to send to
	targets = []
	if send_to in ("CHA", "Both"):
		if doc.cha:
			targets.append(("CHA", doc.cha))
		elif send_to == "CHA":
			frappe.throw(_("CHA is not set on this Payment Requisition"))

	if send_to in ("Forwarder", "Both"):
		if doc.forwarder:
			targets.append(("Forwarder", doc.forwarder))
		elif send_to == "Forwarder":
			frappe.throw(_("Forwarder is not set on this Payment Requisition"))

	if not targets:
		frappe.throw(_("Neither CHA nor Forwarder is set on this Payment Requisition"))

	sent = []
	skipped = []

	for vendor_type, supplier_id in targets:
		supplier = frappe.get_doc("Supplier", supplier_id)
		email_id = get_supplier_email(supplier)

		if not email_id:
			skipped.append("{0} ({1})".format(supplier.supplier_name or supplier_id, vendor_type))
			continue

		vendor_form_link = "{0}/vendor-payment-forms?{1}".format(
			frappe.utils.get_url(),
			urlencode({"supplier": supplier_id, "vendor_type": vendor_type}),
		)

		message_body = """
			Dear <b>{supplier_name}</b>,<br><br>

			Greetings!<br><br>

			Please fill out the Vendor Payment Form ({vendor_type}) using the link below so we can process your payment request. Your supplier details will already be filled in.<br><br>

			<a href="{link}">
				Fill Vendor Payment Form
			</a><br><br>

			Regards,<br>
			Accounts Team
		""".format(
			supplier_name=frappe.utils.escape_html(supplier.supplier_name or ""),
			vendor_type=vendor_type,
			link=vendor_form_link,
		)

		frappe.sendmail(
			recipients=[email_id],
			subject="Vendor Payment Form - Please Fill",
			message=message_body,
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)

		sent.append("{0} ({1}) - {2}".format(supplier.supplier_name or supplier_id, vendor_type, email_id))

	if not sent:
		frappe.throw(
			_("No email found for: {0}. Please set an email on the Supplier, its primary Contact, or its primary Address.").format(
				", ".join(skipped)
			)
		)

	message = _("Mail sent successfully to: {0}").format("<br>".join(sent))
	if skipped:
		message += "<br><br>" + _("Skipped (no email found): {0}").format(", ".join(skipped))

	frappe.response["message"] = message


@frappe.whitelist(allow_guest=True)
def get_vendor_payment_form_data(supplier=None, vendor_type=None):
	supplier = supplier or frappe.form_dict.get("supplier")
	vendor_type = vendor_type or frappe.form_dict.get("vendor_type")

	if not supplier:
		frappe.throw(_("Supplier is required"))

	filters = {"supplier": supplier}
	if vendor_type in ("CHA", "Forwarder"):
		filters["vendor_type"] = vendor_type

	existing = frappe.get_all(
		"Vendor Payment Form",
		filters=filters,
		fields=[
			"name", "vendor_type", "service_type", "invoice_no", "invoice_value",
			"boe_no", "mawb_no", "hawb_no", "remark",
		],
		order_by="modified desc",
		limit_page_length=1,
	)

	if not existing:
		frappe.response["message"] = None
		return

	data = existing[0]

	attachments = frappe.get_all(
		"Vendor CT",
		filters={"parent": data["name"], "parenttype": "Vendor Payment Form"},
		fields=["attachment"],
	)
	data["attachments"] = [a["attachment"] for a in attachments if a.get("attachment")]

	frappe.response["message"] = data

# @frappe.whitelist(allow_guest=True)
# def get_vendor_payment_form_data(supplier=None):
# 	supplier = supplier or frappe.form_dict.get("supplier")

# 	if not supplier:
# 		frappe.throw(_("Supplier is required"))

# 	existing = frappe.get_all(
# 		"Vendor Payment Form",
# 		filters={"supplier": supplier},
# 		fields=["name", "invoice_no", "invoice_value", "boe_no", "awb", "remark"],
# 		order_by="modified desc",
# 		limit_page_length=1,
# 	)

# 	if not existing:
# 		frappe.response["message"] = None
# 		return

# 	data = existing[0]

# 	attachments = frappe.get_all(
# 		"Vendor CT",
# 		filters={"parent": data["name"], "parenttype": "Vendor Payment Form"},
# 		fields=["attachment"],
# 	)
# 	data["attachments"] = [a["attachment"] for a in attachments if a.get("attachment")]

# 	frappe.response["message"] = data



class PaymentRequisition(Document):
    def validate(self):
        """Validation before save"""
        self.check_duplicate_pickup_request()
        self.doc_attachment()
        self.doc_attachment2()

    def on_submit(self):
        """On Submit actions"""
        self.mark_pickup_request_processed()
        self.create_customs_duty_journal_entry()
        self.send_mail()

    def before_cancel(self):
        """Remove Journal Entry linkage before canceling Payment Requisition"""
        if self.journal_entry:
            frappe.msgprint(
                f"Removing linkage with Journal Entry {self.journal_entry}",
                alert=True
            )
            frappe.db.set_value(
                'Payment Requisition',
                self.name,
                'journal_entry',
                None,
                update_modified=False
            )
        frappe.db.commit()
        self.flags.ignore_linked_doctypes = ['Journal Entry']

    def on_cancel(self):
        """On Cancel actions"""
        self.unmark_pickup_request_processed()

    # ---------------- Helper Methods ---------------- #

    def send_mail(self):
        """Send formatted email when Payment Requisition is submitted."""
        if not self.name:
            return

        from frappe.utils import formatdate, fmt_money, get_url_to_form

        # Format PO/WO values
        po_wo_no = ", ".join([row.purchase_order for row in self.po_wono]) if getattr(self, "po_wono", None) else ""

        # Handle supplier_name as child table (Table MultiSelect)
        supplier_names = (
            ", ".join([row.supplier for row in self.supplier_name])
            if getattr(self, "supplier_name", None) and len(self.supplier_name) > 0
            else ""
        )

        # Handle pickup_request as child table — list all linked PRs in email
        pickup_request_names = (
            ", ".join([row.pickup_request for row in self.pickup_request if row.pickup_request])
            if getattr(self, "pickup_request", None) and len(self.pickup_request) > 0
            else ""
        )

        po_wo_date = formatdate(self.get("po_wo_date") or frappe.utils.nowdate(), "dd/MM/yyyy")

        # Get all users with Accounts Manager role
        accounts_manager_users = [
            d.parent for d in frappe.get_all("Has Role", filters={"role": "Accounts Manager"}, fields=["parent"])
        ]
        recipients = [
            u.email for u in frappe.get_all(
                "User",
                filters={"name": ["in", accounts_manager_users], "enabled": 1},
                fields=["email"]
            ) if u.email
        ]

        subject = f"Payment Request No : {self.name} | Kindly release payment"

        message = f"""
        <p>Dear Sir/Ma'am,</p>
        <p>Kindly release the payment as per below request.</p>
        <table style="border-collapse: collapse; width: auto; font-family: Arial, sans-serif;">
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Payment Request No :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.name}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Payment Request Date :</b></td><td style="border:1px solid #ccc; padding:6px;">{formatdate(self.creation, "dd/MM/yyyy")}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Pickup Request(s) :</b></td><td style="border:1px solid #ccc; padding:6px;">{pickup_request_names}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Favoring Of :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.favoring_of or ''}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Country of Origin :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.origin or ''}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Country Of Consignment :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.consignment or ''}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Mode Of Shipment :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.mode_of_shipment or ''}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Payable At :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.payable_at or ''}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Payment By :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.payment_by or ''}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Payment Required :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.payment_required or ''}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>PO/WO No :</b></td><td style="border:1px solid #ccc; padding:6px;">{po_wo_no}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>PO/WO Date :</b></td><td style="border:1px solid #ccc; padding:6px;">{po_wo_date}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Material Type :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.type_of_materials or ''}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Supplier Name :</b></td><td style="border:1px solid #ccc; padding:6px;">{supplier_names}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Amount :</b></td><td style="border:1px solid #ccc; padding:6px;">{fmt_money(self.duty_amount)}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Amount in Words :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.duty_amount_in_word or ''}</td></tr>
            <tr><td style="border:1px solid #ccc; padding:6px;"><b>Special Remark :</b></td><td style="border:1px solid #ccc; padding:6px;">{self.specific_remark or ''}</td></tr>
        </table>
        <br>
        <p>Please click the below link for more details:</p>
        <p><a href="{get_url_to_form('Journal Entry', self.journal_entry)}" target="_blank">View Journal Entry</a></p>
        <br>
        <p>Thanking you,<br>{frappe.session.user_fullname}</p>
        """

        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            delayed=False,
            reference_doctype=self.doctype,
            reference_name=self.name,
        )

        frappe.msgprint("📨 Email notification sent successfully to Accounts Manager(s).")

    def check_duplicate_pickup_request(self):
        """Ensure no Pickup Request is already used in another active Payment Requisition"""
        if not self.pickup_request:
            return

        for row in self.pickup_request:
            pr_name = row.pickup_request
            if not pr_name:
                continue

            existing = frappe.db.sql("""
                SELECT prc.parent
                FROM `tabPickup Request CT` prc
                JOIN `tabPayment Requisition` pr ON pr.name = prc.parent
                WHERE prc.pickup_request = %s
                  AND pr.docstatus != 2
                  AND pr.name != %s
                LIMIT 1
            """, (pr_name, self.name), as_dict=1)

            if existing:
                frappe.throw(
                    _('Pickup Request {0} is already linked to Payment Requisition {1}').format(
                        pr_name, existing[0].parent
                    )
                )

    def mark_pickup_request_processed(self):
        """Mark all linked Pickup Requests as processed on submit"""
        for row in self.pickup_request:
            if row.pickup_request:
                frappe.db.set_value('Pickup Request', row.pickup_request, 'po_updated', 1)

    def unmark_pickup_request_processed(self):
        """Unmark all linked Pickup Requests when cancelled"""
        for row in self.pickup_request:
            if row.pickup_request:
                frappe.db.set_value('Pickup Request', row.pickup_request, 'po_updated', 0)

    def doc_attachment(self):
        """Validate minimum 3 required documents for Manager Approval"""
        if self.workflow_state == "Sent For Manager Approval":
            required_docs = ["Checklist", "Commercial Invoice", "AWB", "PO", "BOE"]
            attached_docs = [d.description for d in self.attach_document]
            matched_count = sum(1 for rd in required_docs if rd in attached_docs)
            if matched_count < 3:
                frappe.throw(
                    f"At least 3 out of 5 required Document Attachments must be present. "
                    f"Currently found: {matched_count}"
                )

    def doc_attachment2(self):
        """Validate minimum 4 required documents for Account Team Approval"""
        if self.workflow_state == "Sent For Account Team Approval":
            required_docs = ["Checklist", "Commercial Invoice", "AWB", "PO", "BOE"]
            attached_docs = [d.description for d in self.attach_document]
            matched_count = sum(1 for rd in required_docs if rd in attached_docs)
            if matched_count < 4:
                frappe.throw(
                    f"At least 4 out of 5 required Document Attachments must be present. "
                    f"Currently found: {matched_count}"
                )

    def create_customs_duty_journal_entry(self):
        """Auto-create a Journal Entry for Customs Duty on submit"""
        from frappe.utils import flt, nowdate

        total_customs_duty = (
            flt(self.bcd)
            + flt(self.igst)
            + flt(self.health_cess)
            + flt(self.sw_surcharge)
        )

        if total_customs_duty <= 0:
            frappe.msgprint(_("No Customs Duty amount found, Journal Entry not created."))
            return

        # Get company details
        company = frappe.get_doc("Company", self.company)
        company_abbr = company.abbr
        customs_duty_expense_account = f"Customs Duty Expense - {company_abbr}"

        # Get Payable Account dynamically from Company
        duty_payable_account = company.default_customs_expense_account
        if not duty_payable_account:
            frappe.throw(_("Please set 'Default Customs Expense Account' in Company {0}.").format(self.company))

        account_type = frappe.db.get_value("Account", duty_payable_account, "account_type")

        # Build comma-separated PO numbers
        po_list = []
        if hasattr(self, "po_wono") and self.po_wono:
            po_list = [d.purchase_order for d in self.po_wono if d.purchase_order]
        po_numbers = ", ".join(po_list) if po_list else "N/A"

        # Fetch port code from first linked Pickup Request
        port_code = None
        if self.pickup_request and len(self.pickup_request) > 0:
            first_pr = self.pickup_request[0].pickup_request
            if first_pr:
                port_code = frappe.db.get_value(
                    "Pickup Request", first_pr, "port_of_destination_pod"
                )

        # Build pickup request names for remark
        pr_names = ", ".join(
            [row.pickup_request for row in self.pickup_request if row.pickup_request]
        ) if self.pickup_request else ""

        # Create Journal Entry
        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = nowdate()
        je.custom_payment_requisition = self.name
        je.company = self.company
        je.user_remark = (
            f"Being Duty payable against {self.name}, Job No. {self.job_no or ''}, "
            f"PO No. {po_numbers}, BE No. {self.boe_number or ''} Dt. {self.boe_date or ''}"
        )
        je.cheque_no = self.name
        je.cheque_date = self.posting_date

        # Duty Splits
        igst_amount = flt(self.igst)
        other_duties = flt(self.bcd) + flt(self.health_cess) + flt(self.sw_surcharge)

        # Debit Entry – Other Duties
        if other_duties > 0:
            je.append("accounts", {
                "account": customs_duty_expense_account,
                "debit_in_account_currency": other_duties,
                "cost_center": getattr(self, "cost_center", None),
                "custom_bill_of_entry_no": self.boe_details,
                "custom_bill_of_entry_date": self.boe_date,
                "custom_port_code": port_code
            })

        # Debit Entry – IGST
        if igst_amount > 0:
            je.append("accounts", {
                "account": "22451700 - IGST RECEIVABLE (IMPORT) - MCPL",
                "debit_in_account_currency": igst_amount,
                "cost_center": getattr(self, "cost_center", None),
                "custom_bill_of_entry_no": self.boe_details,
                "custom_bill_of_entry_date": self.boe_date,
                "custom_port_code": port_code
            })

        # Credit Entry – Duty Payable
        credit_entry = {
            "account": duty_payable_account,
            "credit_in_account_currency": total_customs_duty,
        }

        # Set party — prefer payment_to, fallback to first supplier in child table
        if getattr(self, "payment_to", None):
            credit_entry.update({
                "party_type": "Supplier",
                "party": self.payment_to
            })
        elif account_type == "Payable" and getattr(self, "supplier_name", None):
            if len(self.supplier_name) > 0:
                first_supplier = self.supplier_name[0].supplier
                if first_supplier:
                    credit_entry.update({
                        "party_type": "Supplier",
                        "party": first_supplier
                    })

        credit_entry.update({
            "custom_bill_of_entry_no": self.boe_details,
            "custom_bill_of_entry_date": self.boe_date,
            "custom_port_code": port_code
        })

        je.append("accounts", credit_entry)

        je.insert(ignore_permissions=True)

        self.db_set("journal_entry", je.name)

        frappe.msgprint(
            f"✅ Journal Entry <a href='/app/journal-entry/{je.name}'>{je.name}</a> created for Customs Duty."
        )


# ---------------- Whitelisted Methods ---------------- #

@frappe.whitelist()
def get_amount_in_words(amount):
    """Convert numeric amount to words"""
    try:
        return money_in_words(amount)
    except Exception as e:
        frappe.log_error(f"Money in words error: {str(e)}", "Payment Requisition")
        return ""


@frappe.whitelist()
def get_available_pickup_requests():
    """
    Return all submitted Pickup Requests not yet linked to any active Payment Requisition.
    Excludes via the Pickup Request CT child table.
    """
    # Get all pickup requests already linked via child table
    used_records = frappe.db.sql("""
        SELECT DISTINCT prc.pickup_request
        FROM `tabPickup Request CT` prc
        JOIN `tabPayment Requisition` pr ON pr.name = prc.parent
        WHERE pr.docstatus IN (0, 1)
          AND prc.pickup_request IS NOT NULL
          AND prc.pickup_request != ''
    """, as_list=1)

    used_names = [r[0] for r in used_records if r[0]]

    if used_names:
        placeholders = ", ".join(["%s"] * len(used_names))
        query = f"""
            SELECT
                pr.name,
                pr.po_date,
                pr.company,
                pr.incoterm,
                pr.mode_of_shipment,
                pr.country_origin,
                pr.grand_total,
                pr.currency
            FROM `tabPickup Request` pr
            WHERE pr.docstatus = 1
              AND pr.name NOT IN ({placeholders})
            ORDER BY pr.modified DESC
        """
        results = frappe.db.sql(query, values=used_names, as_dict=1)
    else:
        results = frappe.db.sql("""
            SELECT
                pr.name,
                pr.po_date,
                pr.company,
                pr.incoterm,
                pr.mode_of_shipment,
                pr.country_origin,
                pr.grand_total,
                pr.currency
            FROM `tabPickup Request` pr
            WHERE pr.docstatus = 1
            ORDER BY pr.modified DESC
        """, as_dict=1)

    for row in results:
        suppliers = frappe.get_all(
            "Supplier CT",
            filters={"parent": row.name, "parenttype": "Pickup Request"},
            fields=["supplier"],
            pluck="supplier"
        )
        row['supplier_name'] = ", ".join(suppliers) if suppliers else ""

    return results


@frappe.whitelist()
def get_pickup_request_details(pickup_requests):
    """
    Fetch and merge details from multiple pickup requests.
    Accepts a JSON string or list of pickup request names.
    """
    import json
    if isinstance(pickup_requests, str):
        pickup_requests = json.loads(pickup_requests)

    if not pickup_requests:
        frappe.throw(_("At least one Pickup Request is required"))

    all_po_list = []
    all_suppliers = []
    seen_suppliers = set()
    all_items = []
    first_pr_doc = None

    for pr_name in pickup_requests:
        pr_doc = frappe.get_doc("Pickup Request", pr_name)
        if not first_pr_doc:
            first_pr_doc = pr_doc

        # Merge POs
        po_list = frappe.get_all(
            "PO CT",
            filters={"parent": pr_name, "parenttype": "Pickup Request"},
            fields=["purchase_order"]
        )
        all_po_list.extend(po_list)

        # Merge Suppliers (deduplicated)
        suppliers = frappe.get_all(
            "Supplier CT",
            filters={"parent": pr_name, "parenttype": "Pickup Request"},
            fields=["supplier"],
            pluck="supplier"
        )
        for s in suppliers:
            if s and s not in seen_suppliers:
                all_suppliers.append(s)
                seen_suppliers.add(s)

        # Merge Items
        items = frappe.get_all(
            "Purchase Order Details",
            filters={"parent": pr_name, "parenttype": "Pickup Request"},
            fields=["item", "material", "material_desc"],
            order_by="idx"
        )
        for item in items:
            all_items.append({
                "item": item.get("item"),
                "description": item.get("material_desc") or item.get("material"),
                "pickup_request": pr_name
            })

    return {
        "mode_of_shipment": first_pr_doc.mode_of_shipment,
        "country_origin": first_pr_doc.country_origin,
        "company": first_pr_doc.company,
        "po_date": first_pr_doc.po_date,
        "supplier_name": ", ".join(all_suppliers),
        "po_list": all_po_list,
        "items": all_items
    }


@frappe.whitelist()
def validate_pickup_request(pickup_request):
    """
    Check if a Pickup Request is already linked to an active Payment Requisition.
    Returns dict with 'exists' boolean and 'payment_requisition' name if found.
    """
    if not pickup_request:
        return {"exists": False}

    existing = frappe.db.sql("""
        SELECT prc.parent
        FROM `tabPickup Request CT` prc
        JOIN `tabPayment Requisition` pr ON pr.name = prc.parent
        WHERE prc.pickup_request = %s
          AND pr.docstatus IN (0, 1)
        LIMIT 1
    """, (pickup_request,), as_dict=1)

    if existing:
        return {
            "exists": True,
            "payment_requisition": existing[0].parent
        }

    return {"exists": False}
