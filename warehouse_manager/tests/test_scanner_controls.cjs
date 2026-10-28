const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../www/scanner.html'), 'utf8');
const script = source.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
function extract(start, end) {
    return source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
}
const calls = [];
const nodes = new Map();
const makeNode = () => ({children: [], style: {}, append(...children) { this.children.push(...children); },
    replaceChildren() { this.children = []; }, addEventListener(event, action) { this[event] = action; }});
const context = vm.createContext({
    stockMode: 'In', activeDN: {dn_id: 'DN-OLD'},
    localStorage: {getItem: () => 'test-token'}, getServerSessionKey: mode => `session-${mode}`,
    suppliersData: ["Ahmed's Trading", '<Example & Co>'], customersData: ["Customer's Name"],
    document: {getElementById(id) { if (!nodes.has(id)) nodes.set(id, makeNode()); return nodes.get(id); }, createElement: makeNode},
    processWorkflowLog: (...args) => calls.push(args)
});
vm.runInContext(extract('function buildStockLogPayload(', 'async function handleStockLog('), context);
assert.equal(vm.runInContext("buildStockLogPayload('CRT', {mode: 'In', delivery_note: 'DN-OLD'}).delivery_note", context), null);
context.stockMode = 'Out';
assert.equal(vm.runInContext("buildStockLogPayload('CRT', {mode: 'Out'}).delivery_note", context), null);
context.stockMode = 'Delivery';
assert.equal(vm.runInContext("buildStockLogPayload('CRT', {mode: 'Out'}).delivery_note", context), 'DN-OLD');
vm.runInContext(extract('function renderMetadataList(', 'function buildStockLogPayload('), context);
vm.runInContext("renderMetadataList('Supplier')", context);
const row = nodes.get('metadata-results').children[0];
assert.equal(row.children[0].textContent, "Ahmed's Trading");
row.click();
assert.deepEqual(calls[0], ['Supplier', "Ahmed's Trading"]);
console.log('Scanner syntax, mode isolation, apostrophes, and literal party names passed.');
