import frappe
from frappe import _

from warehouse_manager.stock_queries import current_cartons_query


def execute(filters=None):
	data = get_data(filters or {})
	return get_columns(), data, _("Current carton status determines stock. Packing quantity is not used."), get_chart(data), get_report_summary(data)


def get_columns():
	return [
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 160},
		{"label": _("In Stock (CTN)"), "fieldname": "carton_count", "fieldtype": "Int", "width": 140},
		{"label": _("Carton Numbers"), "fieldname": "cartons", "fieldtype": "Small Text", "width": 250},
		{"label": _("Last Inbound"), "fieldname": "last_inbound", "fieldtype": "Datetime", "width": 170},
	]


def get_data(filters):
	conditions, params = ["state.status = 'In Stock'"], {}
	for field in ("item", "batch", "source_type"):
		if filters.get(field):
			conditions.append(f"state.{field} = %({field})s")
			params[field] = filters[field]
	if filters.get("from_date"):
		conditions.append("COALESCE(state.inbound_time, state.creation) >= %(from_date)s")
		params["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("COALESCE(state.inbound_time, state.creation) <= %(to_date)s")
		params["to_date"] = f"{filters['to_date']} 23:59:59.999999"
	return frappe.db.sql(f"""
		SELECT state.item, item.item_name, state.batch,
			COUNT(DISTINCT state.carton_no) AS carton_count,
			GROUP_CONCAT(DISTINCT state.carton_no ORDER BY state.carton_no SEPARATOR ', ') AS cartons,
			MAX(state.inbound_time) AS last_inbound
		FROM ({current_cartons_query()}) state
		LEFT JOIN `tabItem` item ON item.name = state.item
		WHERE {' AND '.join(conditions)}
		GROUP BY state.item, item.item_name, state.batch
		ORDER BY carton_count DESC
	""", params, as_dict=True)


def get_chart(data):
	by_item = {}
	for row in data:
		by_item[row.item] = by_item.get(row.item, 0) + row.carton_count
	top = sorted(by_item.items(), key=lambda row: row[1], reverse=True)[:5]
	return {"type": "bar", "colors": ["#10b981"], "data": {
		"labels": [item for item, count in top],
		"datasets": [{"name": _("In Stock (CTN)"), "values": [count for item, count in top]}],
	}}


def get_report_summary(data):
	return [
		{"value": sum(row.carton_count for row in data), "label": _("In Stock (CTN)"), "datatype": "Int", "indicator": "Green"},
		{"value": len({row.item for row in data}), "label": _("Unique Items"), "datatype": "Int", "indicator": "Blue"},
	]
