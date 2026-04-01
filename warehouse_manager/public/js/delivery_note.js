frappe.ui.form.on("Delivery Note", {
    refresh(frm) {
        if (frm.is_new() || !frm.doc.name || frm.doc.docstatus === 2) {
            return;
        }

        addDispatchedCartonsButton(frm);
    }
});

function addDispatchedCartonsButton(frm) {
    frappe.call({
        method: "warehouse_manager.api.get_delivery_note_cartons",
        args: {
            delivery_note: frm.doc.name
        },
        callback: (response) => {
            const data = response.message || {};
            const count = cint(data.count || 0);

            if (!count) {
                return;
            }

            frm.dashboard.set_headline_alert(
                __("Dispatched cartons linked: {0}", [count]),
                "blue"
            );

            frm.add_custom_button(__("View Dispatched Cartons ({0})", [count]), () => {
                showDispatchedCartonsDialog(frm, data.cartons || []);
            }, __("Warehouse"));
        }
    });
}

function showDispatchedCartonsDialog(frm, cartons) {
    const rows = (cartons || []).map((row) => {
        const cartonLabel = frappe.utils.escape_html(row.carton_no || "");
        const itemLabel = frappe.utils.escape_html(row.item_name || row.item || "");
        const batchLabel = frappe.utils.escape_html(row.batch || "-");
        const qtyLabel = frappe.utils.escape_html(formatQty(row.qty));
        const link = row.carton_qr_name
            ? `<a href="/app/carton-qr/${encodeURIComponent(row.carton_qr_name)}" style="font-weight: 600;">${cartonLabel}</a>`
            : `<span>${cartonLabel}</span>`;

        return `
            <tr>
                <td style="padding: 8px 10px; border-bottom: 1px solid #e5e7eb;">${link}</td>
                <td style="padding: 8px 10px; border-bottom: 1px solid #e5e7eb;">${itemLabel}</td>
                <td style="padding: 8px 10px; border-bottom: 1px solid #e5e7eb;">${batchLabel}</td>
                <td style="padding: 8px 10px; border-bottom: 1px solid #e5e7eb; text-align: right;">${qtyLabel}</td>
            </tr>
        `;
    }).join("");

    const dialog = new frappe.ui.Dialog({
        title: __("Dispatched Cartons"),
        size: "large",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "cartons_html"
            }
        ],
        primary_action_label: __("Open Carton QR List"),
        primary_action: () => {
            const cartonNames = (cartons || [])
                .map((row) => row.carton_qr_name)
                .filter(Boolean);

            if (!cartonNames.length) {
                frappe.msgprint(__("No Carton QR records were found for this Delivery Note."));
                return;
            }

            frappe.set_route("List", "Carton QR", {
                name: ["in", cartonNames]
            });
            dialog.hide();
        }
    });

    const html = `
        <div style="margin-bottom: 12px; color: #6b7280;">
            ${__("These cartons were dispatched against Delivery Note {0}.", [frappe.utils.escape_html(frm.doc.name)])}
        </div>
        <div style="max-height: 420px; overflow: auto; border: 1px solid #e5e7eb; border-radius: 12px;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead style="position: sticky; top: 0; background: #f9fafb;">
                    <tr>
                        <th style="padding: 10px; text-align: left; border-bottom: 1px solid #e5e7eb;">${__("Carton QR")}</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 1px solid #e5e7eb;">${__("Item")}</th>
                        <th style="padding: 10px; text-align: left; border-bottom: 1px solid #e5e7eb;">${__("Batch")}</th>
                        <th style="padding: 10px; text-align: right; border-bottom: 1px solid #e5e7eb;">${__("Qty")}</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        </div>
    `;

    dialog.fields_dict.cartons_html.$wrapper.html(html);
    dialog.show();
}

function formatQty(value) {
    const numericValue = flt(value);
    return Number.isInteger(numericValue) ? `${numericValue}` : format_number(numericValue);
}
