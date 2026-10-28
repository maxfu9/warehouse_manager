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
		self.setup.prepare_v16_desk()
		self.setup.setup_v16_desk()
		self.assertEqual(self.records, {})

	def test_before_migrate_frees_fixture_labels_without_replacing_records(self):
		for doctype, field in (("Desktop Icon", "label"), ("Workspace Sidebar", "title")):
			doc = self.get_doc({"doctype": doctype, "name": self.setup.APP_TITLE,
				"app": self.setup.APP_NAME, "standard": 1, field: self.setup.DESK_TITLE})
			doc.insert()
		self.setup.prepare_v16_desk()
		self.setup.prepare_v16_desk()
		for doctype in ("Desktop Icon", "Workspace Sidebar"):
			self.assertNotIn((doctype, self.setup.APP_TITLE), self.records)
			self.assertIn((doctype, self.setup.DESK_TITLE), self.records)
		self.assertEqual(len(self.records), 2)
		self.frappe.cache.delete_key.assert_not_called()

	def test_preparation_preserves_other_apps_and_personal_records(self):
		for overrides in ({"app": "another_app"}, {"standard": 0}, {"for_user": "user@example.com"}):
			with self.subTest(overrides=overrides):
				self.records.clear()
				doc = self.get_doc({"doctype": "Workspace Sidebar", "name": self.setup.APP_TITLE,
					"app": self.setup.APP_NAME, "standard": 1, **overrides})
				doc.insert()
				self.setup.prepare_v16_desk()
				self.assertIn(("Workspace Sidebar", self.setup.APP_TITLE), self.records)

	def test_prepare_hook_runs_before_fixture_import(self):
		import ast
		hooks = Path(__file__).resolve().parents[1] / "hooks.py"
		assignments = {
			node.targets[0].id: ast.literal_eval(node.value)
			for node in ast.parse(hooks.read_text()).body
			if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
			and node.targets[0].id == "before_migrate"
		}
		self.assertIn("warehouse_manager.setup.prepare_v16_desk", assignments["before_migrate"])

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
