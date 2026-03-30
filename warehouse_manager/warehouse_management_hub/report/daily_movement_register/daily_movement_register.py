import frappe
from frappe import _

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
		{"label": _("Time"), "fieldname": "time", "fieldtype": "Time", "width": 90},
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 140},
		{"label": _("Movement"), "fieldname": "type", "fieldtype": "Data", "width": 100},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Carton No"), "fieldname": "carton_no", "fieldtype": "Data", "width": 140},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Data", "width": 150}
	]

def get_data(filters):
	conditions = ""
	if filters.get("from_date"):
		conditions += f" AND DATE(scan_time) >= '{filters.get('from_date')}'"
	if filters.get("to_date"):
		conditions += f" AND DATE(scan_time) <= '{filters.get('to_date')}'"
	if filters.get("type"):
		conditions += f" AND type = '{filters.get('type')}'"

	data = frappe.db.sql(f"""
		SELECT 
			DATE(scan_time) as date,
			TIME(scan_time) as time,
			batch,
			type,
			item,
			carton_no,
			qty,
			COALESCE(customer, supplier, source_type) as party
		FROM `tabStock Log`
		WHERE 1=1 {conditions}
		ORDER BY scan_time DESC
	""", as_dict=1)
	
	return data
