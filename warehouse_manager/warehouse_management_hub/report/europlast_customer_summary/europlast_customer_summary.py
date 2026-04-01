import frappe
from frappe import _

def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	report_summary = get_report_summary(data)
	return columns, data, None, chart, report_summary

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

def get_chart(data):
	if not data:
		return None

	top_customers = sorted(data, key=lambda x: x.get("total_qty", 0), reverse=True)[:5]
	return {
		"data": {
			"labels": [row.get("customer") or _("Unknown") for row in top_customers],
			"datasets": [
				{"name": _("Shipped Qty"), "values": [row.get("total_qty") or 0 for row in top_customers]},
				{"name": _("Cartons"), "values": [row.get("carton_count") or 0 for row in top_customers]},
			],
		},
		"type": "bar",
		"colors": ["#f59e0b", "#0ea5e9"],
	}

def get_report_summary(data):
	if not data:
		return []

	total_qty = sum(row.get("total_qty") or 0 for row in data)
	total_cartons = sum(row.get("carton_count") or 0 for row in data)
	return [
		{"value": len({row.get('customer') for row in data if row.get('customer')}), "indicator": "Blue", "label": _("Customers"), "datatype": "Int"},
		{"value": total_qty, "indicator": "Orange", "label": _("Shipped Qty"), "datatype": "Float"},
		{"value": total_cartons, "indicator": "Green", "label": _("Shipped Cartons"), "datatype": "Int"},
	]
