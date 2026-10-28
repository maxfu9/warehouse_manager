import frappe
from frappe import _
from frappe.utils import date_diff, nowdate

from warehouse_manager.stock_queries import current_cartons_query


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"label": _("Carton No"), "fieldname": "carton_no", "fieldtype": "Data", "width": 160},
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 160},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("CTN"), "fieldname": "carton_count", "fieldtype": "Int", "width": 80},
		{"label": _("Inbound Time"), "fieldname": "inbound_time", "fieldtype": "Datetime", "width": 170},
		{"label": _("Source"), "fieldname": "source_type", "fieldtype": "Data", "width": 120},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("Return Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Age (Days)"), "fieldname": "aging", "fieldtype": "Int", "width": 100},
	]


def get_data(filters):
	conditions, params = ["state.status = 'In Stock'"], {}
	for field in ("item", "batch", "source_type"):
		if filters.get(field):
			conditions.append(f"state.{field} = %({field})s")
			params[field] = filters[field]
	for field, operator, suffix in (("from_date", ">=", ""), ("to_date", "<=", " 23:59:59.999999")):
		if filters.get(field):
			conditions.append(f"COALESCE(state.inbound_time, state.creation) {operator} %({field})s")
			params[field] = f"{filters[field]}{suffix}"
	rows = frappe.db.sql(f"""
		SELECT state.*, item.item_name, 1 AS carton_count
		FROM ({current_cartons_query()}) state
		LEFT JOIN `tabItem` item ON item.name = state.item
		WHERE {' AND '.join(conditions)}
		ORDER BY COALESCE(state.inbound_time, state.creation), state.carton_no
	""", params, as_dict=True)
	for row in rows:
		row.aging = date_diff(nowdate(), row.inbound_time or row.creation)
	return rows
