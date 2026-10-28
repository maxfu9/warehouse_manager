"""Shared stock-state ordering and transaction locks."""

import frappe
from frappe import _


def lock_delivery_note(name):
	# All writers for a DN share this row lock, including Desk saves and reopens.
	rows = frappe.db.sql("SELECT name FROM `tabDelivery Note` WHERE name = %s FOR UPDATE", (name,))
	if not rows:
		frappe.throw(_("Delivery Note {0} not found").format(name))


def active_log(alias):
	return f"IFNULL({alias}.movement_status, 'Logged') != 'Cancelled'"


def latest_active_log(alias, movement_type=None):
	type_condition = f"AND newer.type = {alias}.type" if movement_type else ""
	return f"""{active_log(alias)} AND NOT EXISTS (
		SELECT 1 FROM `tabStock Log` newer
		WHERE newer.carton_no = {alias}.carton_no AND {active_log('newer')}
		{type_condition}
		AND (
			COALESCE(newer.scan_time, newer.creation) > COALESCE({alias}.scan_time, {alias}.creation)
			OR (COALESCE(newer.scan_time, newer.creation) = COALESCE({alias}.scan_time, {alias}.creation)
				AND (newer.creation > {alias}.creation
					OR (newer.creation = {alias}.creation AND newer.name > {alias}.name)))
		)
	)"""


def current_cartons_query():
	"""Live carton state, with batch-row fallback for missing tracking records.

	Movement history supplies context, not the available-stock calculation.
	"""
	return f"""
		SELECT state.*, receipt.source_type, receipt.supplier, receipt.customer,
			receipt.scan_time AS inbound_time,
			COALESCE(last_log.scan_time, state.creation) AS last_movement
		FROM (
			SELECT c.name AS carton_no,
				CASE WHEN bi.parent IS NOT NULL AND (bi.status = 'Cancelled' OR IFNULL(c.batch, '') = '')
					THEN parent_batch.item ELSE c.item END AS item,
				COALESCE(NULLIF(c.batch, ''), bi.parent) AS batch, c.qty, c.uom,
				CASE WHEN bi.parent IS NOT NULL AND (bi.status = 'Cancelled' OR IFNULL(c.batch, '') = '')
					THEN bi.status ELSE c.status END AS status, c.creation
			FROM `tabCarton QR` c
			LEFT JOIN `tabBatch QR Maker Item` bi ON bi.carton_no = c.name
				AND (IFNULL(c.batch, '') = '' OR c.batch = bi.parent)
			LEFT JOIN `tabBatch QR Maker` parent_batch ON parent_batch.name = bi.parent
			UNION ALL
			SELECT bi.carton_no, b.item, bi.parent, bi.qty, bi.uom, bi.status, b.creation
			FROM `tabBatch QR Maker Item` bi
			INNER JOIN `tabBatch QR Maker` b ON b.name = bi.parent
			WHERE IFNULL(bi.carton_no, '') != '' AND NOT EXISTS (
				SELECT 1 FROM `tabCarton QR` c WHERE c.name = bi.carton_no
					AND (IFNULL(c.batch, '') = '' OR c.batch = bi.parent)
			)
		) state
		LEFT JOIN `tabStock Log` receipt ON receipt.carton_no = state.carton_no
			AND receipt.type = 'In' AND {latest_active_log('receipt', 'In')}
		LEFT JOIN `tabStock Log` last_log ON last_log.carton_no = state.carton_no
			AND {latest_active_log('last_log')}
	"""
