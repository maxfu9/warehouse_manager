import frappe
from frappe import _
from frappe.utils import flt, nowdate, date_diff

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{"label": _("Carton No"), "fieldname": "carton_no", "fieldtype": "Data", "width": 140},
		{"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link", "options": "Batch QR Maker", "width": 140},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Inbound Date"), "fieldname": "inbound_date", "fieldtype": "Date", "width": 110},
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 120},
		{"label": _("Aging (Days)"), "fieldname": "aging", "fieldtype": "Int", "width": 100}
	]

def get_data(filters):
	# Subquery to find cartons that have an 'In' but NO 'Out'
	item_filter = ""
	if filters.get("item"):
		item_filter = f"AND item = '{filters.get('item')}'"

	data = frappe.db.sql(f"""
		SELECT 
			carton_no, batch, item, qty, uom, 
			scan_time as inbound_date,
			COALESCE(supplier, source_type) as source
		FROM `tabStock Log` t1
		WHERE type = 'In'
		{item_filter}
		AND NOT EXISTS (
			SELECT 1 FROM `tabStock Log` t2 
			WHERE t2.carton_no = t1.carton_no AND t2.type = 'Out'
		)
		ORDER BY scan_time ASC
	""", as_dict=1)

	today = nowdate()
	for d in data:
		d.aging = date_diff(today, d.inbound_date)
	
	return data
