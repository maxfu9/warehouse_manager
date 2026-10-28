import frappe


APP_NAME = "warehouse_manager"
APP_TITLE = "Warehouse Management Hub"
DESK_TITLE = "Warehouse Hub"
WORKSPACE = "EuroPlast Stock Log"
ROLES = ("System Manager", "Stock Manager")
APP_LOGO = "/assets/warehouse_manager/icons/manager-scanner-icon.svg"


def sync_standard_navigation():
	# Existing sites can have newer DB timestamps than the shipped standard
	# charts/workspace. Explicitly reload app-owned definitions on upgrade.
	for name in ("top_5_products_in_stock", "customer_dispatch_share", "weekly_movement_trend"):
		frappe.reload_doc("warehouse_management_hub", "dashboard_chart", name, force=True)
	frappe.reload_doc("warehouse_management_hub", "workspace", "europlast_stock_log", force=True)
	frappe.reload_doc("warehouse_management_hub", "print_format", "batch_labels_a5", force=True)


def _save_standard_doc(doctype, name, values):
	values = dict(values)
	if frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": doctype, "name": name, **values})
		doc.insert(ignore_permissions=True)

	# These are app-owned standard Desk records created during migration, where
	# there is no interactive user permission context to apply.
	return doc


def _rename_legacy_desk_record(doctype):
	# The old setup used the module name as the document name, but a different
	# label/title. v16 resolves sidebars by the desktop icon's label.
	if frappe.db.exists(doctype, DESK_TITLE) or not frappe.db.exists(doctype, APP_TITLE):
		return
	doc = frappe.get_doc(doctype, APP_TITLE)
	if doc.app == APP_NAME and doc.standard and not doc.get("for_user"):
		frappe.rename_doc(doctype, APP_TITLE, DESK_TITLE, force=True)


def _sidebar_item(label, link_type, link_to=None, type="Link", icon=None, child=0, indent=0, url=None):
	row = {
		"type": type,
		"label": label,
		"link_type": link_type,
		"child": child,
		"indent": indent,
		"collapsible": 1,
		"keep_closed": 0,
		"show_arrow": 0,
	}
	if link_to:
		row["link_to"] = link_to
	if icon:
		row["icon"] = icon
	if url:
		row["url"] = url
	return row


def setup_v16_desk():
	for doctype in ("Desktop Icon", "Workspace Sidebar"):
		if not frappe.db.table_exists(doctype):
			return

	for doctype in ("Workspace Sidebar", "Desktop Icon"):
		_rename_legacy_desk_record(doctype)

	items = [
		_sidebar_item("Dashboard", "Workspace", WORKSPACE, icon="package"),
		_sidebar_item("Stock Scanner", "URL", icon="scan-line", url="/stock-scanner"),
		_sidebar_item("Operations", "DocType", type="Section Break", icon="clipboard-list", indent=1),
		_sidebar_item("Stock Log", "DocType", "Stock Log", child=1),
		_sidebar_item("Batch QR Maker", "DocType", "Batch QR Maker", child=1),
		_sidebar_item("Carton QR", "DocType", "Carton QR", child=1),
		_sidebar_item("Scan Sessions", "DocType", "Warehouse Scan Session", child=1),
		_sidebar_item("Reports", "Report", type="Section Break", icon="file-text", indent=1),
		_sidebar_item("Current Inventory Detail", "Report", "Current Inventory Detail", child=1),
		_sidebar_item("Daily Movement Register", "Report", "Daily Movement Register", child=1),
		_sidebar_item("EuroPlast Inventory Summary", "Report", "EuroPlast Inventory Summary", child=1),
		_sidebar_item("EuroPlast Batch Summary", "Report", "EuroPlast Batch Summary", child=1),
		_sidebar_item("EuroPlast Customer Summary", "Report", "EuroPlast Customer Summary", child=1),
		_sidebar_item("Warehouse Exceptions", "Report", "Warehouse Exceptions", child=1),
		_sidebar_item("Settings", "DocType", type="Section Break", icon="settings", indent=1),
		_sidebar_item("Stock Log Settings", "DocType", "Stock Log Settings", child=1),
		_sidebar_item("Manager Scanner Settings", "DocType", "Manager Scanner Settings", child=1),
	]

	_save_standard_doc(
		"Workspace Sidebar",
		DESK_TITLE,
		{
			"title": DESK_TITLE,
			"module": "Warehouse Management Hub",
			"app": APP_NAME,
			"standard": 1,
			"for_user": "",
			"header_icon": "package",
			"items": items,
		},
	)
	_save_standard_doc(
		"Desktop Icon",
		DESK_TITLE,
		{
			"label": DESK_TITLE,
			"standard": 1,
			"app": APP_NAME,
			"icon_type": "App",
			"link_type": "Workspace Sidebar",
			"link_to": DESK_TITLE,
			"sidebar": DESK_TITLE,
			"link": "",
			"logo_url": APP_LOGO,
			"parent_icon": "",
			"hidden": 0,
			"bg_color": "blue",
			"roles": [{"role": role} for role in ROLES],
		},
	)
	# Both are user-keyed hashes; invalidate every user's cached Desk navigation.
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")

