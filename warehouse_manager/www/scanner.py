import frappe
import os


def get_context(context):
	app_path = frappe.get_app_path('warehouse_manager')
	html_path = os.path.join(app_path, 'www', 'scanner.html')
	if not os.path.exists(html_path):
		html_path = os.path.join(app_path, 'warehouse_manager', 'www', 'scanner.html')

	if os.path.exists(html_path):
		frappe.local.response.type = 'text/html'
		frappe.local.response.message = frappe.read_file(html_path)
	else:
		frappe.local.response.type = 'text/html'
		frappe.local.response.message = '<h1>Error: scanner.html not found</h1>'

	return context
