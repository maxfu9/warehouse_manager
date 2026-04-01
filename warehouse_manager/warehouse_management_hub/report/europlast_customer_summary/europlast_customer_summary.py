import frappe
from frappe import _

def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Delivery Note"), "fieldname": "delivery_note", "fieldtype": "Link", "options": "Delivery Note", "width": 150},
		{"label": _("Total Qty Shipped"), "fieldname": "total_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Carton Count"), "fieldname": "carton_count", "fieldtype": "Int", "width": 110},
		{"label": _("Latest Ship Date"), "fieldname": "latest_date", "fieldtype": "Date", "width": 130},
		{"label": _("Latest Ship Time"), "fieldname": "latest_time", "fieldtype": "Datetime", "width": 155}
	]

def get_data(filters):
	conditions = []
	params = {}

	if filters.get("customer"):
		conditions.append("sl.customer = %(customer)s")
		params["customer"] = filters.get("customer")
	if filters.get("item"):
		conditions.append("sl.item = %(item)s")
		params["item"] = filters.get("item")
	if filters.get("delivery_note"):
		conditions.append("sl.delivery_note = %(delivery_note)s")
		params["delivery_note"] = filters.get("delivery_note")
	if filters.get("from_date"):
		conditions.append("DATE(sl.scan_time) >= %(from_date)s")
		params["from_date"] = filters.get("from_date")
	if filters.get("to_date"):
		conditions.append("DATE(sl.scan_time) <= %(to_date)s")
		params["to_date"] = filters.get("to_date")

	where_clause = f" AND {' AND '.join(conditions)}" if conditions else ""

	data = frappe.db.sql(
		f"""
		SELECT 
			sl.customer,
			sl.item,
			item.item_name,
			sl.delivery_note,
			SUM(sl.qty) as total_qty,
			COUNT(DISTINCT sl.carton_no) as carton_count,
			MAX(DATE(sl.scan_time)) as latest_date,
			MAX(sl.scan_time) as latest_time
		FROM `tabStock Log` sl
		LEFT JOIN `tabItem` item ON item.name = sl.item
		WHERE sl.type = 'Out' 
		AND sl.customer IS NOT NULL
		{where_clause}
		GROUP BY sl.customer, sl.item, item.item_name, sl.delivery_note
		ORDER BY latest_date DESC
		""",
		params,
		as_dict=1,
	)
	
	return data
