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
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
		{"label": _("Time"), "fieldname": "time", "fieldtype": "Time", "width": 90},
		{"label": _("Movement"), "fieldname": "type", "fieldtype": "Data", "width": 100},
		{"label": _("Carton No"), "fieldname": "carton_no", "fieldtype": "Data", "width": 140},
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 140},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("Delivery Note"), "fieldname": "delivery_note", "fieldtype": "Link", "options": "Delivery Note", "width": 150},
		{"label": _("Source Type"), "fieldname": "source_type", "fieldtype": "Data", "width": 110},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Data", "width": 150}
	]

def get_data(filters):
	conditions = []
	params = {}

	if filters.get("from_date"):
		conditions.append("DATE(scan_time) >= %(from_date)s")
		params["from_date"] = filters.get("from_date")
	if filters.get("to_date"):
		conditions.append("DATE(scan_time) <= %(to_date)s")
		params["to_date"] = filters.get("to_date")
	if filters.get("type"):
		conditions.append("type = %(type)s")
		params["type"] = filters.get("type")
	if filters.get("item"):
		conditions.append("item = %(item)s")
		params["item"] = filters.get("item")
	if filters.get("batch"):
		conditions.append("batch = %(batch)s")
		params["batch"] = filters.get("batch")
	if filters.get("carton_no"):
		conditions.append("carton_no = %(carton_no)s")
		params["carton_no"] = filters.get("carton_no")
	if filters.get("customer"):
		conditions.append("customer = %(customer)s")
		params["customer"] = filters.get("customer")
	if filters.get("supplier"):
		conditions.append("supplier = %(supplier)s")
		params["supplier"] = filters.get("supplier")
	if filters.get("delivery_note"):
		conditions.append("delivery_note = %(delivery_note)s")
		params["delivery_note"] = filters.get("delivery_note")
	if filters.get("source_type"):
		conditions.append("source_type = %(source_type)s")
		params["source_type"] = filters.get("source_type")

	where_clause = f" AND {' AND '.join(conditions)}" if conditions else ""

	data = frappe.db.sql(
		f"""
		SELECT 
			DATE(scan_time) as date,
			TIME(scan_time) as time,
			type,
			carton_no,
			batch,
			item,
			customer,
			supplier,
			delivery_note,
			source_type,
			qty,
			COALESCE(customer, supplier, source_type) as party
		FROM `tabStock Log`
		WHERE 1=1 {where_clause}
		ORDER BY scan_time DESC
		""",
		params,
		as_dict=1,
	)
	
	return data

def get_chart(data):
	if not data:
		return None

	day_map = {}
	for row in reversed(data):
		date_key = str(row.get("date"))
		entry = day_map.setdefault(date_key, {"In": 0, "Out": 0})
		entry[row.get("type")] = entry.get(row.get("type"), 0) + 1

	labels = list(day_map.keys())[-7:]
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Inbound"), "values": [day_map[d].get("In", 0) for d in labels]},
				{"name": _("Outbound"), "values": [day_map[d].get("Out", 0) for d in labels]},
			],
		},
		"type": "bar",
		"colors": ["#10b981", "#3b82f6"],
	}

def get_report_summary(data):
	if not data:
		return []

	inbound = sum(1 for row in data if row.get("type") == "In")
	outbound = sum(1 for row in data if row.get("type") == "Out")
	total_qty = sum(row.get("qty") or 0 for row in data)
	return [
		{"value": inbound, "indicator": "Green", "label": _("Inbound Scans"), "datatype": "Int"},
		{"value": outbound, "indicator": "Blue", "label": _("Outbound Scans"), "datatype": "Int"},
		{"value": total_qty, "indicator": "Orange", "label": _("Movement Qty"), "datatype": "Float"},
	]
