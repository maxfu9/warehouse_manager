import frappe
from frappe import _

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Total Qty Shipped"), "fieldname": "total_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Carton Count"), "fieldname": "carton_count", "fieldtype": "Int", "width": 110},
		{"label": _("Latest Ship Date"), "fieldname": "latest_date", "fieldtype": "Date", "width": 130}
	]

def get_data(filters):
	conditions = ""
	if filters.get("customer"):
		conditions += f" AND customer = '{filters.get('customer')}'"
	if filters.get("item"):
		conditions += f" AND item = '{filters.get('item')}'"

	data = frappe.db.sql(f"""
		SELECT 
			customer, item, 
			SUM(qty) as total_qty,
			COUNT(DISTINCT carton_no) as carton_count,
			MAX(DATE(scan_time)) as latest_date
		FROM `tabStock Log`
		WHERE type = 'Out' 
		AND customer IS NOT NULL
		{conditions}
		GROUP BY customer, item
		ORDER BY latest_date DESC
	""", as_dict=1)
	
	return data
