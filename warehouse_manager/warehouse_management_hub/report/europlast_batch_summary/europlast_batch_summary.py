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
		{"label": _("Batch ID"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 160},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Total In"), "fieldname": "total_in", "fieldtype": "Float", "width": 100},
		{"label": _("Total Out"), "fieldname": "total_out", "fieldtype": "Float", "width": 100},
		{"label": _("In Stock"), "fieldname": "balance", "fieldtype": "Float", "width": 100},
		{"label": _("Cartons in Stock"), "fieldname": "carton_count", "fieldtype": "Int", "width": 110},
		{"label": _("Last Movement"), "fieldname": "last_movement", "fieldtype": "Datetime", "width": 155},
		{"label": _("Batch Age (Days)"), "fieldname": "aging_days", "fieldtype": "Int", "width": 110}
	]

def get_data(filters):
	conditions = []
	params = {}

	if filters.get("batch"):
		conditions.append("sl.batch = %(batch)s")
		params["batch"] = filters.get("batch")
	if filters.get("item"):
		conditions.append("sl.item = %(item)s")
		params["item"] = filters.get("item")
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
			sl.batch,
			sl.item,
			item.item_name,
			sl.uom,
			SUM(CASE WHEN sl.type = 'In' THEN sl.qty ELSE 0 END) as total_in,
			SUM(CASE WHEN sl.type = 'Out' THEN sl.qty ELSE 0 END) as total_out,
			SUM(
				CASE
					WHEN latest.name IS NOT NULL AND latest.type = 'In' THEN 1
					ELSE 0
				END
			) as carton_count,
			MAX(sl.scan_time) as last_movement
		FROM `tabStock Log` sl
		LEFT JOIN `tabItem` item ON item.name = sl.item
		LEFT JOIN (
			SELECT cur.*
			FROM `tabStock Log` cur
			WHERE NOT EXISTS (
				SELECT 1
				FROM `tabStock Log` newer
				WHERE newer.carton_no = cur.carton_no
				AND (
					newer.scan_time > cur.scan_time
					OR (newer.scan_time = cur.scan_time AND newer.name > cur.name)
				)
			)
		) latest ON latest.carton_no = sl.carton_no
			AND latest.item = sl.item
			AND IFNULL(latest.batch, '') = IFNULL(sl.batch, '')
			AND latest.uom = sl.uom
		WHERE 1=1 {where_clause}
		GROUP BY sl.batch, sl.item, item.item_name, sl.uom
		ORDER BY last_movement DESC
		""",
		params,
		as_dict=1,
	)

	today = nowdate()
	for d in data:
		d.balance = (d.total_in or 0) - (d.total_out or 0)
		d.aging_days = date_diff(today, d.last_movement) if d.last_movement else 0
	
	return data
