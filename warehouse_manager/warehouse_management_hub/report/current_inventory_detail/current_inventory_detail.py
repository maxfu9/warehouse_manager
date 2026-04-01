import frappe
from frappe import _
from frappe.utils import date_diff, nowdate

def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{"label": _("Carton No"), "fieldname": "carton_no", "fieldtype": "Data", "width": 140},
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 140},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Inbound Time"), "fieldname": "inbound_time", "fieldtype": "Datetime", "width": 155},
		{"label": _("Source Type"), "fieldname": "source_type", "fieldtype": "Data", "width": 110},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Aging (Days)"), "fieldname": "aging", "fieldtype": "Int", "width": 100}
	]

def get_data(filters):
	conditions = []
	params = {}

	if filters.get("item"):
		conditions.append("sl.item = %(item)s")
		params["item"] = filters.get("item")
	if filters.get("batch"):
		conditions.append("sl.batch = %(batch)s")
		params["batch"] = filters.get("batch")
	if filters.get("source_type"):
		conditions.append("sl.source_type = %(source_type)s")
		params["source_type"] = filters.get("source_type")
	if filters.get("from_date"):
		conditions.append("DATE(sl.scan_time) >= %(from_date)s")
		params["from_date"] = filters.get("from_date")
	if filters.get("to_date"):
		conditions.append("DATE(sl.scan_time) <= %(to_date)s")
		params["to_date"] = filters.get("to_date")

	where_clause = f"AND {' AND '.join(conditions)}" if conditions else ""

	data = frappe.db.sql(
		f"""
		SELECT 
			sl.carton_no,
			sl.batch,
			sl.item,
			item.item_name,
			sl.qty,
			sl.uom,
			sl.scan_time as inbound_time,
			sl.source_type,
			sl.supplier,
			sl.customer
		FROM `tabStock Log` sl
		LEFT JOIN `tabItem` item ON item.name = sl.item
		WHERE sl.type = 'In'
		{where_clause}
		AND NOT EXISTS (
			SELECT 1
			FROM `tabStock Log` newer
			WHERE newer.carton_no = sl.carton_no
			AND (
				newer.scan_time > sl.scan_time
				OR (newer.scan_time = sl.scan_time AND newer.name > sl.name)
			)
		)
		ORDER BY sl.scan_time ASC
		""",
		params,
		as_dict=1,
	)

	today = nowdate()
	for d in data:
		d.aging = date_diff(today, d.inbound_time)
	
	return data
