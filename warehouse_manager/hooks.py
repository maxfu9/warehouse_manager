app_name = "warehouse_manager"
app_title = "Warehouse Hub"
app_publisher = "Antigravity"
app_description = "Manager QR Scanner"
app_email = "antigravity@example.com"
app_license = "mit"

from warehouse_manager import _apply_workspace_compatibility_patch

_apply_workspace_compatibility_patch()

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "warehouse_manager",
		"logo": "/assets/warehouse_manager/icons/manager-scanner-icon.svg",
		"title": "Warehouse Hub",
		"route": "/desk/europlast-stock-log",
		"has_permission": "warehouse_manager.api.has_app_permission"
	}
]

# Desk records are created by setup_v16_desk, which skips sites without the
# v16 Sidebar schema. Do not export v16-only records as cross-version fixtures.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/warehouse_manager/css/warehouse_manager.css"
# app_include_js = "/assets/warehouse_manager/js/warehouse_manager.js"

# include js, css files in header of web template
# web_include_css = "/assets/warehouse_manager/css/warehouse_manager.css"
# web_include_js = "/assets/warehouse_manager/js/warehouse_manager.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "warehouse_manager/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Manager Scanner Settings": "public/js/manager_scanner_settings.js",
	"Delivery Note": "public/js/delivery_note.js",
	"Stock Log": "public/js/stock_log.js",
	"Work Order": "public/js/production_labels.js",
	"Stock Entry": "public/js/production_labels.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "warehouse_manager/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

website_route_rules = [
    {"from_route": "/stock-scanner", "to_route": "scanner"},
    {"from_route": "/scanner", "to_route": "warehouse_manager.api.get_scanner_page"},
]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	"methods": [
		"warehouse_manager.utils",
		"warehouse_manager.api.generate_qr_svg",
		"warehouse_manager.api.generate_qr_png_data_uri"
	],
}

# Installation
# ------------

# before_install = "warehouse_manager.install.before_install"
after_install = ["warehouse_manager.production.setup_production_fields", "warehouse_manager.setup.sync_standard_navigation", "warehouse_manager.setup.setup_v16_desk"]

before_migrate = ["warehouse_manager.setup.prepare_v16_desk"]
after_migrate = ["warehouse_manager.production.setup_production_fields", "warehouse_manager.setup.sync_standard_navigation", "warehouse_manager.setup.setup_v16_desk"]

# Uninstallation
# ------------

# before_uninstall = "warehouse_manager.uninstall.before_uninstall"
# after_uninstall = "warehouse_manager.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "warehouse_manager.utils.before_app_install"
# after_app_install = "warehouse_manager.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "warehouse_manager.utils.before_app_uninstall"
# after_app_uninstall = "warehouse_manager.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "warehouse_manager.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Stock Entry": {
		"on_submit": "warehouse_manager.production.create_manufacture_batch",
		"before_cancel": "warehouse_manager.production.validate_manufacture_cancellation",
		"on_cancel": "warehouse_manager.production.cancel_manufacture_batch",
	}
}

override_doctype_dashboards = {
	"Work Order": "warehouse_manager.production.work_order_dashboard",
	"Stock Entry": "warehouse_manager.production.stock_entry_dashboard",
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"warehouse_manager.tasks.all"
# 	],
# 	"daily": [
# 		"warehouse_manager.tasks.daily"
# 	],
# 	"hourly": [
# 		"warehouse_manager.tasks.hourly"
# 	],
# 	"weekly": [
# 		"warehouse_manager.tasks.weekly"
# 	],
# 	"monthly": [
# 		"warehouse_manager.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "warehouse_manager.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "warehouse_manager.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "warehouse_manager.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["warehouse_manager.utils.before_request"]
# after_request = ["warehouse_manager.utils.after_request"]

# Job Events
# ----------
# before_job = ["warehouse_manager.utils.before_job"]
# after_job = ["warehouse_manager.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"warehouse_manager.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
