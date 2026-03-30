import frappe
from frappe import _

def execute(filters=None):
	columns, data = [], []
	columns = get_columns()
	data = get_data(filters)
	
	chart = get_chart(data)
	report_summary = get_report_summary(data)

	return columns, data, None, chart, report_summary

def get_columns():
	return [
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 140},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 100},
		{"label": _("Total In (Qty)"), "fieldname": "total_in", "fieldtype": "Float", "width": 110},
		{"label": _("Total Out (Qty)"), "fieldname": "total_out", "fieldtype": "Float", "width": 110},
		{"label": _("Balance (Qty)"), "fieldname": "balance", "fieldtype": "Float", "width": 110},
		{"label": _("Cartons in Stock"), "fieldname": "carton_count", "fieldtype": "Int", "width": 120}
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
	conditions = ""
	if filters.get("from_date"):
		conditions += f" AND scan_time >= '{filters.get('from_date')}'"
	if filters.get("to_date"):
		conditions += f" AND scan_time <= '{filters.get('to_date')} 23:59:59'"
	if filters.get("item"):
		conditions += f" AND item = '{filters.get('item')}'"

	# 1. Get totals
	raw_data = frappe.db.sql(f"""
		SELECT 
			item, batch, uom,
			SUM(CASE WHEN type = 'In' THEN qty ELSE 0 END) as total_in,
			SUM(CASE WHEN type = 'Out' THEN qty ELSE 0 END) as total_out
		FROM `tabStock Log`
		WHERE 1=1 {conditions}
		GROUP BY item, batch, uom
	""", as_dict=1)

	for d in raw_data:
		d.balance = d.total_in - d.total_out
		
		# 2. Get current carton count (those with IN but no OUT logs)
		# Filter by item AND batch to get specific batch status
		d.carton_count = frappe.db.sql("""
			SELECT COUNT(DISTINCT carton_no)
			FROM `tabStock Log` t1
			WHERE item = %s
			AND (batch = %s OR batch IS NULL)
			AND type = 'In'
			AND NOT EXISTS (
				SELECT 1 FROM `tabStock Log` t2 
				WHERE t2.carton_no = t1.carton_no AND t2.type = 'Out'
			)
		""", (d.item, d.batch))[0][0]

	return raw_data
