"""Persist scanner sessions without requiring a Desk login."""

from uuid import UUID

import frappe
from frappe import _
from frappe.utils import now_datetime


def validate_session_key(key):
	try:
		return str(UUID(str(key)))
	except (ValueError, TypeError, AttributeError):
		frappe.throw(_("Invalid scanner session ID. Start a new lot or dispatch."))


def lock_scan_session(key, mode, source_type=None, supplier=None, customer=None):
	# Older scanner clients keep working; new clients always supply a UUID.
	if not key:
		return None
	key = validate_session_key(key)
	if not frappe.db.exists("Warehouse Scan Session", key):
		frappe.get_doc({
			"doctype": "Warehouse Scan Session", "session_key": key,
			"mode": mode, "status": "Open", "source_type": source_type if mode == "In" else None,
			"supplier": supplier if mode == "In" else None,
			"customer": customer if mode == "In" else None,
		}).insert(ignore_permissions=True, ignore_if_duplicate=True)
	rows = frappe.db.sql(
		"SELECT mode, status, source_type, supplier, customer FROM `tabWarehouse Scan Session` WHERE name = %s FOR UPDATE",
		(key,), as_dict=True,
	)
	session = rows[0]
	if session.status != "Open" or session.mode != mode:
		frappe.throw(_("This scan session is closed or belongs to another mode. Start a new session."))
	if mode == "In" and any((session.get(field) or "") != (value or "") for field, value in (
		("source_type", source_type), ("supplier", supplier), ("customer", customer),
	)):
		frappe.throw(_("This lot has a different source or partner. Close the lot before changing it."))
	return key


@frappe.whitelist(allow_guest=True)
def get_scan_session(session_key, token=None):
	from warehouse_manager.api import validate_token

	validate_token(token)
	key = validate_session_key(session_key)
	if not frappe.db.exists("Warehouse Scan Session", key):
		return None
	session = frappe.get_doc("Warehouse Scan Session", key)
	items = frappe.db.sql("""
		SELECT sl.item, COALESCE(i.item_name, sl.item) AS name, SUM(sl.qty) AS qty, COUNT(*) AS scans
		FROM `tabStock Log` sl LEFT JOIN `tabItem` i ON i.name = sl.item
		WHERE sl.scan_session = %s AND IFNULL(sl.movement_status, 'Logged') != 'Cancelled'
		GROUP BY sl.item, i.item_name
	""", (key,), as_dict=True)
	return {"session_key": key, "mode": session.mode, "status": session.status,
		"source_type": session.source_type, "supplier": session.supplier, "customer": session.customer,
		"items": items, "cartons": sum(row.scans for row in items)}


@frappe.whitelist(allow_guest=True)
def close_scan_session(session_key, token=None):
	from warehouse_manager.api import validate_token

	validate_token(token)
	key = validate_session_key(session_key)
	rows = frappe.db.sql("SELECT status FROM `tabWarehouse Scan Session` WHERE name = %s FOR UPDATE", (key,))
	if rows and rows[0][0] == "Open":
		frappe.db.set_value("Warehouse Scan Session", key, {"status": "Closed", "closed_at": now_datetime()})
	return {"status": "success"}
