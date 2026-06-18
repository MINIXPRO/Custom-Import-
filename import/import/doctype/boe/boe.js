// Copyright (c) 2025, Pragati Dike and contributors
// For license information, please see license.txt

frappe.ui.form.on('BOE', {
    on_submit: function(frm) {
        frappe.call({
            method: 'import.import.doctype.boe.boe.sync_boe_to_payment_requisition',
            args: { boe_name: frm.doc.name },
            freeze: true,
            freeze_message: __('Updating Payment Requisition...'),
            callback: function(r) {
                if (!r.exc) {
                    frappe.show_alert({
                        message: __('Payment Requisition updated with BOE details'),
                        indicator: 'green'
                    }, 5);
                    setTimeout(function() {
                        if (frm.doc.payment_requisition) {
                            frappe.set_route('Form', 'Payment Requisition', frm.doc.payment_requisition);
                        }
                    }, 1000);
                }
            }
        });
    }
});