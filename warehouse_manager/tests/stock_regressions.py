"""Database regressions isolated in connection-local temporary tables.

Run using bench execute warehouse_manager.tests.stock_regressions.run.
No production rows are read or changed by the report tests below.
"""

import frappe
from uuid import uuid4

from warehouse_manager.warehouse_management_hub.report.current_inventory_detail.current_inventory_detail import get_data as detail
from warehouse_manager.warehouse_management_hub.report.europlast_inventory_summary.europlast_inventory_summary import get_data as inventory
from warehouse_manager.warehouse_management_hub.report.europlast_batch_summary.europlast_batch_summary import get_data as batches
from warehouse_manager.warehouse_management_hub.report.europlast_customer_summary.europlast_customer_summary import get_data as customers
from warehouse_manager.warehouse_management_hub.report.daily_movement_register.daily_movement_register import get_data as movements
from warehouse_manager.warehouse_management_hub.report.warehouse_exceptions.warehouse_exceptions import execute as exceptions


def run():
	tables = []
	try:
		for name, fields in (
			("Stock Log", "name varchar(140), carton_no varchar(140), item varchar(140), batch varchar(140), uom varchar(140), qty decimal(18,6), type varchar(10), scan_time datetime(6), creation datetime(6), movement_status varchar(30), customer varchar(140), supplier varchar(140), source_type varchar(30), delivery_note varchar(140), scan_session varchar(140)"),
			("Item", "name varchar(140), item_name varchar(140)"),
			("Carton QR", "name varchar(140), status varchar(30), item varchar(140), batch varchar(140), qty decimal(18,6), uom varchar(140), creation datetime(6)"),
			("Batch QR Maker", "name varchar(140), item varchar(140), creation datetime(6)"),
			("Batch QR Maker Item", "carton_no varchar(140), parent varchar(140), qty decimal(18,6), uom varchar(140), status varchar(30)"),
			("Warehouse Scan Session", "name varchar(140) PRIMARY KEY, creation datetime(6), modified datetime(6), modified_by varchar(140), owner varchar(140), docstatus int DEFAULT 0, idx int DEFAULT 0, session_key varchar(140) UNIQUE, mode varchar(10), status varchar(20), source_type varchar(30), supplier varchar(140), customer varchar(140), closed_at datetime(6)"),
		):
			frappe.db.sql(f"CREATE TEMPORARY TABLE `tab{name}` ({fields})")
			tables.append(name)
		frappe.db.sql("INSERT INTO `tabItem` VALUES ('TEST-ITEM', 'Regression Item')")
		frappe.db.sql("INSERT INTO `tabCarton QR` VALUES ('TEST-CARTON', 'In Stock', 'TEST-ITEM', 'TEST-BATCH', 10, NULL, '2026-10-01')")
		frappe.db.sql("INSERT INTO `tabBatch QR Maker` VALUES ('TEST-BATCH', 'TEST-ITEM', '2026-10-01')")
		frappe.db.sql("INSERT INTO `tabBatch QR Maker Item` VALUES ('TEST-CARTON', 'TEST-BATCH', 10, NULL, 'In Stock')")

		def scan(name, kind, timestamp, source=None):
			frappe.db.sql("""INSERT INTO `tabStock Log`
				(name, carton_no, item, batch, uom, qty, type, scan_time, creation, movement_status, customer, source_type)
				VALUES (%s, 'TEST-CARTON', 'TEST-ITEM', 'TEST-BATCH', NULL, 10, %s, %s, %s, 'Logged', 'Test Customer', %s)
			""", (name, kind, timestamp, timestamp, source))
			status = 'In Stock' if kind == 'In' else 'Dispatched'
			frappe.db.sql("UPDATE `tabCarton QR` SET status = %s", (status,))
			frappe.db.sql("UPDATE `tabBatch QR Maker Item` SET status = %s", (status,))

		def check(count):
			assert len(detail({})) == count, "Carton inventory state differs"
			assert sum(row.carton_count for row in inventory({})) == count, "Inventory count differs"
			assert sum(row.carton_count for row in batches({})) == count, "Batch count differs"

		scan('in', 'In', '2026-10-01 10:00:00', 'Production')
		check(1)
		scan('out', 'Out', '2026-10-02 10:00:00')
		check(0)
		scan('return', 'In', '2026-10-03 10:00:00', 'Return Stock')
		check(1)
		frappe.db.sql("UPDATE `tabStock Log` SET movement_status = 'Cancelled' WHERE name = 'return'")
		frappe.db.sql("UPDATE `tabCarton QR` SET status = 'Dispatched'")
		check(0)
		frappe.db.sql("UPDATE `tabStock Log` SET movement_status = 'Cancelled' WHERE name = 'out'")
		frappe.db.sql("UPDATE `tabCarton QR` SET status = 'In Stock'")
		check(1)
		assert len(movements({})) == 1, "Cancelled scans still affect movement totals"
		assert customers({}) == [], "Cancelled dispatch still affects customer totals"
		frappe.db.sql("UPDATE `tabCarton QR` SET status = 'Draft'")
		assert any(row.issue == 'Carton Status Mismatch' for row in exceptions({})[1])
		assert inventory({"item": "' OR 1=1 --"}) == [], "Filter is not parameterized"
		# Current status must win when a historical dispatch log is missing.
		frappe.db.sql("UPDATE `tabCarton QR` SET status = 'Dispatched'")
		frappe.db.sql("UPDATE `tabBatch QR Maker Item` SET status = 'Dispatched'")
		check(0)
		assert batches({})[0].dispatched_cartons == 1
		frappe.db.sql("DELETE FROM `tabCarton QR`")
		check(0)
		assert batches({})[0].dispatched_cartons == 1, 'Missing QR must retain the batch-row dispatch status'
		frappe.db.sql("INSERT INTO `tabBatch QR Maker Item` VALUES ('CANCELLED-LABEL', 'TEST-BATCH', 999, NULL, 'Cancelled')")
		assert batches({})[0].cancelled_cartons == 1
		check(0)
		# A cancelled label recreated without its batch must never become stock.
		frappe.db.sql("INSERT INTO `tabCarton QR` VALUES ('CANCELLED-LABEL', 'In Stock', 'OTHER-ITEM', NULL, 999, NULL, '2026-10-04')")
		check(0)
		assert batches({})[0].cancelled_cartons == 1
		assert len(batches({})) == 1, 'Recreated cancelled labels must not change the batch item'
		from warehouse_manager.scanner_sessions import lock_scan_session, get_scan_session, close_scan_session

		key = str(uuid4())
		assert lock_scan_session(key, 'In', 'Production') == key
		assert lock_scan_session(key, 'In', 'Production') == key
		frappe.db.sql("UPDATE `tabStock Log` SET scan_session = %s WHERE name = 'in'", (key,))
		assert get_scan_session(key)['cartons'] == 1
		try:
			lock_scan_session(key, 'In', 'Purchase', 'Different Supplier')
		except frappe.ValidationError:
			pass
		else:
			raise AssertionError("Session accepted a different lot source")
		close_scan_session(key)
		assert get_scan_session(key)['status'] == 'Closed'
		try:
			lock_scan_session(key, 'In', 'Production')
		except frappe.ValidationError:
			pass
		else:
			raise AssertionError("Closed session accepted another scan")
		return {"status": "passed", "checks": "Movement lifecycle, cancellation, NULL UOM, carton counts, exceptions, SQL filters, session persistence, source locking, session close"}
	finally:
		frappe.db.rollback()
		for name in reversed(tables):
			frappe.db.sql(f"DROP TEMPORARY TABLE IF EXISTS `tab{name}`")


def smoke():
	"""Read-only checks against the migrated site's real metadata and reports."""
	from frappe.utils import add_days, nowdate

	filters = {"from_date": add_days(nowdate(), -30), "to_date": nowdate()}
	counts = {label: len(fn(filters)) for label, fn in (
		("inventory", inventory), ("detail", detail), ("batches", batches),
		("customers", customers), ("movements", movements),
	)}
	counts["exceptions"] = len(exceptions({})[1])
	sidebar = frappe.get_doc("Workspace Sidebar", "Warehouse Hub")
	assert any(item.link_to == 'Warehouse Exceptions' for item in sidebar.items)
	assert any(item.link_to == 'Warehouse Scan Session' for item in sidebar.items)
	assert frappe.db.get_value('Dashboard Chart', 'Top 5 Products in Stock', 'chart_type') == 'Report'
	assert frappe.get_meta('Stock Log').has_field('scan_session')
	return {"status": "passed", "navigation": "Sessions and exceptions present", "report_rows": counts}


def check_dn_lock():
	"""Check the DN mutex with two connections; no documents are changed."""
	from threading import Event, Thread
	from queue import Queue
	from warehouse_manager.stock_queries import lock_delivery_note

	name = frappe.db.get_value('Delivery Note', {"docstatus": 2}, 'name')
	if not name:
		name = frappe.db.get_value('Delivery Note', {}, 'name')
	if not name:
		return {"status": "skipped", "reason": "No Delivery Note available"}
	site = frappe.local.site
	first_locked, release_first, second_locked = Event(), Event(), Event()
	errors = Queue()

	def worker(first):
		try:
			frappe.init(site=site)
			frappe.connect()
			lock_delivery_note(name)
			if first:
				first_locked.set()
				if not release_first.wait(10):
					raise AssertionError('Lock test release timed out')
			else:
				second_locked.set()
		except Exception as error:
			errors.put(str(error))
		finally:
			if frappe.db:
				frappe.db.rollback()
			frappe.destroy()

	first = Thread(target=worker, args=(True,), daemon=True)
	second = Thread(target=worker, args=(False,), daemon=True)
	first.start()
	try:
		assert first_locked.wait(5), 'First connection could not obtain the DN lock'
		second.start()
		assert not second_locked.wait(0.4), 'Second connection bypassed the DN lock'
	finally:
		release_first.set()
		first.join(10)
		if second.ident:
			second.join(10)
	assert errors.empty(), f'DN lock test failed: {list(errors.queue)}'
	assert second_locked.is_set(), 'Second connection did not continue after lock release'
	return {"status": "passed", "checks": "Second connection waits for the first DN transaction to release"}
