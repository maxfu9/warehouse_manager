import frappe
from frappe import _

from warehouse_manager.stock_queries import current_cartons_query


def execute(filters=None):
	data = get_data(filters or {})
	return get_columns(), data, _("Counts are cartons, based on current carton/batch-row status."), get_chart(data), get_report_summary(data)


def get_columns():
	return [
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 160},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Received (CTN)"), "fieldname": "received_cartons", "fieldtype": "Int", "width": 140},
		{"label": _("Dispatched (CTN)"), "fieldname": "dispatched_cartons", "fieldtype": "Int", "width": 140},
		{"label": _("In Stock (CTN)"), "fieldname": "carton_count", "fieldtype": "Int", "width": 140},
		{"label": _("Cancelled Labels"), "fieldname": "cancelled_cartons", "fieldtype": "Int", "width": 140},
		{"label": _("Last Movement"), "fieldname": "last_movement", "fieldtype": "Datetime", "width": 170},
	]


def get_data(filters):
	conditions, params = ["IFNULL(state.batch, '') != ''"], {}
	for field in ("item", "batch"):
		if filters.get(field):
			conditions.append(f"state.{field} = %({field})s")
			params[field] = filters[field]
	for field, operator, suffix in (("from_date", ">=", ""), ("to_date", "<=", " 23:59:59.999999")):
		if filters.get(field):
			conditions.append(f"state.last_movement {operator} %({field})s")
			params[field] = f"{filters[field]}{suffix}"
	return frappe.db.sql(f"""
		SELECT state.batch, state.item, item.item_name,
			COUNT(DISTINCT CASE WHEN state.status IN ('In Stock', 'Dispatched') THEN state.carton_no END) AS received_cartons,
			COUNT(DISTINCT CASE WHEN state.status = 'Dispatched' THEN state.carton_no END) AS dispatched_cartons,
			COUNT(DISTINCT CASE WHEN state.status = 'In Stock' THEN state.carton_no END) AS carton_count,
			COUNT(DISTINCT CASE WHEN state.status = 'Cancelled' THEN state.carton_no END) AS cancelled_cartons,
			MAX(state.last_movement) AS last_movement
		FROM ({current_cartons_query()}) state LEFT JOIN `tabItem` item ON item.name = state.item
		WHERE {' AND '.join(conditions)}
		GROUP BY state.batch, state.item, item.item_name
		ORDER BY last_movement DESC
	""", params, as_dict=True)


def get_chart(data):
	if not data:
		return None
	top = sorted(data, key=lambda row: row.carton_count, reverse=True)[:5]
	return {"type": "bar", "colors": ["#10b981", "#3b82f6"], "data": {
		"labels": [row.batch for row in top],
		"datasets": [
			{"name": _("In Stock (CTN)"), "values": [row.carton_count for row in top]},
			{"name": _("Dispatched (CTN)"), "values": [row.dispatched_cartons for row in top]},
		],
	}}


def get_report_summary(data):
	return [{"value": sum(row.get(field, 0) for row in data), "label": _(label), "datatype": "Int", "indicator": color}
		for field, label, color in (("received_cartons", "Received (CTN)", "Blue"),
			("dispatched_cartons", "Dispatched (CTN)", "Orange"), ("carton_count", "In Stock (CTN)", "Green"))]
