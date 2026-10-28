const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../warehouse_management_hub/doctype/batch_qr_maker/batch_qr_maker.js'), 'utf8');
let refresh, intro, footer;
const chain = {addClass() { return this; }, css() { return this; }};
const context = vm.createContext({
    frappe: {ui: {form: {on(name, handlers) { if (name === 'Batch QR Maker') refresh = handlers.refresh; }}}},
    cint: Number, format_number: String,
    __: (message, values) => message.replace(/\{(\d+)\}/g, (_, i) => values[i]),
    $: markup => ({markup})
});
vm.runInContext(source, context);
refresh({
    doc: {docstatus: 1, status: 'Closed', scanned_cartons: 9, dispatched_cartons: 9, remaining_stock: 0,
        cancelled_cartons: 1, items: Array.from({length: 10}, (_, i) => ({qty: 144, status: i === 9 ? 'Cancelled' : 'Dispatched'}))},
    fields_dict: {items: {grid: {grid_rows: [], wrapper: {find() { return {remove() {}, after(row) { footer = row.markup; }}; }}}}},
    set_df_property() {}, add_custom_button() { return chain; }, set_intro(text) { intro = text; }
});
assert.equal(intro, 'Stock Snapshot: 9 received CTN, 9 dispatched CTN, 0 in stock CTN, 1 cancelled labels.');
assert.match(footer, /Total CTN/);
assert.match(footer, /<span>9<\/span>/);
assert.doesNotMatch(footer, /1296|1440|Total Qty/);
console.log('Batch snapshot distinguishes received/current stock and totals cartons, excluding cancelled labels.');

const stored = {};
context.localStorage = {getItem: key => stored[key], setItem: (key, value) => { stored[key] = value; }};
context.URLSearchParams = URLSearchParams;
context.window = {location: {href: ''}};
context.frappe.boot = {lang: 'en'};
context.frappe.urllib = {get_full_url: url => 'https://example.test' + url};
for (const count of [2, 4, 6, 8]) {
    context.open_batch_label_print({doctype: 'Batch QR Maker', docname: 'BCH /# test'}, count, false);
    const url = new URL(context.window.location.href);
    assert.equal(JSON.parse(url.searchParams.get('settings')).warehouse_labels_per_page, count);
    assert.equal(url.searchParams.get('name'), 'BCH /# test');
    assert.equal(url.searchParams.get('trigger_print'), '0');
    assert.equal(stored.warehouse_labels_per_page, String(count));
}
context.open_batch_label_print({doctype: 'Batch QR Maker', docname: 'BCH'}, 100, true);
const printURL = new URL(context.window.location.href);
assert.equal(JSON.parse(printURL.searchParams.get('settings')).warehouse_labels_per_page, 2);
assert.equal(printURL.searchParams.get('trigger_print'), '1');
console.log('Print/preview URLs carry the selected layout and safely default invalid choices.');
