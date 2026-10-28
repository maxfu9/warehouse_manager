import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class Values(dict):
	def __getattr__(self, field):
		return self.get(field)


class TestProductionLabels(TestCase):
	def setUp(self):
		def fail(message):
			raise ValueError(message)
		self.frappe = SimpleNamespace(db=Mock(), get_doc=Mock(), throw=fail, get_all=Mock())
		utils = SimpleNamespace(cint=lambda v: int(v or 0), flt=lambda v: float(v or 0))
		self.frappe._ = lambda text: text
		spec = importlib.util.spec_from_file_location('production_under_test', Path(__file__).resolve().parents[1] / 'production.py')
		self.production = importlib.util.module_from_spec(spec)
		with patch.dict('sys.modules', {'frappe': self.frappe, 'frappe.utils': utils}):
			spec.loader.exec_module(self.production)
		self.entry = Values(name='SE-TEST', work_order='WO-TEST', purpose='Manufacture', docstatus=1,
			warehouse_generate_qr_batch=1,
			posting_date='2026-10-29', fg_completed_qty=500,
			items=[Values(item_code='ITEM', is_finished_item=1, transfer_qty=3)], db_set=Mock())
		self.order = Values(name='WO-TEST', production_item='ITEM', warehouse_create_qr_batch=1,
			warehouse_qty_per_carton=144, warehouse_contents_uom='Piece')
		self.batch = Mock(name='batch')
		self.batch.name = 'BATCH-TEST'
		self.batch.flags = SimpleNamespace()
		self.frappe.get_doc.side_effect = lambda *args, **kwargs: self.order if args[0] == 'Work Order' else self.batch
		self.frappe.db.get_value.return_value = None

	def test_finished_rows_define_cartons_without_packing_conversion(self):
		self.entry['items'] += [Values(item_code='ITEM', is_finished_item=1, transfer_qty=2),
			Values(item_code='SCRAP', is_finished_item=0, is_scrap_item=1, transfer_qty=100)]
		self.assertEqual(self.production.produced_carton_count(self.entry, 'ITEM'), 5)
		self.assertEqual(self.production.create_manufacture_batch(self.entry), 'BATCH-TEST')
		data = self.frappe.get_doc.call_args_list[-1].args[0]
		self.assertEqual(data['no_of_cartons'], 5)
		self.assertEqual(data['qty_per_carton'], 144)
		self.assertEqual(data['date'], '2026-10-29')
		self.batch.generate_cartons.assert_called_once()
		self.batch.submit.assert_called_once()
		self.frappe.db.commit.assert_not_called()

	def test_fractional_and_zero_cartons_are_rejected(self):
		for qty in (0, -1, 2.5, 'NaN'):
			self.entry['items'][0]['transfer_qty'] = qty
			with self.assertRaises(ValueError):
				self.production.produced_carton_count(self.entry, 'ITEM')

	def test_retry_reuses_the_existing_batch(self):
		self.frappe.db.get_value.return_value = Values(name='EXISTING', docstatus=1)
		self.assertEqual(self.production.create_manufacture_batch(self.entry), 'EXISTING')
		self.frappe.get_doc.assert_not_called()
		self.entry.db_set.assert_called_with('warehouse_qr_batch', 'EXISTING', update_modified=False)

	def test_transfer_and_disabled_orders_create_no_batch(self):
		self.entry['purpose'] = 'Material Transfer for Manufacture'
		self.production.create_manufacture_batch(self.entry)
		self.frappe.get_doc.assert_not_called()
		self.entry['purpose'] = 'Manufacture'
		self.order['warehouse_create_qr_batch'] = 0
		with self.assertRaisesRegex(ValueError, 'Allow Carton Labels'):
			self.production.create_manufacture_batch(self.entry)
		self.batch.insert.assert_not_called()

	def test_unchecked_intermediate_entry_does_not_generate_labels(self):
		self.entry['warehouse_generate_qr_batch'] = 0
		self.entry['items'][0]['transfer_qty'] = 2.5
		self.assertIsNone(self.production.create_manufacture_batch(self.entry))
		self.frappe.db.sql.assert_not_called()
		self.frappe.get_doc.assert_not_called()

	def test_missing_checkbox_is_not_an_opt_in(self):
		del self.entry['warehouse_generate_qr_batch']
		self.assertIsNone(self.production.create_manufacture_batch(self.entry))
		self.frappe.get_doc.assert_not_called()

	def test_generation_failure_is_not_committed_or_linked(self):
		self.batch.generate_cartons.side_effect = ValueError('QR generation failed')
		with self.assertRaises(ValueError):
			self.production.create_manufacture_batch(self.entry)
		self.entry.db_set.assert_not_called()
		self.frappe.db.commit.assert_not_called()

	def test_consumed_labels_block_cancellation(self):
		self.frappe.get_all.return_value = ['BATCH-TEST']
		self.frappe.db.sql.side_effect = [[Values(name='CRT', status='In Stock')], []]
		self.batch.items = [Values(status='In Stock')]
		with self.assertRaisesRegex(ValueError, 'Reverse those movements'):
			self.production.validate_manufacture_cancellation(self.entry)

	def test_manual_generator_does_not_commit_inside_manufacturing(self):
		import ast
		file = Path(__file__).resolve().parents[1] / 'warehouse_management_hub/doctype/batch_qr_maker/batch_qr_maker.py'
		tree = ast.parse(file.read_text())
		method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'generate_cartons')
		self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'commit' for node in ast.walk(method)))
