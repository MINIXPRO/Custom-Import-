// Copyright (c) 2025, Pragati Dike and contributors
// For license information, please see license.txt

frappe.ui.form.on('Pickup Request', {
refresh: function(frm) {
if (frm.doc.docstatus === 1) {
        frm.add_custom_button(__('Purchase Receipt'), function () {
            if (!frm.doc.fop && (!frm.doc.po_no || frm.doc.po_no.length === 0)) {
                frappe.msgprint({
                    title: __('No Purchase Orders'),
                    indicator: 'red',
                    message: __('Please add at least one Purchase Order before creating a Purchase Receipt.')
                });
                return;
            }

        frappe.call({
            method: 'import.import.doctype.pickup_request.pickup_request.make_purchase_receipt_from_pickup',
            args: { pickup_request: frm.doc.name },
            freeze: true,
            freeze_message: __('Creating Purchase Receipt(s)...'),
            callback: function (r) {
                if (!r.message || r.message.length === 0) {
                    frappe.msgprint({
                        title: __('No Receipts Created'),
                        indicator: 'orange',
                        message: __('No items with valid pick quantities were found.')
                    });
                    return;
                }

                let pr_list = r.message;

                if (pr_list.length === 1) {
                    frappe.set_route('Form', 'Purchase Receipt', pr_list[0].name);
                } else {
                    let links = pr_list.map(function (pr) {
                        let url = `/app/purchase-receipt/${pr.name}`;
                        return `<a href="${url}" target="_blank">${pr.name} (${pr.supplier})</a>`;
                    });

                    frappe.msgprint({
                        title: __('Purchase Receipts Created'),
                        indicator: 'green',
                        message: __(
                            'The following Purchase Receipts were created as drafts, one per Purchase Order:<br><br>' +
                            links.join('<br>')
                        )
                    });
                }
            }
        });
    }, __('Create'));
}

        // ── Payment Requisition button ──
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Payment Requisition'), function () {
                frappe.model.with_doctype('Payment Requisition', function() {
                    let payment_req = frappe.model.get_new_doc('Payment Requisition');
                    payment_req.company = frm.doc.company;
                    payment_req.mode_of_shipment = frm.doc.mode_of_shipment;
                    payment_req.origin = frm.doc.country_origin;
                    payment_req.cargo_type = frm.doc.type_of_cargo;

                    let pickup_row = frappe.model.add_child(payment_req, 'Pickup Request CT', 'pickup_request');
                    pickup_row.pickup_request = frm.doc.name;

                    if (frm.doc.po_no && frm.doc.po_no.length > 0) {
                        frm.doc.po_no.forEach(function(po) {
                            let po_row = frappe.model.add_child(payment_req, 'PO CT', 'po_wono');
                            po_row.purchase_order = po.purchase_order;
                        });
                    }

                    if (frm.doc.name_of_supplier && frm.doc.name_of_supplier.length > 0) {
                        frm.doc.name_of_supplier.forEach(function(supplier) {
                            let supplier_row = frappe.model.add_child(payment_req, 'Supplier CT', 'supplier_name');
                            supplier_row.supplier = supplier.supplier;
                        });
                    }

                    if (frm.doc.purchase_order_details && frm.doc.purchase_order_details.length > 0) {
                        frm.doc.purchase_order_details.forEach(function(item) {
                            let item_row = frappe.model.add_child(payment_req, 'Payment Requisition CT', 'items');
                            item_row.item = item.item;
                            item_row.description = item.material;
                            item_row.pickup_request = frm.doc.name;
                        });
                    }

                    frappe.model.sync(payment_req);
                    frappe.set_route('Form', 'Payment Requisition', payment_req.name);
                });
            }, __('Create'));
        }

        // ── Create RFQ button ──
        if (frm.doc.docstatus == 1) {
            frm.add_custom_button('Create RFQ', () => {
                show_supplier_popup(frm);
            });
        }

        // ── Update PO Pickup Qty button ──
        if (frm.doc.docstatus === 1 && !frm.doc.custom_po_updated) {
            frappe.call({
                method: "import.import.doctype.pickup_request.pickup_request.should_show_update_button",
                args: { pickup_request: frm.doc.name },
                callback: function (r) {
                    if (r.message === true) {
                        frm.add_custom_button("Update PO Pickup Qty", function () {
                            frappe.call({
                                method: "import.import.doctype.pickup_request.pickup_request.trigger_pickup_updates",
                                args: { pickup_request: frm.doc.name },
                                callback: function () {
                                    frappe.msgprint("Purchase Orders updated.");
                                    frappe.call({
                                        method: "frappe.client.set_value",
                                        args: {
                                            doctype: "Pickup Request",
                                            name: frm.doc.name,
                                            fieldname: "custom_po_updated",
                                            value: 1
                                        },
                                        callback: function() {
                                            frm.reload_doc();
                                        }
                                    });
                                }
                            });
                        });
                    }
                }
            });
        }

        // ── Field queries ──
        frm.set_query('supplier_address', function (doc) {
            return {
                query: 'frappe.contacts.doctype.address.address.address_query',
                filters: { link_doctype: 'Supplier', link_name: doc.name_of_supplier }
            };
        });

        frm.set_query('billing_address', function (doc) {
            return {
                query: 'frappe.contacts.doctype.address.address.address_query',
                filters: { link_doctype: 'Company', link_name: doc.company }
            };
        });

        frm.set_query('pickup_address_display', function (doc) {
            return {
                query: 'frappe.contacts.doctype.address.address.address_query',
                filters: { link_doctype: 'Supplier', link_name: doc.name_of_supplier }
            };
        });

        frm.set_query('name_of_supplier', function () {
            return { filters: { 'supplier_group': ['!=', "CHA"] } };
        });

        // ── Get Items button ──
        frm.add_custom_button("Purchase Order", function () {
            let d = new frappe.ui.form.MultiSelectDialog({
                doctype: "Purchase Order",
                target: this.cur_frm,
                setters: {
                    custom_port_of_destination_pod: frm.doc.custom_port_of_destination_pod,
                    custom_port_of_loading_pol: frm.doc.custom_port_of_loading_pol
                },
                add_filters_group: 1,
                date_field: 'transaction_date',
                columns: ['name', 'transaction_date', 'supplier', 'custom_purchase_sub_type'],
                get_query() {
                    return {
                        filters: {
                            docstatus: ['!=', 2],
                            custom_purchase_sub_type: 'Import',
                            custom_pickup_status: ['!=', 'Fully Picked']
                        }
                    };
                },
                action: async function (selections) {
                    d.dialog.hide();

                    let suppliers_set = new Set((frm.doc.name_of_supplier || []).map(row => row.supplier));
                    let existing_po_set = new Set((frm.doc.po_no || []).map(row => row.purchase_order));
                    let existing_po_list_set = new Set((frm.doc.purchase_order_list || []).map(row => row.po_number));

                    let currencies_set = new Set();
                    let po_details_map = new Map();

                    // First pass: collect PO details
                    for (const po_name of selections) {
                        await frappe.call({
                            method: "import.import.doctype.pickup_request.pickup_request.get_po_all_details",
                            args: { po_name },
                            callback: function (r) {
                                if (r.message) {
                                    po_details_map.set(po_name, r.message);
                                    currencies_set.add(r.message.currency);
                                }
                            }
                        });
                    }

                    let has_multiple_currencies = currencies_set.size > 1;

                    if (has_multiple_currencies) {
                        frm.set_df_property('total', 'hidden', 1);
                        frm.set_df_property('grand_total', 'hidden', 1);
                        if (frm.fields_dict.base_total) frm.set_df_property('base_total', 'hidden', 0);
                        if (frm.fields_dict.base_grand_total) frm.set_df_property('base_grand_total', 'hidden', 0);
                    } else {
                        frm.set_df_property('total', 'hidden', 0);
                        frm.set_df_property('grand_total', 'hidden', 0);
                        if (frm.fields_dict.base_total) frm.set_df_property('base_total', 'hidden', 0);
                        if (frm.fields_dict.base_grand_total) frm.set_df_property('base_grand_total', 'hidden', 0);
                    }

                    // Second pass: process POs
                    for (const po_name of selections) {
                        let r_message = po_details_map.get(po_name);
                        if (!r_message) continue;

                        let po_id = r_message.name;
                        let supplier_id = r_message.supplier;

                        if (frm.doc.port_of_loading_pol && frm.doc.port_of_loading_pol !== r_message.custom_port_of_loading_pol) {
                            frappe.msgprint({
                                title: "Port of Loading Mismatch",
                                message: `Purchase Order ${po_id} has a different Port of Loading (${r_message.custom_port_of_loading_pol}) than the Pickup Request (${frm.doc.port_of_loading_pol}).`,
                                indicator: "red"
                            });
                            continue;
                        }

                        if (frm.doc.port_of_destination_pod && frm.doc.port_of_destination_pod !== r_message.custom_port_of_destination_pod) {
                            frappe.msgprint({
                                title: "Port of Destination Mismatch",
                                message: `Purchase Order ${po_id} has a different Port of Destination (${r_message.custom_port_of_destination_pod}) than the Pickup Request (${frm.doc.port_of_destination_pod}).`,
                                indicator: "red"
                            });
                            continue;
                        }

                        if (!suppliers_set.has(supplier_id)) {
                            suppliers_set.add(supplier_id);
                            let supplier_row = frm.add_child("name_of_supplier");
                            supplier_row.supplier = supplier_id;
                        }

                        if (!existing_po_set.has(po_id)) {
                            existing_po_set.add(po_id);
                            let po_row = frm.add_child("po_no");
                            po_row.purchase_order = po_id;
                        }

                        if (!existing_po_list_set.has(po_id)) {
                            existing_po_list_set.add(po_id);
                            let row = frm.add_child("purchase_order_list");
                            row.po_number = po_id;
                            row.document_date = r_message.transaction_date;
                            row.po_type = r_message.custom_purchase_type;
                            row.vendor = supplier_id;
                            row.vendor_name = r_message.supplier_name;
                            row.currency = r_message.currency;
                            row.company = r_message.company;
                            row.exchange_rate = r_message.conversion_rate;
                        }

                        // ✅ Add PO items with correct calculated amounts
                        r_message.items.forEach(item => {
                            let remaining_qty = item.qty - (item.custom_pick_qty || 0);
                            if (remaining_qty <= 0) return;

                            let amount = remaining_qty * (item.rate || 0);
                            let amount_in_inr = amount * (r_message.conversion_rate || 1);

                            let item_row = frm.add_child("purchase_order_details");
                            item_row.item = item.item_code;
                            item_row.material = item.item_name;
                            item_row.quantity = item.qty;
                            item_row.material_desc = item.description;
                            item_row.pick_qty = remaining_qty;
                            item_row.po_number = item.parent;
                            item_row.currency = r_message.currency;
                            item_row.currency_rate = r_message.conversion_rate;
                            item_row.rate = item.rate;
                            item_row.amount = amount;
                            item_row.amount_in_inr = amount_in_inr;
                            item_row.custom_oligo_bank_ref = item.custom_oligo_bank_ref;
                        });

                        if (!frm.doc.port_of_loading_pol) frm.set_value("port_of_loading_pol", r_message.custom_port_of_loading_pol);
                        if (!frm.doc.port_of_destination_pod) frm.set_value("port_of_destination_pod", r_message.custom_port_of_destination_pod);
                        if (frm.fields_dict.incoterm) frm.set_value("incoterm", r_message.incoterm);
                        if (frm.fields_dict.taxes_and_charges) frm.set_value("taxes_and_charges", r_message.taxes_and_charges);
                        if (frm.fields_dict.tax_category) frm.set_value("tax_category", r_message.tax_category);
                        if (frm.fields_dict.company_address && r_message.billing_address) frm.set_value("company_address", r_message.billing_address);

                        frm.refresh_field("purchase_order_list");
                        frm.refresh_field("purchase_order_details");
                        frm.refresh_field("name_of_supplier");
                        frm.refresh_field("po_no");
                    }

                    frm.refresh_fields();
                    setTimeout(() => { frm.save(); }, 500);
                }
            });
            d.dialog.show();
        }, __("Get Items"));

        // ── Toggle totals visibility ──
        frm.enable_save();
        toggle_total_field(frm);
    },

    // ── Field events ──

    supplier_address: function (frm) {
        erpnext.utils.get_address_display(frm, "supplier_address", "supplier_address_display", false);
    },

    billing_address: function (frm) {
        erpnext.utils.get_address_display(frm, "billing_address", "billing_address_display", false);
    },

    supplier_pickup_address: function (frm) {
        erpnext.utils.get_address_display(frm, "supplier_pickup_address", "pickup_address_display", false);
    },

    taxes_and_charges: function(frm) {
        if (frm.doc.taxes_and_charges) {
            frappe.call({
                method: "import.import.doctype.pickup_request.pickup_request.apply_tax_template_to_pickup_request",
                args: {
                    pickup_request_name: frm.doc.name,
                    template_name: frm.doc.taxes_and_charges
                },
                callback: function(r) {
                    if (r.message) {
                        frm.clear_table("purchase_taxes_and_charges");
                        if (r.message.purchase_taxes_and_charges) {
                            r.message.purchase_taxes_and_charges.forEach(function(tax) {
                                let row = frm.add_child("purchase_taxes_and_charges");
                                Object.assign(row, tax);
                            });
                        }
                        frm.set_value("total_taxes_and_charges", r.message.total_taxes_and_charges);
                        frm.set_value("base_grand_total", r.message.base_grand_total);
                        frm.set_value("grand_total", r.message.grand_total);
                        frm.refresh_fields();
                    }
                }
            });
        } else {
            frm.clear_table("purchase_taxes_and_charges");
            frm.set_value("total_taxes_and_charges", 0);
            frm.set_value("taxes_and_charges_added", 0);
            frm.set_value("base_taxes_and_charges_added", 0);
            clear_tax_calculations(frm);
            calculate_grand_totals(frm);
            frm.refresh_fields();
        }
    },

    tax_category: function(frm) {
        if (frm.doc.tax_category) {
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Purchase Taxes and Charges Template",
                    filters: { tax_category: frm.doc.tax_category, disabled: 0 },
                    fields: ["name"],
                    limit: 1
                },
                callback: function(r) {
                    if (r.message && r.message.length > 0) {
                        frm.set_value('taxes_and_charges', r.message[0].name);
                    }
                }
            });
        }
    },

    currency: function(frm) {
        if (frm.doc.currency) {
            frappe.call({
                method: "erpnext.setup.utils.get_exchange_rate",
                args: {
                    from_currency: frm.doc.currency,
                    to_currency: "INR",
                    transaction_date: frm.doc.po_date || frappe.datetime.get_today()
                },
                callback: function(r) {
                    if (r.message) frm.set_value('conversion_rate', r.message);
                }
            });
        }
    },

    conversion_rate: function(frm) {
        update_currency_rates(frm);
    },

    custom_get_po_items: function (frm) {
        frappe.call({
            method: "get_items",
            doc: frm.doc,
            args: { po: frm.doc.purchase_order_list },
            callback: function (r) {
                frm.refresh();
                calculate_taxes_and_totals(frm);
            }
        });
    },

    before_save: function (frm) {
        calculate_taxes_and_totals(frm);
    },


    validate: function (frm) {
        remove_zero_pick_qty_rows(frm);

        // Skip PO qty validation entirely when FOP is checked
        if (frm.doc.fop) return;

        let validation_failed = false;
        let promises = [];

        $.each(frm.doc.purchase_order_details || [], function (i, d) {
            if (!d.po_number) return;

        promises.push(
            frappe.call({
                method: "import.import.doctype.pickup_request.pickup_request.validate_po_order_qty_to_pickup_qty",
                args: { po_no: d.po_number, item_code: d.item }
            }).then(r => {
                    if (r.message) {
                        let qty = r.message[0]['qty'];
                        let received_qty = r.message[0]['received_qty'];
                        let check_qty = qty - received_qty;
                        if (d.pick_qty > check_qty) {
                            validation_failed = true;
                            frappe.msgprint({
                                title: __("Invalid Pickup Quantity"),
                                indicator: "red",
                                message: __(`You cannot pick up more than the available PO quantity for item ${d.item}. Please check the PO quantity.`)
                            });
                        }
                    }
                })
            );
        });

        return Promise.all(promises).then(() => {
            if (validation_failed) frappe.validated = false;
        });
    },

    mode_of_shipment: function (frm) {
        if (frm.doc.mode_of_shipment == "Ocean liner") frm.set_value("type_wise_value", 6000);
        else if (frm.doc.mode_of_shipment == "MOS1-AIR") frm.set_value("type_wise_value", 5000);
    },

    gross_weight: function(frm) {
        frm.set_value('gross__weight', frm.doc.gross_weight ? frm.doc.gross_weight * 2.20462 : 0);
    },

    gross__weight: function(frm) {
        frm.set_value('gross_weight', frm.doc.gross__weight ? frm.doc.gross__weight / 2.20462 : 0);
    },

    total_quantity: function(frm) {
        set_po_totals_if_condition(frm);
    },

    total_picked_quantity: function(frm) {
        set_po_totals_if_condition(frm);
    },

    po_no_add: function(frm) {
        toggle_total_field(frm);
        fetch_rounding_if_single_po(frm);
        set_po_totals_if_condition(frm);
    },

    po_no_remove: function(frm) {
        toggle_total_field(frm);
        fetch_rounding_if_single_po(frm);
        set_po_totals_if_condition(frm);
    },

    get_pos: function (frm) {
        let purchase_order = [];
        $.each(frm.doc.purchase_order_details || [], function (i, d) {
            if (!purchase_order.includes(d.po_number)) purchase_order.push(d.po_number);
        });

        purchase_order.forEach(function (obj) {
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Purchase Order",
                    filters: { name: obj },
                    fields: ["supplier", "currency", "conversion_rate", "transaction_date", "custom_purchase_type", "company"]
                },
                callback: function (r) {
                    let data = r.message;
                    let row = frm.add_child("purchase_order_list");
                    row.po_number = obj;
                    row.document_date = data[0]['transaction_date'];
                    row.vendor = data[0]['supplier'];
                    row.vendor_name = data[0]['supplier'];
                    row.po_type = data[0]['custom_purchase_type'];
                    row.currency = data[0]['currency'];
                    row.company = data[0]['company'];
                    row.exchange_rate = data[0]['conversion_rate'];
                    frm.refresh_field("purchase_order_list");
                }
            });
        });

        $.each(frm.doc.purchase_order_details || [], function (i, d) {
            frappe.call({
                method: "import.import.doctype.pickup_request.pickup_request.get_items_details",
                args: { parent: d.po_number, item_name: d.item },
                callback: function (r) {
                    let data = r.message;
                    const parent_date = data[0];
                    const child_date = data[1];
                    d.currency = parent_date[0]['currency'];
                    d.currency_rate = parent_date[0]['conversion_rate'];
                    d.rate = child_date[0]['rate'];
                    d.amount = d.pick_qty * child_date[0]['rate'];
                    d.amount_in_inr = d.amount * parent_date[0]['conversion_rate'];
                    frm.refresh_field("purchase_order_details");
                    calculate_taxes_and_totals(frm);
                }
            });
        });
    }
});

// ── Child table events ──

frappe.ui.form.on('Purchase Order Details', {
    pick_qty: function(frm, cdt, cdn) { calculate_taxes_and_totals(frm); },
    rate: function(frm, cdt, cdn) { calculate_taxes_and_totals(frm); },
    currency_rate: function(frm, cdt, cdn) { calculate_taxes_and_totals(frm); },
    purchase_order_details_remove: function(frm) { calculate_taxes_and_totals(frm); }
});

frappe.ui.form.on('Purchase Taxes and Charges', {
    rate: function(frm, cdt, cdn) { calculate_taxes_and_totals(frm); },
    tax_amount: function(frm, cdt, cdn) { calculate_taxes_and_totals(frm); },
    purchase_taxes_and_charges_remove: function(frm) { calculate_taxes_and_totals(frm); }
});

// ── Calculation functions ──

function calculate_taxes_and_totals(frm) {
    if (!frm.doc.purchase_order_details || frm.doc.purchase_order_details.length === 0) return;
    calculate_base_totals(frm);
    if (frm.doc.taxes_and_charges) {
        calculate_taxes(frm);
    } else {
        clear_tax_calculations(frm);
        calculate_grand_totals(frm);
    }
}

function calculate_base_totals(frm) {
    let total_qty = 0;
    let total_picked_qty = 0;
    let base_total = 0;
    let total = 0;

    frm.doc.purchase_order_details.forEach(item => {
        if (item.quantity) total_qty += item.quantity;
        if (item.pick_qty) total_picked_qty += item.pick_qty;

        let pick_qty = item.pick_qty || 0;
        let rate = item.rate || 0;
        let currency_rate = item.currency_rate || 1;

        let amount = pick_qty * rate;
        let base_amount = amount * currency_rate;

        frappe.model.set_value(item.doctype, item.name, 'amount', amount);
        frappe.model.set_value(item.doctype, item.name, 'amount_in_inr', base_amount);

        total += amount;
        base_total += base_amount;
    });

    frm.set_value('total_quantity', total_qty);
    frm.set_value('total_picked_quantity', total_picked_qty);
    frm.set_value('total', total);
    frm.set_value('base_total', base_total);
}

function calculate_taxes(frm) {
    if (!frm.doc.taxes_and_charges) return;

    frappe.call({
        method: "erpnext.controllers.accounts_controller.get_taxes_and_charges",
        args: {
            "master_doctype": "Purchase Taxes and Charges Template",
            "master_name": frm.doc.taxes_and_charges
        },
        callback: function(r) {
            if (r.message) {
                frm.clear_table("purchase_taxes_and_charges");

                let base_total = frm.doc.base_total || 0;
                let total = frm.doc.total || 0;
                let cumulative_base_total = base_total;
                let cumulative_total = total;

                r.message.forEach(tax => {
                    let tax_row = frm.add_child("purchase_taxes_and_charges");
                    tax_row.charge_type = tax.charge_type;
                    tax_row.account_head = tax.account_head;
                    tax_row.description = tax.description;
                    tax_row.rate = tax.rate;
                    tax_row.cost_center = tax.cost_center;
                    tax_row.add_deduct_tax = tax.add_deduct_tax;

                    let tax_amount = 0;
                    let base_tax_amount = 0;

                    if (tax.charge_type === "On Net Total") {
                        tax_amount = total * (tax.rate / 100);
                        base_tax_amount = base_total * (tax.rate / 100);
                    } else if (tax.charge_type === "On Previous Row Amount") {
                        let prev_row = frm.doc.purchase_taxes_and_charges[frm.doc.purchase_taxes_and_charges.length - 2];
                        if (prev_row) {
                            tax_amount = (prev_row.tax_amount || 0) * (tax.rate / 100);
                            base_tax_amount = (prev_row.base_tax_amount || 0) * (tax.rate / 100);
                        }
                    } else if (tax.charge_type === "On Previous Row Total") {
                        tax_amount = cumulative_total * (tax.rate / 100);
                        base_tax_amount = cumulative_base_total * (tax.rate / 100);
                    } else if (tax.charge_type === "Actual") {
                        tax_amount = tax.tax_amount || 0;
                        base_tax_amount = tax_amount * (frm.doc.conversion_rate || 1);
                    }

                    if (tax.add_deduct_tax === "Deduct") {
                        tax_amount = -tax_amount;
                        base_tax_amount = -base_tax_amount;
                    }

                    tax_row.tax_amount = tax_amount;
                    tax_row.base_tax_amount = base_tax_amount;

                    cumulative_total += tax_amount;
                    cumulative_base_total += base_tax_amount;

                    tax_row.total = cumulative_total;
                    tax_row.base_total = cumulative_base_total;
                });

                frm.refresh_field("purchase_taxes_and_charges");
                calculate_tax_totals(frm);
            }
        }
    });
}

function calculate_tax_totals(frm) {
    let taxes_and_charges_added = 0;
    let base_taxes_and_charges_added = 0;

    if (frm.doc.purchase_taxes_and_charges) {
        frm.doc.purchase_taxes_and_charges.forEach(tax => {
            taxes_and_charges_added += (tax.tax_amount || 0);
            base_taxes_and_charges_added += (tax.base_tax_amount || 0);
        });
    }

    frm.set_value('taxes_and_charges_added', taxes_and_charges_added);
    frm.set_value('base_taxes_and_charges_added', base_taxes_and_charges_added);
    calculate_grand_totals(frm);
}

function calculate_grand_totals(frm) {
    let total = frm.doc.total || 0;
    let base_taxes = frm.doc.base_taxes_and_charges_added || 0;
    let exact = (frm.doc.base_total || 0) + base_taxes;
    frm.doc.base_grand_total = exact;
    frm.refresh_field('base_grand_total');
    frm.set_value('grand_total', total + (frm.doc.taxes_and_charges_added || 0));
}

function clear_tax_calculations(frm) {
    frm.clear_table("purchase_taxes_and_charges");
    frm.set_value('taxes_and_charges_added', 0);
    frm.set_value('base_taxes_and_charges_added', 0);
    frm.refresh_field("purchase_taxes_and_charges");
}

function update_currency_rates(frm) {
    if (!frm.doc.purchase_order_details) return;
    let promises = [];
    frm.doc.purchase_order_details.forEach(item => {
        if (item.currency && item.currency !== "INR") {
            promises.push(
                frappe.call({
                    method: "erpnext.setup.utils.get_exchange_rate",
                    args: {
                        from_currency: item.currency,
                        to_currency: "INR",
                        transaction_date: frm.doc.po_date || frappe.datetime.get_today()
                    },
                    callback: function(r) {
                        if (r.message) frappe.model.set_value(item.doctype, item.name, "currency_rate", r.message);
                    }
                })
            );
        }
    });
    Promise.all(promises).then(() => { calculate_taxes_and_totals(frm); });
}

function toggle_total_field(frm) {
    const table = frm.doc.po_no || [];
    let multi = table.length >= 2;
    frm.toggle_display("total", !multi);
    frm.toggle_display("taxes_and_charges_added", !multi);
    frm.toggle_display("grand_total", !multi);
    frm.toggle_display("rounding_adjustment", !multi);
}

function fetch_rounding_if_single_po(frm) {
    const po_table = frm.doc.po_no || [];
    if (po_table.length === 1) {
        frappe.db.get_value('Purchase Order', po_table[0].purchase_order, ['rounding_adjustment', 'base_rounding_adjustment'])
            .then(r => {
                if (r && r.message) {
                    frm.set_value("rounding_adjustment", r.message.rounding_adjustment);
                    frm.set_value("base_rounding_adjustment", r.message.base_rounding_adjustment);
                }
            });
    } else {
        frm.set_value("rounding_adjustment", null);
        frm.set_value("base_rounding_adjustment", null);
    }
}

function set_po_totals_if_condition(frm) {
    const po_rows = frm.doc.po_no || [];
    const total_qty = frm.doc.total_quantity;
    const picked_qty = frm.doc.total_picked_quantity;

    if (po_rows.length === 1 && total_qty && picked_qty && total_qty === picked_qty) {
        frappe.db.get_value('Purchase Order', po_rows[0].purchase_order, ['rounded_total', 'base_rounded_total', 'base_total_taxes_and_charges'])
            .then(r => {
                if (r && r.message) {
                    frm.set_value('total', r.message.rounded_total);
                    if (!frm.doc.taxes_and_charges && (!frm.doc.purchase_taxes_and_charges || frm.doc.purchase_taxes_and_charges.length === 0)) {
                        frm.set_value('base_grand_total', r.message.base_rounded_total);
                    } else {
                        calculate_taxes_and_totals(frm);
                    }
                }
            });
    }
}

function remove_zero_pick_qty_rows(frm) {
    let keep_rows = (frm.doc.purchase_order_details || []).filter(r => Number(r.pick_qty) > 0);
    frm.clear_table("purchase_order_details");
    keep_rows.forEach(r => {
        let child = frm.add_child("purchase_order_details");
        Object.assign(child, r);
    });
    frm.refresh_field("purchase_order_details");
}

// ── RFQ helpers ──

function show_supplier_popup(frm) {
    const d = new frappe.ui.Dialog({
        title: 'Create RFQ - Add Suppliers',

        fields: [
    {
        label: 'Suppliers',
        fieldname: 'supplier_table',
        fieldtype: 'Table',
        reqd: 1,
        options: 'Supplier Child Table',
        fields: [
            {
                fieldname: 'supplier',
                fieldtype: 'Link',
                options: 'Supplier',
                label: 'Supplier',
                reqd: 1,
                in_list_view: 1
            },
            {
                fieldname: 'required_by',
                fieldtype: 'Date',
                label: 'Required By',
                reqd: 1,
                in_list_view: 1
            }
        ]
    },

    {
        fieldname: "warehouse",
        label: "Warehouse",
        fieldtype: "Link",
        options: "Warehouse",
        reqd: frm.doc.fop ? 1 : 0,
        hidden: !frm.doc.fop
    },

    {
        fieldname: 'email_template',
        fieldtype: 'Link',
        options: 'Email Template',
        label: 'Email Template',
        reqd: 1
    }
],
        primary_action_label: 'Submit',
        primary_action: function(values) {
            if (!values.supplier_table || values.supplier_table.length === 0) {
                frappe.msgprint('Please add at least one supplier');
                return;
            }
            const schedule_date = values.supplier_table[0].required_by;
            d.disable_primary_action();

            validate_supplier_emails(values.supplier_table, function(validation_result) {
                if (!validation_result.valid) {
                    d.enable_primary_action();
                    frappe.msgprint({
                        title: 'Missing Email Addresses',
                        indicator: 'red',
                        message: `The following suppliers don't have email addresses:<br><br><strong>${validation_result.missing_emails.join('<br>')}</strong><br><br>Please add email addresses to these suppliers before creating the RFQ.`
                    });
                    return;
                }

                frappe.call({
                    method: 'import.import.doctype.pickup_request.pickup_request.create_rfq_from_pickup_request',
                    args: {
                        pickup_request: frm.doc.name,
                        suppliers: values.supplier_table,
                        email_template: values.email_template,
                        schedule_date: schedule_date,
                        warehouse: values.warehouse

                    },
                    callback: function(r) {
                        d.enable_primary_action();
                        if (r && !r.exc && r.message) {
                            frappe.msgprint({
                                title: 'Success',
                                indicator: 'green',
                                message: `RFQ <a href="/app/request-for-quotation/${r.message}" target="_blank">${r.message}</a> created successfully`
                            });
                            d.hide();
                            frm.reload_doc();
                        } else {
                            let error_message = 'Failed to create RFQ.';
                            if (r.exc) {
                                if (typeof r.exc === 'string' && r.exc.includes('ValidationError')) error_message = 'Validation error occurred.';
                                else if (typeof r.exc === 'string' && r.exc.includes('PermissionError')) error_message = 'Permission denied.';
                            }
                            frappe.msgprint({ title: 'Error', indicator: 'red', message: error_message + ' Please check the server logs.' });
                        }
                    },
                    error: function() {
                        d.enable_primary_action();
                        frappe.msgprint({ title: 'Error', indicator: 'red', message: 'Network error occurred. Please try again.' });
                    }
                });
            });
        }
    });
    d.show();
}

function validate_supplier_emails(suppliers, callback) {
    const supplier_names = suppliers.map(s => s.supplier);
    frappe.call({
        method: 'frappe.client.get_list',
        args: { doctype: 'Supplier', filters: [['name', 'in', supplier_names]], fields: ['name', 'email_id'] },
        callback: function(r) {
            if (r.message) {
                const missing_emails = r.message.filter(s => !s.email_id || s.email_id.trim() === '').map(s => s.name);
                callback({ valid: missing_emails.length === 0, missing_emails });
            } else {
                callback({ valid: false, missing_emails: supplier_names });
            }
        },
        error: function() { callback({ valid: false, missing_emails: supplier_names }); }
    });
}

// Legacy
function calculation_of_amount_and_inr_amount(frm) {
    calculate_taxes_and_totals(frm);
}