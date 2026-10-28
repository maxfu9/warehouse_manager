"""Carton label batches from actual Work Order production."""

from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.utils import cint, flt


def setup_production_fields():
	if not frappe.db.exists("DocType", "Work Order"):
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({
		"Work Order": [
			{"fieldname": "warehouse_labels_section", "fieldtype": "Tab Break", "label": "Warehouse Labels", "insert_after": "amended_from"},
			{"fieldname": "warehouse_create_qr_batch", "fieldtype": "Check", "label": "Allow Carton Labels", "default": "1", "insert_after": "warehouse_labels_section", "allow_on_submit": 1,
			 "description": "Permit labels for complete cartons from this Work Order. Also check Generate Carton Labels on each finished Manufacture entry."},
			{"fieldname": "warehouse_qty_per_carton", "fieldtype": "Float", "label": "Qty per Carton (Label Only)", "default": "1", "insert_after": "warehouse_create_qr_batch", "allow_on_submit": 1,
			 "description": "Packing information printed on labels; does not divide or multiply the number of cartons. Set before completing production."},
			{"fieldname": "warehouse_contents_uom", "fieldtype": "Link", "label": "Contents UOM (Label Only)", "options": "UOM", "insert_after": "warehouse_qty_per_carton", "allow_on_submit": 1},
		],
		"Stock Entry": [
			{"fieldname": "warehouse_generate_qr_batch", "fieldtype": "Check", "label": "Generate Carton Labels", "default": "0", "insert_after": "work_order", "no_copy": 1,
			 "depends_on": "eval:doc.purpose == 'Manufacture' && doc.work_order",
			 "description": "Check only for complete packed cartons. Leave unchecked for parts or intermediate production. One finished unit creates one carton QR."},
			{"fieldname": "warehouse_qr_batch", "fieldtype": "Link", "label": "Carton Label Batch", "options": "Batch QR Maker", "insert_after": "warehouse_generate_qr_batch", "read_only": 1, "allow_on_submit": 1, "no_copy": 1},
		],
	})


def produced_carton_count(entry, production_item):
	try:
		quantity = sum((Decimal(str(row.get("transfer_qty") or 0)) for row in entry.get("items", [])
			if row.get("is_finished_item") and not row.get("is_scrap_item") and row.get("item_code") == production_item), Decimal(0))
	except InvalidOperation:
		frappe.throw(_("Finished production quantity must be a whole number of cartons."))
	if not quantity.is_finite() or quantity <= 0 or quantity != quantity.to_integral_value():
		frappe.throw(_("Finished production quantity must be a positive whole number of cartons. One produced unit creates one carton QR."))
	return int(quantity)


def create_manufacture_batch(entry, method=None):
	if entry.purpose != "Manufacture" or not entry.work_order or entry.docstatus != 1:
		return
	if not cint(entry.get("warehouse_generate_qr_batch")):
		return
	# Serialize retries for the same manufacturing entry. The unique source
	# field also prevents duplicates from other entry points.
	frappe.db.sql("SELECT name FROM `tabStock Entry` WHERE name = %s FOR UPDATE", (entry.name,))
	existing = frappe.db.get_value("Batch QR Maker", {"production_stock_entry": entry.name}, ["name", "docstatus"], as_dict=True)
	if existing:
		if existing.docstatus != 1:
			frappe.throw(_("Manufacturing entry already has batch {0}. Review that batch before retrying.").format(existing.name))
		entry.db_set("warehouse_qr_batch", existing.name, update_modified=False)
		return existing.name

	order = frappe.get_doc("Work Order", entry.work_order)
	if not cint(order.get("warehouse_create_qr_batch", 1)):
		frappe.throw(_("Enable Allow Carton Labels on Work Order {0}, or uncheck Generate Carton Labels on this entry.").format(order.name))
	count = produced_carton_count(entry, order.production_item)
	packing_qty = flt(order.get("warehouse_qty_per_carton") if order.get("warehouse_qty_per_carton") is not None else 1)
	if packing_qty <= 0:
		frappe.throw(_("Qty per Carton on Work Order must be greater than zero."))
	uom = order.get("warehouse_contents_uom") or frappe.db.get_value("Item", order.production_item, "stock_uom")
	batch = frappe.get_doc({
		"doctype": "Batch QR Maker", "item": order.production_item,
		"date": entry.posting_date, "no_of_cartons": count,
		"qty_per_carton": packing_qty, "uom": uom, "status": "Draft",
		"work_order": order.name, "production_stock_entry": entry.name,
	})
	batch.flags.ignore_permissions = True
	batch.insert(ignore_permissions=True)
	batch.generate_cartons()
	batch.submit()
	entry.db_set("warehouse_qr_batch", batch.name, update_modified=False)
	return batch.name


def _locked_production_batches(entry):
	batch_names = frappe.get_all("Batch QR Maker", filters={"production_stock_entry": entry.name, "docstatus": ["!=", 2]}, pluck="name")
	for name in batch_names:
		# Stock scans lock the carton before updating its batch; use that order.
		cartons = frappe.db.sql("SELECT name, status FROM `tabCarton QR` WHERE batch = %s ORDER BY name FOR UPDATE", (name,), as_dict=True)
		batch = frappe.get_doc("Batch QR Maker", name, for_update=True)
		used = frappe.db.sql("""
			SELECT sl.name FROM `tabStock Log` sl
			WHERE IFNULL(sl.movement_status, 'Logged') != 'Cancelled'
			AND (sl.batch = %(batch)s OR sl.carton_no IN (
				SELECT carton_no FROM `tabBatch QR Maker Item` WHERE parent = %(batch)s
			)) LIMIT 1 FOR UPDATE
		""", {"batch": name})
		if used or any(row.status in ("In Stock", "Dispatched") for row in cartons) or any(row.status in ("In Stock", "Dispatched") for row in batch.items):
			frappe.throw(_("Batch {0} has received or dispatched cartons. Reverse those movements before cancelling manufacture.").format(name))
		yield batch


def validate_manufacture_cancellation(entry, method=None):
	if entry.purpose == "Manufacture" and entry.work_order:
		list(_locked_production_batches(entry))


def cancel_manufacture_batch(entry, method=None):
	if entry.purpose != "Manufacture" or not entry.work_order:
		return
	for batch in _locked_production_batches(entry):
		batch.flags.ignore_permissions = True
		if batch.docstatus == 1:
			batch.cancel()
		frappe.db.sql("UPDATE `tabBatch QR Maker Item` SET status = 'Cancelled' WHERE parent = %s", (batch.name,))
		frappe.db.set_value("Batch QR Maker", batch.name, {
			"cancelled_cartons": len(batch.items), "scanned_cartons": 0,
			"dispatched_cartons": 0, "remaining_stock": 0,
		})
	# Keep the source link for audit; cancelled batches do not block cancellation.


def work_order_dashboard(data):
	data.setdefault("transactions", []).append({"label": _("Warehouse"), "items": ["Batch QR Maker"]})
	data.setdefault("non_standard_fieldnames", {})["Batch QR Maker"] = "work_order"
	return data


def stock_entry_dashboard(data):
	data.setdefault("transactions", []).append({"label": _("Warehouse"), "items": ["Batch QR Maker"]})
	data.setdefault("non_standard_fieldnames", {})["Batch QR Maker"] = "production_stock_entry"
	return data
