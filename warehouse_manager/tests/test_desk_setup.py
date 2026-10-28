import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


class TestDeskSetup(unittest.TestCase):
	def setUp(self):
		self.records = {}
		self.frappe = SimpleNamespace(
			db=SimpleNamespace(exists=lambda dt, name: (dt, name) in self.records, table_exists=Mock(return_value=True)),
			cache=Mock(),
		)
		self.frappe.get_doc = self.get_doc
		self.frappe.rename_doc = self.rename_doc
		path = Path(__file__).resolve().parents[1] / "setup.py"
		spec = importlib.util.spec_from_file_location("desk_setup_under_test", path)
		self.setup = importlib.util.module_from_spec(spec)
		with patch.dict("sys.modules", {"frappe": self.frappe}):
			spec.loader.exec_module(self.setup)

	def get_doc(self, doctype, name=None):
		if name is not None:
			return self.records[(doctype, name)]
		doc = SimpleNamespace(**doctype)
		doc.update = lambda values: doc.__dict__.update(values)
		doc.get = lambda key: getattr(doc, key, None)
		def save(**kwargs):
			self.assertIn((doc.doctype, doc.name), self.records, 'New Desk records must be inserted')
		doc.save = save
		doc.insert = lambda **kwargs: self.records.update({(doc.doctype, doc.name): doc})
		return doc

	def rename_doc(self, doctype, old, new, force=False):
		self.assertTrue(force)
		doc = self.records.pop((doctype, old))
		doc.name = new
		self.records[(doctype, new)] = doc

	def test_v15_skips_v16_records(self):
		self.frappe.db.table_exists.return_value = False
		self.setup.setup_v16_desk()
		self.assertEqual(self.records, {})

	def test_navigation_is_connected_and_repeatable(self):
		self.setup.setup_v16_desk()
		self.setup.setup_v16_desk()
		self.assertEqual(len(self.records), 2)
		icon = self.records[("Desktop Icon", "Warehouse Hub")]
		sidebar = self.records[("Workspace Sidebar", icon.link_to)]
		self.assertEqual(icon.label, sidebar.name)
		self.assertEqual(icon.link_type, "Workspace Sidebar")
		self.assertEqual(sidebar.items[0]["link_to"], self.setup.WORKSPACE)
		self.assertEqual(len([i for i in sidebar.items if i["link_type"] == "Report" and i["type"] == "Link"]), 6)
		self.assertIn("Manager Scanner Settings", [i.get("link_to") for i in sidebar.items])
		asset = Path(__file__).resolve().parents[1] / "public" / icon.logo_url.split("/assets/warehouse_manager/")[1]
		self.assertTrue(asset.is_file())
		self.frappe.cache.delete_key.assert_any_call("bootinfo")

	def test_repairs_legacy_names_and_missing_logo(self):
		for doctype, field in (("Desktop Icon", "label"), ("Workspace Sidebar", "title")):
			doc = self.get_doc({"doctype": doctype, "name": self.setup.APP_TITLE, "app": self.setup.APP_NAME, "standard": 1, field: self.setup.DESK_TITLE})
			doc.insert()
		self.setup.setup_v16_desk()
		self.assertEqual(len(self.records), 2)
		icon = self.records[("Desktop Icon", self.setup.DESK_TITLE)]
		self.assertEqual(icon.logo_url, self.setup.APP_LOGO)
		self.assertEqual(icon.sidebar, self.setup.DESK_TITLE)

	def test_standard_exports_match_migration(self):
		self.setup.setup_v16_desk()
		root = Path(__file__).resolve().parents[1]
		for folder, doctype in (("desktop_icon", "Desktop Icon"), ("workspace_sidebar", "Workspace Sidebar")):
			definition = json.loads((root / folder / 'warehouse_hub.json').read_text())
			self.assertEqual(definition['name'], definition.get('label', definition.get('title')))
			self.assertEqual(definition['name'], self.setup.DESK_TITLE)
			if folder == 'workspace_sidebar':
				actual = self.records[(doctype, self.setup.DESK_TITLE)]
				self.assertEqual([(r['label'], r.get('link_to')) for r in definition['items']],
					[(r['label'], r.get('link_to')) for r in actual.items])


if __name__ == "__main__":
	unittest.main()
