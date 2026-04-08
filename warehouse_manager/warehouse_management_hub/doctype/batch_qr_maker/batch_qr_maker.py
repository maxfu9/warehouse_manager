import frappe
import json
from io import BytesIO
import pyqrcode
from frappe.model.document import Document
from frappe import _

class BatchQRMaker(Document):
	def validate(self):
		if self.no_of_cartons <= 0:
			frappe.throw(_("Number of cartons must be greater than zero."))
		if self.qty_per_carton <= 0:
			frappe.throw(_("Quantity per carton must be greater than zero."))

	def before_submit(self):
		if self.status == "Draft" or not self.items:
			frappe.throw(_("Please generate cartons before submitting the batch."))

	def before_save(self):
		scanned = int(self.scanned_cartons or 0)
		dispatched = int(self.dispatched_cartons or 0)
		self.remaining_stock = max(scanned - dispatched, 0)

	def get_qr_svg(self, data):
		"""Generates an SVG string for the QR code."""
		if not data:
			return ""
		
		# Create QR code
		qr = pyqrcode.create(data, error='L')
		
		# Write to SVG stream
		stream = BytesIO()
		qr.svg(stream, scale=4, background="white", module_color="black")
		
		# Return clean SVG string
		return stream.getvalue().decode().replace("\n", "")

	@frappe.whitelist()
	def generate_cartons(self):
		if self.status != "Draft" or self.docstatus != 0:
			frappe.throw(_("Can only generate cartons for Draft batches"))
		
		if not self.no_of_cartons or self.no_of_cartons <= 0:
			frappe.throw(_("Please specify a valid number of cartons"))

		# Clear existing items if any to avoid duplicates on re-click
		self.items = []
			
		for i in range(self.no_of_cartons):
			carton = frappe.get_doc({
				"doctype": "Carton QR",
				"item": self.item,
				"qty": self.qty_per_carton,
				"uom": self.uom,
				"batch": self.name,
				"date": self.date
			})
			carton.insert(ignore_permissions=True)
			
			self.append("items", {
				"carton_no": carton.name,
				"status": "Draft",
				"qty": carton.qty,
				"uom": carton.uom
			})
			
		self.status = "Generated"
		self.scanned_cartons = 0
		self.dispatched_cartons = 0
		self.cancelled_cartons = 0
		self.remaining_stock = 0
		self.save(ignore_permissions=True)
		frappe.db.commit()
		return _("Generated {0} carton records").format(self.no_of_cartons)

	@frappe.whitelist()
	def close_batch(self):
		# Restriction: Stock Manager / System Manager
		if "Stock Manager" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
			frappe.throw(_("Only Stock Managers can close a batch"))
			
		if self.status != "Generated" or self.docstatus != 1:
			frappe.throw(_("A batch must be Submitted before it can be closed."))
			
		scanned = 0
		dispatched = 0
		cancelled = 0
		
		for item in self.items:
			# Check current status from the Carton QR record
			current_status = frappe.db.get_value("Carton QR", item.carton_no, "status")
			
			if not current_status or current_status == "Draft":
				# This carton was not scanned. Delete the QR record.
				frappe.delete_doc("Carton QR", item.carton_no, ignore_missing=True, ignore_permissions=True)
				item.status = "Cancelled"
				cancelled += 1
			elif current_status == "In Stock":
				item.status = "In Stock"
				scanned += 1
			elif current_status == "Dispatched":
				item.status = "Dispatched"
				scanned += 1
				dispatched += 1
				
		self.status = "Closed"
		self.scanned_cartons = scanned
		self.dispatched_cartons = dispatched
		self.cancelled_cartons = cancelled
		self.remaining_stock = max(scanned - dispatched, 0)
		self.save(ignore_permissions=True)
		frappe.db.commit()
		
		return _("Batch closed. Results: {0} In Stock, {1} Dispatched, {2} Cancelled.").format(scanned, dispatched, cancelled)

	def on_cancel(self):
		"""
		If a batch is cancelled, delete all generated Carton QR records
		that haven't been scanned yet.
		"""
		for item in self.items:
			if not frappe.db.exists("Stock Log", {"carton_no": item.carton_no}):
				frappe.delete_doc("Carton QR", item.carton_no, ignore_missing=True, ignore_permissions=True)
				item.status = "Cancelled"
			
		self.status = "Draft" # Reset status for amendment
