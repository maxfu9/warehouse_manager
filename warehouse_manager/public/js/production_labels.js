function addProductionBatchButton(frm) {
    if (frm.is_new() || !frappe.model.can_read('Batch QR Maker')) return;
    if (frm.doctype === 'Stock Entry' && frm.doc.warehouse_qr_batch) {
        frm.add_custom_button(__('Carton Label Batch'), () => {
            frappe.set_route('Form', 'Batch QR Maker', frm.doc.warehouse_qr_batch);
        }, __('Warehouse'));
    } else if (frm.doctype === 'Work Order') {
        frm.add_custom_button(__('Carton Label Batches'), () => {
            frappe.route_options = {work_order: frm.doc.name};
            frappe.set_route('List', 'Batch QR Maker');
        }, __('Warehouse'));
    }
}

frappe.ui.form.on('Work Order', {refresh: addProductionBatchButton});
frappe.ui.form.on('Stock Entry', {refresh: addProductionBatchButton});
