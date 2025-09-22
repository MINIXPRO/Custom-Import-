# Copyright (c) 2025, Pragati Dike and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.pdf import get_pdf
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import nowdate
import json
from frappe.utils import flt
from frappe.utils import money_in_words
from erpnext.controllers.buying_controller import BuyingController
from frappe.utils import get_url

class PickupRequest(Document):
   
    def validate(self):
        self.set_missing_values()
        self.calculate_totals()
        # Apply tax template if taxes_and_charges is set but purchase_taxes_and_charges is empty
        if self.taxes_and_charges and not self.get("purchase_taxes_and_charges"):
            self.apply_taxes_and_charges_template()
        self.calculate_taxes_and_totals()
        
    def before_save(self):
        self.calculate_taxes_and_totals()
    
    def set_missing_values(self):
        """Set missing values"""
        # Set tax category based on supplier or company
        if not self.tax_category and self.get('name_of_supplier'):
            supplier_tax_category = frappe.get_cached_value("Supplier", self.name_of_supplier, "tax_category")
            if supplier_tax_category:
                self.tax_category = supplier_tax_category
        
        if not self.tax_category and self.company:
            company_tax_category = frappe.get_cached_value("Company", self.company, "tax_category")
            if company_tax_category:
                self.tax_category = company_tax_category
        
        # Set default currency
        if not self.get('currency'):
            self.currency = frappe.get_cached_value("Company", self.company, "default_currency") or "INR"
        
        # Set default conversion rate - check multiple possible field names
        if not self.get('conversion_rate'):
            # Try to get from purchase order details first
            if self.get("purchase_order_details"):
                for item in self.purchase_order_details:
                    if item.get("currency_rate"):
                        self.conversion_rate = flt(item.currency_rate, 1.0)
                        break
            
            # If still not set, default to 1.0
            if not self.get('conversion_rate'):
                self.conversion_rate = 1.0

    def calculate_totals(self):
        """Calculate basic totals from items"""
        self.total_amount = 0
        self.total_quantity = 0
        self.total_picked_quantity = 0
        
        if self.get("purchase_order_details"):
            for item in self.purchase_order_details:
                amount = flt(item.get("amount_in_inr", 0)) or flt(item.get("amount", 0))
                self.total_amount += amount
                self.total_quantity += flt(item.get("quantity", 0))
                self.total_picked_quantity += flt(item.get("pick_qty", 0))
        
        # Set net totals for tax calculations
        self.base_net_total = self.total_amount
        self.net_total = self.total_amount / flt(self.get('conversion_rate', 1), 1)

    @frappe.whitelist()
    def calculate_taxes_and_totals(self):
        """Calculate taxes and totals"""
        # Ensure conversion_rate is set
        if not self.get('conversion_rate'):
            self.conversion_rate = 1.0
            
        if not self.get("purchase_taxes_and_charges"):
            self.base_total_taxes_and_charges = 0
            self.total_taxes_and_charges = 0
            self.set_grand_total()
            return
            
        # Initialize totals
        self.base_total_taxes_and_charges = 0
        self.total_taxes_and_charges = 0
        
        # Get base net total
        base_net_total = flt(self.total_amount, 0)
        
        if base_net_total == 0:
            self.base_total_taxes_and_charges = 0
            self.total_taxes_and_charges = 0
            self.set_grand_total()
            return
        
        cumulative_total = base_net_total
        
        for tax in self.get("purchase_taxes_and_charges"):
            # Ensure rate is a float
            tax_rate = flt(tax.get("rate", 0))
            
            # Calculate tax amount based on charge type
            if tax.charge_type == "On Net Total":
                tax.base_tax_amount = flt((base_net_total * tax_rate) / 100)
            elif tax.charge_type == "On Previous Row Amount":
                if tax.row_id and int(tax.row_id) <= len(self.purchase_taxes_and_charges):
                    try:
                        previous_row = self.purchase_taxes_and_charges[int(tax.row_id) - 1]
                        prev_amount = flt(previous_row.get("base_tax_amount", 0))
                        tax.base_tax_amount = flt((prev_amount * tax_rate) / 100)
                    except (IndexError, ValueError):
                        tax.base_tax_amount = 0
                else:
                    tax.base_tax_amount = 0
            elif tax.charge_type == "On Previous Row Total":
                if tax.row_id and int(tax.row_id) <= len(self.purchase_taxes_and_charges):
                    try:
                        previous_row = self.purchase_taxes_and_charges[int(tax.row_id) - 1]
                        prev_total = flt(previous_row.get("base_total", 0))
                        tax.base_tax_amount = flt((prev_total * tax_rate) / 100)
                    except (IndexError, ValueError):
                        tax.base_tax_amount = 0
                else:
                    tax.base_tax_amount = 0
            elif tax.charge_type == "Actual":
                tax.base_tax_amount = flt(tax.get("tax_amount", 0))
            else:
                # Default: On Net Total
                tax.base_tax_amount = flt((base_net_total * tax_rate) / 100)
            
            # Apply add/deduct logic
            if tax.get("add_deduct_tax") == "Deduct":
                tax.base_tax_amount = -1 * abs(flt(tax.base_tax_amount))
            else:
                tax.base_tax_amount = abs(flt(tax.base_tax_amount))
            
            # Handle currency conversion
            conversion_rate = flt(self.get('conversion_rate', 1), 1)
            tax.tax_amount = flt(tax.base_tax_amount / conversion_rate)
            
            # Calculate running totals
            if tax.get("add_deduct_tax") == "Deduct":
                cumulative_total -= abs(flt(tax.base_tax_amount))
            else:
                cumulative_total += abs(flt(tax.base_tax_amount))
            
            tax.base_total = flt(cumulative_total)
            tax.total = flt(tax.base_total / conversion_rate)
            
            # Add to total taxes (always positive for display)
            if tax.get("add_deduct_tax") == "Deduct":
                self.base_total_taxes_and_charges -= abs(flt(tax.base_tax_amount))
            else:
                self.base_total_taxes_and_charges += abs(flt(tax.base_tax_amount))
        
        # Set final total taxes
        conversion_rate = flt(self.get('conversion_rate', 1), 1)
        self.total_taxes_and_charges = flt(self.base_total_taxes_and_charges / conversion_rate)
        
        # Set grand totals
        self.set_grand_total()

    def set_grand_total(self):
        """Set grand total fields"""
        base_net_total = flt(self.total_amount, 0)
        self.base_grand_total = flt(base_net_total + self.base_total_taxes_and_charges)
        self.grand_total = flt(self.total) + flt(self.taxes_and_charges_added)
        
    @frappe.whitelist()
    def apply_taxes_and_charges_template(self):
        """Apply taxes and charges template"""
        if not self.taxes_and_charges:
            return
            
        # Clear existing taxes
        self.purchase_taxes_and_charges = []
        
        # Get template
        template = frappe.get_doc("Purchase Taxes and Charges Template", self.taxes_and_charges)
        
        # Add taxes from template
        for tax in template.taxes:
            tax_row = {
                "charge_type": tax.charge_type,
                "row_id": tax.row_id,
                "account_head": tax.account_head,
                "description": tax.description,
                "rate": tax.rate,
                "cost_center": tax.cost_center,
                "tax_amount": tax.tax_amount,
                "add_deduct_tax": tax.add_deduct_tax,
                "category": tax.category,
                "included_in_print_rate": tax.included_in_print_rate,
                "included_in_paid_amount": tax.included_in_paid_amount
            }
            self.append("purchase_taxes_and_charges", tax_row)
        
        # Calculate taxes after adding
        self.calculate_taxes_and_totals()

    @frappe.whitelist()
    def get_items(self, po):
        self.purchase_order_details = []
        for i in po:
            doc = frappe.get_doc("Purchase Order", i.get("po_number"))
            for j in doc.items:
                self.append(
                    "purchase_order_details",
                    {
                        "item": j.item_code,
                        "material": j.item_name,
                        "quantity": j.qty,
                        "po_number": i.get("po_number"),
                        "material_desc": j.description,
                    },
                )

# Utility methods that can be called from client side
@frappe.whitelist()
def get_tax_template_taxes(template_name):
    """Get taxes from tax template"""
    if not template_name:
        return []
    
    try:
        template = frappe.get_doc("Purchase Taxes and Charges Template", template_name)
        taxes = []
        
        for tax in template.taxes:
            taxes.append({
                "charge_type": tax.charge_type,
                "row_id": tax.row_id,
                "account_head": tax.account_head,
                "description": tax.description,
                "rate": tax.rate,
                "cost_center": tax.cost_center,
                "tax_amount": tax.tax_amount,
                "add_deduct_tax": tax.add_deduct_tax,
                "category": tax.category,
                "included_in_print_rate": tax.included_in_print_rate,
                "included_in_paid_amount": tax.included_in_paid_amount
            })
        
        return taxes
    except Exception as e:
        frappe.throw(_("Error fetching tax template: {0}").format(str(e)))

@frappe.whitelist()
def apply_tax_template_to_pickup_request(pickup_request_name, template_name):
    """Apply tax template to pickup request - can be called from client side"""
    try:
        doc = frappe.get_doc("Pickup Request", pickup_request_name)
        doc.taxes_and_charges = template_name
        doc.apply_taxes_and_charges_template()
        doc.save()
        return {
            "purchase_taxes_and_charges": doc.purchase_taxes_and_charges,
            "base_total_taxes_and_charges": doc.base_total_taxes_and_charges,
            "total_taxes_and_charges": doc.total_taxes_and_charges,
            "base_grand_total": doc.base_grand_total,
            "grand_total": doc.grand_total
        }
    except Exception as e:
        frappe.throw(_("Error applying tax template: {0}").format(str(e)))

@frappe.whitelist()
def get_supplier_tax_category(supplier):
    """Get tax category from supplier"""
    if not supplier:
        return None
    return frappe.get_cached_value("Supplier", supplier, "tax_category")

@frappe.whitelist()
def get_company_tax_category(company):
    """Get tax category from company"""
    if not company:
        return None
    return frappe.get_cached_value("Company", company, "tax_category")

@frappe.whitelist()
def get_items_details(parent, item_name):
    parent_data = frappe.db.sql(" select currency,conversion_rate from `tabPurchase Order` where name=%s ", (parent), as_dict=True)
    child_data = frappe.db.sql(" select rate from `tabPurchase Order Item` where parent=%s and item_code=%s ", (parent, item_name), as_dict=True)
    return parent_data, child_data

@frappe.whitelist()
def validate_po_order_qty_to_pickup_qty(po_no, item_code):
    data = frappe.db.sql(" select received_qty, qty from `tabPurchase Order Item` where parent=%s and item_code=%s ",(po_no, item_code), as_dict=True)
    return data

# @frappe.whitelist()
# def get_po_all_details(po_name):
#     data = frappe.get_doc("Purchase Order", po_name)
#     return data

# import/import/doctype/pickup_request/pickup_request.py

@frappe.whitelist()
def get_po_all_details(po_name):
    po = frappe.get_doc("Purchase Order", po_name)

    details = {
        "name": po.name,
        "supplier": po.supplier,
        "supplier_name": po.get("supplier_name"),
        "transaction_date": po.get("transaction_date"),
        "custom_purchase_type": po.get("custom_purchase_type"),
        "currency": po.get("currency"),
        "conversion_rate": po.get("conversion_rate"),
        "company": po.get("company"),
        "custom_port_of_loading_pol": po.get("custom_port_of_loading_pol"),
        "custom_port_of_destination_pod": po.get("custom_port_of_destination_pod"),
        "incoterm": po.get("incoterm"),
        "taxes_and_charges": po.get("taxes_and_charges"),
        "tax_category": po.get("tax_category"),
        "billing_address": po.get("billing_address"),
        # return child tables
        "items": [d.as_dict() for d in po.get("items")],
        # return taxes child table (list) if present, else empty list
        "taxes": [t.as_dict() for t in po.get("taxes")] if po.get("taxes") else []
    }
    return details


@frappe.whitelist()
def attach_po_pdf_to_pickup_request(po_name, pickup_request_name, format_name="Standard"):
    """Generate Purchase Order PDF from print format and attach it to Pickup Request."""
    if not frappe.has_permission("Purchase Order", "read", po_name):
        frappe.throw(_("Not permitted"))

    html = frappe.get_print("Purchase Order", po_name, format_name)
    pdf_data = get_pdf(html)

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"PO-{po_name}.pdf",
        "attached_to_doctype": "Pickup Request",
        "attached_to_name": pickup_request_name,
        "content": pdf_data,
        "is_private": 1
    })
    file_doc.save(ignore_permissions=True)
    return file_doc.name  

@frappe.whitelist()
def get_suppliers_dialog_data(pickup_request):
    return [
        {"supplier": s.name, "email_id": s.email_id or ""}
        for s in frappe.get_all("Supplier", fields=["name", "email_id"])
    ]

# @frappe.whitelist()
# def create_rfq_from_pickup_request(pickup_request, suppliers, email_template):
#     if not suppliers:
#         frappe.throw("Please add at least one supplier.")
    
#     suppliers = json.loads(suppliers)
#     pickup = frappe.get_doc("Pickup Request", pickup_request)
#     email_template_doc = frappe.get_doc("Email Template", email_template)
#     message_for_supplier = email_template_doc.response or ""
#     company_abbr = frappe.db.get_value("Company", pickup.company, "abbr")

#     rfq = frappe.new_doc("Request for Quotation")
#     rfq.transaction_date = nowdate()
#     rfq.custom_pickup_request = pickup.name
#     rfq.message_for_supplier = message_for_supplier
#     rfq.custom_type = "Logistics"
#     # rfq.billing_address = pickup.company_address
#     # rfq.custom_shipment_address = pickup.company_address
#     rfq.custom_no_of_pkg_units = pickup.no_of_package
#     rfq.custom_shipment_type = pickup.type_of_shipments

#     # Add suppliers with email from Supplier doctype
#     for sup in suppliers:
#         supplier_name = sup.get("supplier")
#         supplier_doc = frappe.get_doc("Supplier", supplier_name)

#         rfq.append("suppliers", {
#             "supplier": supplier_name,
#             "email_id": supplier_doc.email_id or ""
#         })

#     # Add items
#     for item in pickup.purchase_order_details:
#         item_doc = frappe.get_doc("Item", item.item)
#         conversion_factor = 1
#         if item_doc.uoms:
#             for uom_row in item_doc.uoms:
#                 if uom_row.uom == item_doc.stock_uom:
#                     conversion_factor = uom_row.conversion_factor
#                     break

#         rfq.append("items", {
#             "item_code": item.item,
#             "item_name": item.material,
#             "description": item.material_desc,
#             "qty": item.pick_qty,
#             "schedule_date": nowdate(),
#             "warehouse": f"Finished Goods - {company_abbr}",
#             "uom": item_doc.stock_uom,
#             "conversion_factor": conversion_factor
#         })

#     rfq.insert()
#     rfq.submit()
    
#     # Send emails to suppliers after successful submission
#     try:
#         on_rfq_submit(rfq)
#     except Exception as e:
#         frappe.log_error(f"Failed to send RFQ emails: {str(e)}")
#         # Don't fail the RFQ creation if email sending fails
#         frappe.msgprint(f"RFQ created successfully but failed to send emails: {str(e)}", 
#                        title="Email Warning", indicator="orange")
    
#     return rfq.name

@frappe.whitelist()
def create_rfq_from_pickup_request(pickup_request, suppliers, email_template, schedule_date=None):
    if not suppliers:
        frappe.throw("Please add at least one supplier.")
    
    suppliers = json.loads(suppliers)
    pickup = frappe.get_doc("Pickup Request", pickup_request)
    email_template_doc = frappe.get_doc("Email Template", email_template)
    message_for_supplier = email_template_doc.response or ""
    company_abbr = frappe.db.get_value("Company", pickup.company, "abbr")

    rfq = frappe.new_doc("Request for Quotation")
    rfq.transaction_date = nowdate()
    rfq.custom_pickup_request = pickup.name
    rfq.message_for_supplier = message_for_supplier
    rfq.custom_type = "Logistics"
    rfq.company = pickup.company 
    # rfq.billing_address = pickup.company_address
    # rfq.custom_shipment_address = pickup.company_address
    rfq.custom_no_of_pkg_units = pickup.no_of_package
    rfq.custom_shipment_type = pickup.type_of_shipments
    
    # Set schedule_date properly - ensure it's a date string
    if schedule_date:
        if isinstance(schedule_date, str):
            rfq.schedule_date = schedule_date
        else:
            rfq.schedule_date = str(schedule_date)
    else:
        rfq.schedule_date = nowdate()

    # Add suppliers with email from Supplier doctype
    for sup in suppliers:
        supplier_name = sup.get("supplier")
        supplier_doc = frappe.get_doc("Supplier", supplier_name)

        rfq.append("suppliers", {
            "supplier": supplier_name,
            "email_id": supplier_doc.email_id or ""
        })

    # Add items
    for item in pickup.purchase_order_details:
        item_doc = frappe.get_doc("Item", item.item)
        conversion_factor = 1
        if item_doc.uoms:
            for uom_row in item_doc.uoms:
                if uom_row.uom == item_doc.stock_uom:
                    conversion_factor = uom_row.conversion_factor
                    break

        rfq.append("items", {
            "item_code": item.item,
            "item_name": item.material,
            "description": item.material_desc,
            "qty": item.pick_qty,
            "schedule_date": rfq.schedule_date,  # Use the RFQ's schedule_date
            "warehouse": f"Finished Goods - {company_abbr}",
            "uom": item_doc.stock_uom,
            "conversion_factor": conversion_factor
        })

    # Validate before insert to catch any type issues
    try:
        rfq.insert()
        rfq.submit()
        
        try:
            on_rfq_submit(rfq)
        except Exception as e:
            frappe.log_error(f"Failed to send RFQ emails: {str(e)}")
            # Don't fail the RFQ creation if email sending fails
            frappe.msgprint(f"RFQ created successfully but failed to send emails: {str(e)}", 
                           title="Email Warning", indicator="orange")
        
        return rfq.name
        
    except Exception as e:
        frappe.log_error(f"RFQ Creation Error: {str(e)}")
        frappe.throw(f"Failed to create RFQ: {str(e)}")


def update_po_pick_qty_and_status(pickup_request_name):
    pickup = frappe.get_doc("Pickup Request", pickup_request_name)
    updated_purchase_orders = {}

    for detail in pickup.purchase_order_details:
        if detail.po_number:
            po = updated_purchase_orders.get(detail.po_number) or frappe.get_doc("Purchase Order", detail.po_number)

            for item in po.items:
                if (
                    item.item_code == detail.item
                    and item.qty == detail.quantity
                ):
                    # Initialize if None
                    if not item.custom_pick_qty:
                        item.custom_pick_qty = 0

                    item.custom_pick_qty += detail.pick_qty
                    break  # Assume only one match per PO

            updated_purchase_orders[po.name] = po

    # Update pickup status and pickup requests for each PO
    for po in updated_purchase_orders.values():
        all_fully_picked = True
        any_partially_picked = False

        for item in po.items:
            # Make sure null values don't break comparison
            pick_qty = item.custom_pick_qty or 0
            if pick_qty < item.qty:
                all_fully_picked = False
                if pick_qty > 0:
                    any_partially_picked = True

        if all_fully_picked:
            po.custom_pickup_status = "Fully Picked"
        elif any_partially_picked:
            po.custom_pickup_status = "Partially Picked"
        else:
            po.custom_pickup_status = "Pending"

        # Update pickup requests table - check if this pickup request is already in the table
        existing_pickup_request = None
        if hasattr(po, 'custom_pickup_request'):
            for pr in po.custom_pickup_request:
                if pr.pickup_request == pickup.name:
                    existing_pickup_request = pr
                    break
        
        # If not found, add new pickup request entry
        if not existing_pickup_request and hasattr(po, 'custom_pickup_request'):
            po.append('custom_pickup_request', {
                'pickup_request': pickup.name
            })

        po.save(ignore_permissions=True)

    frappe.db.commit()

@frappe.whitelist()
def trigger_pickup_updates(pickup_request):
    update_po_pick_qty_and_status(pickup_request)
    doc = frappe.get_doc("Pickup Request", pickup_request)
    doc.db_set("po_updated", 1)

def get_dashboard_data(data):
    # Links for Pickup Request
    data["non_standard_fieldnames"]["Request for Quotation"] = "pickup_request"
    data["non_standard_fieldnames"]["Pre Alert"] = "pickup_request"

    data["transactions"] = [
        {
            "label": _("Fulfillment"),
            "items": ["Pre Alert", "Request for Quotation"],
        }
    ]
    return data

@frappe.whitelist()
def get_dashboard_link_data(doctype, name, data=None):
    if doctype == "Pickup Request":
        return {
            "Request for Quotation": frappe.get_all(
                "Request for Quotation",
                filters={"pickup_request": name},
                fields=["name", "status", "transaction_date"],
            ),
            "Pre Alert": frappe.get_all(
                "Pre Alert",
                filters={"pickup_request": name},
                fields=["name", "status", "creation"],
            ),
        }
    return {}

@frappe.whitelist()
def should_show_update_button(pickup_request):
    pickup = frappe.get_doc("Pickup Request", pickup_request)
    po_names = list(set([row.po_number for row in pickup.purchase_order_details if row.po_number]))

    for po_name in po_names:
        po = frappe.get_doc("Purchase Order", po_name)
        for item in po.items:
            custom_pick_qty = item.custom_pick_qty or 0
            if custom_pick_qty < item.qty:
                return True  # At least one item still pending
    return False  # All fully picked




def on_rfq_submit(doc, method=None):
    """
    Send an email to each supplier on RFQ submit with a webform link pre-filled with RFQ and supplier.
    """
    base_url = get_url() 
    webform_base_url = f"{base_url}/supplier-quotation/new"

    for supplier_row in doc.suppliers:
        supplier = supplier_row.supplier
        email_id = supplier_row.email_id
        if not email_id:
            continue
        # Build webform link
        webform_link = f"{webform_base_url}?request_for_quotation={doc.name}&supplier={supplier}"
        subject = f"Request for Quotation {doc.name} - Submit Your Quotation"
        message = f"""
        Dear Supplier,<br><br>
        You are invited to submit your quotation for RFQ <b>{doc.name}</b>.<br>
        Please use the following link to submit your quotation:<br><br>
        <a href='{webform_link}' target='_blank'>Submit Quotation (Web Form)</a><br><br>
        Thank you.<br>
        """
        frappe.sendmail(
            recipients=[email_id],
            subject=subject,
            message=message,
            reference_doctype=doc.doctype,
            reference_name=doc.name,
            now=True,
        )
