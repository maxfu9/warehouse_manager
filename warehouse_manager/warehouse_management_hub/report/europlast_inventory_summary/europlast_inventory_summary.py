import frappe
from frappe import _

def execute(filters=None):
	filters = filters or {}
	columns, data = [], []
	columns = get_columns()
	data = get_data(filters)
	
	chart = get_chart(data)
	report_summary = get_report_summary(data)

	return columns, data, None, chart, report_summary

def get_columns():
	return [
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 140},
		{"label": _("Cartons"), "fieldname": "cartons", "fieldtype": "Small Text", "width": 220},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 100},
		{"label": _("Total In (Qty)"), "fieldname": "total_in", "fieldtype": "Float", "width": 110},
		{"label": _("Total Out (Qty)"), "fieldname": "total_out", "fieldtype": "Float", "width": 110},
		{"label": _("Balance (Qty)"), "fieldname": "balance", "fieldtype": "Float", "width": 110},
		{"label": _("Cartons in Stock"), "fieldname": "carton_count", "fieldtype": "Int", "width": 120},
		{"label": _("Last Inbound"), "fieldname": "last_inbound", "fieldtype": "Datetime", "width": 155}
	]

def get_chart(data):
	if not data:
		return None

	# Sort by balance descending and take top 5
	top_items = sorted(data, key=lambda x: x.get("balance", 0), reverse=True)[:5]

	return {
		"data": {
			"labels": [d.get("item") for d in top_items],
			"datasets": [
				{
					"name": _("Stock Balance"),
					"values": [d.get("balance") for d in top_items]
				}
			]
		},
		"type": "bar",
		"colors": ["#48bb78"]
	}

def get_report_summary(data):
	if not data:
		return []

	total_stock = sum(d.get("balance", 0) for d in data)
	total_cartons = sum(d.get("carton_count", 0) for d in data)

	return [
		{"value": total_stock, "indicator": "Green", "label": _("Total Units In Stock"), "datatype": "Float"},
		{"value": total_cartons, "indicator": "Blue", "label": _("Total Cartons on Floor"), "datatype": "Int"}
	]

def get_data(filters):
	conditions = []
	params = {}

	if filters.get("from_date"):
		conditions.append("sl.scan_time >= %(from_date)s")
		params["from_date"] = filters.get("from_date")
	if filters.get("to_date"):
		conditions.append("sl.scan_time <= %(to_date)s")
		params["to_date"] = f"{filters.get('to_date')} 23:59:59"
	if filters.get("item"):
		conditions.append("sl.item = %(item)s")
		params["item"] = filters.get("item")
	if filters.get("batch"):
		conditions.append("sl.batch = %(batch)s")
		params["batch"] = filters.get("batch")
	if filters.get("source_type"):
		conditions.append("sl.source_type = %(source_type)s")
		params["source_type"] = filters.get("source_type")

	where_clause = f" AND {' AND '.join(conditions)}" if conditions else ""

	raw_data = frappe.db.sql(
		f"""
		SELECT 
			sl.item,
			item.item_name,
			sl.batch,
			sl.uom,
			SUM(CASE WHEN sl.type = 'In' THEN sl.qty ELSE 0 END) as total_in,
			SUM(CASE WHEN sl.type = 'Out' THEN sl.qty ELSE 0 END) as total_out,
			SUM(
				CASE
					WHEN latest.name IS NOT NULL AND latest.type = 'In' THEN 1
					ELSE 0
				END
			) as carton_count,
			GROUP_CONCAT(
				DISTINCT CASE
					WHEN latest.name IS NOT NULL AND latest.type = 'In' THEN latest.carton_no
					ELSE NULL
				END
				ORDER BY latest.carton_no SEPARATOR ', '
			) as cartons,
			MAX(CASE WHEN latest.name IS NOT NULL AND latest.type = 'In' THEN latest.scan_time END) as last_inbound
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
		GROUP BY sl.item, item.item_name, sl.batch, sl.uom
		ORDER BY SUM(CASE WHEN sl.type = 'In' THEN sl.qty ELSE 0 END) - SUM(CASE WHEN sl.type = 'Out' THEN sl.qty ELSE 0 END) DESC
		""",
		params,
		as_dict=1,
	)

	for d in raw_data:
		d.balance = (d.total_in or 0) - (d.total_out or 0)

	return [d for d in raw_data if (d.balance or 0) > 0 and (d.carton_count or 0) > 0]
