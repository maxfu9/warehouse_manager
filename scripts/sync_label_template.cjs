// The JSON export and HTML template must stay identical for site reloads.
const fs = require('node:fs');
const path = require('node:path');
const folder = path.join(__dirname, '../warehouse_manager/warehouse_management_hub/print_format/batch_labels_a5');
const file = path.join(folder, 'batch_labels_a5.json');
const definition = JSON.parse(fs.readFileSync(file, 'utf8'));
definition.html = fs.readFileSync(path.join(folder, 'batch_labels_a5.html'), 'utf8');
fs.writeFileSync(file, JSON.stringify(definition, null, 1) + '\n');
