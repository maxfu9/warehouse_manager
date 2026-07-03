import frappe


APP_NAME = "warehouse_manager"
APP_TITLE = "Warehouse Management Hub"
WORKSPACE = "EuroPlast Stock Log"
ROLES = ("System Manager", "Stock Manager")


def _save_standard_doc(doctype, name, values):
	values = dict(values)
	values.update({"doctype": doctype, "name": name})
	if frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
		doc.update(values)
	else:
		doc = frappe.get_doc(values)

	# These are app-owned standard Desk records created during migration, where
	# there is no interactive user permission context to apply.
	doc.save(ignore_permissions=True)
	return doc


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

	_save_standard_doc(
		"Desktop Icon",
		APP_TITLE,
		{
			"label": APP_TITLE,
			"standard": 1,
			"app": APP_NAME,
			"icon_type": "App",
			"link_type": "External",
			"link": "/desk/europlast-stock-log",
			"hidden": 0,
			"bg_color": "blue",
			"roles": [{"role": role} for role in ROLES],
		},
	)

	items = [
		_sidebar_item("Dashboard", "Workspace", WORKSPACE, icon="package"),
		_sidebar_item("Stock Scanner", "URL", icon="scan-line", url="/stock-scanner"),
		_sidebar_item("Operations", "DocType", type="Section Break", icon="clipboard-list", indent=1),
		_sidebar_item("Stock Log", "DocType", "Stock Log", child=1),
		_sidebar_item("Batch QR Maker", "DocType", "Batch QR Maker", child=1),
		_sidebar_item("Carton QR", "DocType", "Carton QR", child=1),
		_sidebar_item("Reports", "Report", type="Section Break", icon="file-text", indent=1),
		_sidebar_item("Current Inventory Detail", "Report", "Current Inventory Detail", child=1),
		_sidebar_item("Daily Movement Register", "Report", "Daily Movement Register", child=1),
		_sidebar_item("EuroPlast Inventory Summary", "Report", "EuroPlast Inventory Summary", child=1),
		_sidebar_item("EuroPlast Batch Summary", "Report", "EuroPlast Batch Summary", child=1),
		_sidebar_item("EuroPlast Customer Summary", "Report", "EuroPlast Customer Summary", child=1),
		_sidebar_item("Settings", "DocType", type="Section Break", icon="settings", indent=1),
		_sidebar_item("Stock Log Settings", "DocType", "Stock Log Settings", child=1),
	]

	_save_standard_doc(
		"Workspace Sidebar",
		APP_TITLE,
		{
			"title": APP_TITLE,
			"module": "Warehouse Management Hub",
			"app": APP_NAME,
			"standard": 1,
			"header_icon": "package",
			"items": items,
		},
	)
