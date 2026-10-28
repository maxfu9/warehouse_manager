"""Exercise production-label hooks against temporary document tables only."""

from uuid import uuid4

import frappe

from warehouse_manager.production import create_manufacture_batch, validate_manufacture_cancellation, cancel_manufacture_batch


def run():
	item = frappe.db.get_value('Item', {'disabled': 0, 'is_stock_item': 1}, ['name', 'stock_uom'], as_dict=True)
	if not item:
		return {'status': 'skipped', 'reason': 'A stock item is required'}
	tables = []
	prefix = 'QR-REGRESSION-' + uuid4().hex[:12]
	try:
		for name in ('Work Order', 'Stock Entry', 'Batch QR Maker', 'Batch QR Maker Item', 'Carton QR', 'Stock Log'):
			definition = frappe.db.sql(f'SHOW CREATE TABLE `tab{name}`')[0][1]
			frappe.db.sql(definition.replace('CREATE TABLE', 'CREATE TEMPORARY TABLE', 1))
			tables.append(name)
		order = prefix + '-WO'
		frappe.db.sql('''INSERT INTO `tabWork Order`
			(name, docstatus, production_item, warehouse_create_qr_batch, warehouse_qty_per_carton, warehouse_contents_uom)
			VALUES (%s, 1, %s, 1, 144, %s)''', (order, item.name, item.stock_uom))

		def manufacture(suffix, count, generate=True):
			name = prefix + suffix
			frappe.db.sql('''INSERT INTO `tabStock Entry` (name, docstatus, purpose, work_order, posting_date, warehouse_generate_qr_batch)
				VALUES (%s, 1, 'Manufacture', %s, '2026-10-29', %s)''', (name, order, int(generate)))
			entry = frappe._dict(name=name, purpose='Manufacture', work_order=order, docstatus=1,
				warehouse_generate_qr_batch=int(generate),
				posting_date='2026-10-29', items=[frappe._dict(item_code=item.name, is_finished_item=1, transfer_qty=count)])
			def set_link(field, value, **kwargs):
				frappe.db.set_value('Stock Entry', name, field, value, update_modified=False)
				entry[field] = value
			entry.db_set = set_link
			batch = create_manufacture_batch(entry)
			return entry, batch

		_, skipped = manufacture('-PART', 2.5, generate=False)
		assert skipped is None
		assert frappe.db.count('Batch QR Maker') == 0
		first, batch1 = manufacture('-SE1', 2)
		assert frappe.db.count('Carton QR', {'batch': batch1}) == 2
		assert frappe.db.count('Carton QR', {'batch': batch1, 'status': 'In Stock'}) == 0
		assert frappe.db.get_value('Batch QR Maker', batch1, 'docstatus') == 1
		assert frappe.db.get_value('Batch QR Maker', batch1, 'date').isoformat() == '2026-10-29'
		assert create_manufacture_batch(first) == batch1
		assert frappe.db.count('Batch QR Maker') == 1
		second, batch2 = manufacture('-SE2', 3)
		assert batch1 != batch2
		assert frappe.db.count('Carton QR') == 5
		assert frappe.db.count('Stock Log') == 0

		validate_manufacture_cancellation(first)
		frappe.db.set_value('Stock Entry', first.name, 'docstatus', 2, update_modified=False)
		cancel_manufacture_batch(first)
		assert frappe.db.get_value('Batch QR Maker', batch1, 'docstatus') == 2
		assert frappe.db.count('Carton QR', {'batch': batch1}) == 0
		assert frappe.db.count('Batch QR Maker Item', {'parent': batch1, 'status': 'Cancelled'}) == 2

		carton = frappe.db.get_value('Carton QR', {'batch': batch2}, 'name')
		frappe.db.set_value('Carton QR', carton, 'status', 'In Stock')
		try:
			validate_manufacture_cancellation(second)
		except frappe.ValidationError:
			pass
		else:
			raise AssertionError('Used cartons did not block cancellation')
		return {'status': 'passed', 'checks': 'Unchecked parts produce no labels; checked production 2 + 3 CTN, idempotency, source links, cancellation safeguards'}
	finally:
		# This also rolls back naming-series advances and document Version rows.
		frappe.db.rollback()
		for name in reversed(tables):
			frappe.db.sql(f'DROP TEMPORARY TABLE IF EXISTS `tab{name}`')


def smoke():
	order = frappe.get_meta('Work Order')
	assert order.get_field('warehouse_create_qr_batch').default == '1'
	assert order.get_field('warehouse_qty_per_carton')
	assert frappe.get_meta('Stock Entry').has_field('warehouse_qr_batch')
	assert frappe.get_meta('Stock Entry').get_field('warehouse_generate_qr_batch').default == '0'
	assert frappe.get_meta('Batch QR Maker').get_field('production_stock_entry').unique
	for doctype in ('Work Order', 'Stock Entry'):
		data = frappe.get_meta(doctype).get_dashboard_data()
		assert any('Batch QR Maker' in group['items'] for group in data.transactions)
	return {'status': 'passed', 'checks': 'Work Order label settings, Stock Entry batch link, unique manufacturing source, both dashboard connections'}
