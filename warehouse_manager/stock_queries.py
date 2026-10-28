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


def latest_active_log(alias):
	return f"""{active_log(alias)} AND NOT EXISTS (
		SELECT 1 FROM `tabStock Log` newer
		WHERE newer.carton_no = {alias}.carton_no AND {active_log('newer')}
		AND (
			COALESCE(newer.scan_time, newer.creation) > COALESCE({alias}.scan_time, {alias}.creation)
			OR (COALESCE(newer.scan_time, newer.creation) = COALESCE({alias}.scan_time, {alias}.creation)
				AND (newer.creation > {alias}.creation
					OR (newer.creation = {alias}.creation AND newer.name > {alias}.name)))
		)
	)"""
