import frappe
from frappe import _
from frappe.utils import cint

from warehouse_manager.stock_queries import latest_active_log, active_log


def execute(filters=None):
	filters = filters or {}
	conditions, params = [], {"aging_days": max(cint(filters.get("aging_days", 30)), 1)}
	for field in ("item", "carton_no"):
		if filters.get(field):
			conditions.append(f"sl.{field} = %({field})s")
			params[field] = filters[field]
	where = " AND " + " AND ".join(conditions) if conditions else ""
	rows = frappe.db.sql(f"""
		SELECT sl.name AS stock_log, sl.carton_no, sl.item, sl.scan_time,
			sl.delivery_note, c.status AS carton_status,
			CASE WHEN c.name IS NULL THEN 'Missing Carton QR'
				WHEN c.status != CASE WHEN sl.type = 'In' THEN 'In Stock' ELSE 'Dispatched' END
				THEN 'Carton Status Mismatch'
				ELSE 'Inactive Stock' END AS issue
		FROM `tabStock Log` sl LEFT JOIN `tabCarton QR` c ON c.name = sl.carton_no
		WHERE {latest_active_log('sl')} {where}
		AND (c.name IS NULL OR c.status != CASE WHEN sl.type = 'In' THEN 'In Stock' ELSE 'Dispatched' END
			OR (sl.type = 'In' AND COALESCE(sl.scan_time, sl.creation) < DATE_SUB(NOW(), INTERVAL %(aging_days)s DAY)))
		UNION ALL
		SELECT sl.name, sl.carton_no, sl.item, sl.scan_time, sl.delivery_note, NULL,
			CASE WHEN sl.type = 'Out' AND IFNULL(sl.customer, '') = '' THEN 'Missing Dispatch Customer'
				WHEN sl.source_type = 'Purchase' THEN 'Missing Supplier'
				WHEN sl.source_type = 'Return Stock' THEN 'Missing Return Customer'
				ELSE 'Missing Inbound Source' END
		FROM `tabStock Log` sl
		WHERE {active_log('sl')} {where}
		AND ((sl.type = 'Out' AND IFNULL(sl.customer, '') = '')
			OR (sl.type = 'In' AND (IFNULL(sl.source_type, '') = ''
				OR (sl.source_type = 'Purchase' AND IFNULL(sl.supplier, '') = '')
				OR (sl.source_type = 'Return Stock' AND IFNULL(sl.customer, '') = ''))))
		ORDER BY scan_time DESC LIMIT 500
	""", params, as_dict=True)
	columns = [
		{"fieldname": "issue", "label": _("Exception"), "fieldtype": "Data", "width": 210},
		{"fieldname": "stock_log", "label": _("Stock Log"), "fieldtype": "Link", "options": "Stock Log", "width": 140},
		{"fieldname": "carton_no", "label": _("Carton"), "fieldtype": "Data", "width": 160},
		{"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 150},
		{"fieldname": "carton_status", "label": _("Carton Status"), "fieldtype": "Data", "width": 130},
		{"fieldname": "delivery_note", "label": _("Delivery Note"), "fieldtype": "Link", "options": "Delivery Note", "width": 150},
		{"fieldname": "scan_time", "label": _("Scan Time"), "fieldtype": "Datetime", "width": 170},
	]
	message = _("Showing up to 500 exceptions. Filter by item or carton to narrow results.")
	return columns, rows, message
