import frappe
from frappe import _

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{"label": _("Batch ID"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 160},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Total In"), "fieldname": "total_in", "fieldtype": "Float", "width": 100},
		{"label": _("Total Out"), "fieldname": "total_out", "fieldtype": "Float", "width": 100},
		{"label": _("In Stock"), "fieldname": "balance", "fieldtype": "Float", "width": 100},
		{"label": _("Carton Count"), "fieldname": "carton_count", "fieldtype": "Int", "width": 110}
	]

def get_data(filters):
	conditions = ""
	if filters.get("batch"):
		conditions += f" AND batch = '{filters.get('batch')}'"
	if filters.get("item"):
		conditions += f" AND item = '{filters.get('item')}'"

	data = frappe.db.sql(f"""
		SELECT 
			batch, item, uom,
			SUM(CASE WHEN type = 'In' THEN qty ELSE 0 END) as total_in,
			SUM(CASE WHEN type = 'Out' THEN qty ELSE 0 END) as total_out,
			COUNT(DISTINCT CASE WHEN type = 'In' THEN carton_no END) - 
			COUNT(DISTINCT CASE WHEN type = 'Out' THEN carton_no END) as carton_count
		FROM `tabStock Log`
		WHERE 1=1 {conditions}
		GROUP BY batch, item, uom
		ORDER BY batch DESC
	""", as_dict=1)

	for d in data:
		d.balance = d.total_in - d.total_out
	
	return data
