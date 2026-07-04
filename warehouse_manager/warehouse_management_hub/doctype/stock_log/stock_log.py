import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


CANCELLED_STATUS = "Cancelled"


class StockLog(Document):
	def validate(self):
		self.normalize_values()
		self.validate_item()
		self.validate_quantity()
		self.validate_party_context()
		self.validate_delivery_note()
		self.validate_carton_sequence()

	def after_insert(self):
		self.sync_carton_status()

	def on_update(self):
		if self.carton_no:
			from warehouse_manager.api import sync_carton_status_from_latest_log

			sync_carton_status_from_latest_log(self.carton_no)

	def is_status_only_update(self):
		if self.is_new():
			return False
		fields_that_change_stock = ("type", "carton_no", "item", "qty", "delivery_note", "source_type")
		return self.has_value_changed("movement_status") and not any(
			self.has_value_changed(fieldname) for fieldname in fields_that_change_stock
		)

	def normalize_values(self):
		if self.type:
			self.type = self.type.strip().title()
		if self.type not in {"In", "Out"}:
			frappe.throw(_("Stock Log Type must be either In or Out"))

		if not self.scan_time:
			self.scan_time = now_datetime()
		if not self.movement_status:
			self.movement_status = "Logged"

		if self.carton_no:
			self.carton_no = self.carton_no.strip()

	def validate_item(self):
		if not frappe.db.exists("Item", self.item):
			frappe.throw(_("Item {0} does not exist").format(self.item))

		item = frappe.db.get_value("Item", self.item, ["disabled", "is_stock_item", "stock_uom"], as_dict=True)
		if item.disabled:
			frappe.throw(_("Item {0} is disabled").format(self.item))
		if not item.is_stock_item:
			frappe.throw(_("Item {0} is not a stock item").format(self.item))
		if not self.uom:
			self.uom = item.stock_uom

	def validate_quantity(self):
		if flt(self.qty) <= 0:
			frappe.throw(_("Quantity must be greater than zero"))

	def validate_party_context(self):
		if self.type == "Out" and self.source_type:
			self.source_type = None
		if self.type == "Out" and self.supplier:
			self.supplier = None

		if self.type == "In" and self.source_type == "Purchase" and not self.supplier:
			frappe.throw(_("Supplier is required for purchase receipts"))
		if self.type == "In" and self.source_type == "Return Stock" and not self.customer:
			frappe.throw(_("Customer is required for return stock receipts"))

	def validate_delivery_note(self):
		if self.type != "Out":
			self.delivery_note = None
			return

		if not self.delivery_note:
			return
		if not frappe.db.exists("Delivery Note", self.delivery_note):
			frappe.throw(_("Delivery Note {0} not found").format(self.delivery_note))
		if frappe.db.get_value("Delivery Note", self.delivery_note, "docstatus") == 2:
			frappe.throw(_("Delivery Note {0} is cancelled").format(self.delivery_note))

		target_qty = frappe.db.sql(
			"""
			SELECT SUM(qty)
			FROM `tabDelivery Note Item`
			WHERE parent = %(delivery_note)s AND item_code = %(item_code)s
			""",
			{"delivery_note": self.delivery_note, "item_code": self.item},
		)[0][0]
		if flt(target_qty) <= 0:
			frappe.throw(_("Item {0} is not part of Delivery Note {1}").format(self.item, self.delivery_note))

		current_scans = frappe.db.sql(
			"""
			SELECT COUNT(*)
			FROM `tabStock Log`
			WHERE delivery_note = %(delivery_note)s
				AND item = %(item)s
				AND type = 'Out'
				AND IFNULL(movement_status, 'Logged') != 'Cancelled'
				AND name != %(name)s
			""",
			{"delivery_note": self.delivery_note, "item": self.item, "name": self.name or ""},
		)[0][0]
		if current_scans >= flt(target_qty):
			frappe.throw(_("Target quantity reached for Item {0} on Delivery Note {1}").format(self.item, self.delivery_note))

		if not self.customer:
			self.customer = frappe.db.get_value("Delivery Note", self.delivery_note, "customer")

	def validate_carton_sequence(self):
		if not self.carton_no or self.movement_status == CANCELLED_STATUS:
			return
		if self.is_status_only_update():
			return

		carton = frappe.db.get_value(
			"Carton QR",
			self.carton_no,
			["name", "item", "status"],
			as_dict=True,
		)
		if not carton:
			is_batch_scan = frappe.db.exists("Batch QR Maker", self.carton_no) or frappe.db.exists("Carton QR", {"batch": self.carton_no})
			if self.type == "Out" and not is_batch_scan:
				frappe.throw(_("Carton {0} must be received before dispatch").format(self.carton_no))
			return

		if carton.item and carton.item != self.item:
			frappe.throw(_("Carton {0} belongs to Item {1}, not {2}").format(self.carton_no, carton.item, self.item))

		if self.type == "In":
			if carton.status == "In Stock":
				frappe.throw(_("Carton {0} is already In Stock").format(self.carton_no))
			if carton.status == "Dispatched" and self.source_type != "Return Stock":
				frappe.throw(_("Use Return Stock to receive dispatched carton {0}").format(self.carton_no))

		if self.type == "Out" and carton.status != "In Stock":
			frappe.throw(_("Carton {0} must be In Stock before dispatch. Current status: {1}").format(
				self.carton_no, carton.status or _("Unknown")
			))

		if self.type == "Out" and self.delivery_note:
			duplicate_scan = frappe.db.sql(
				"""
				SELECT name
				FROM `tabStock Log`
				WHERE carton_no = %(carton_no)s
					AND delivery_note = %(delivery_note)s
					AND type = 'Out'
					AND IFNULL(movement_status, 'Logged') != 'Cancelled'
					AND name != %(name)s
				LIMIT 1
				""",
				{"carton_no": self.carton_no, "delivery_note": self.delivery_note, "name": self.name or ""},
			)
			if duplicate_scan:
				frappe.throw(_("Carton {0} is already scanned against Delivery Note {1}").format(
					self.carton_no, self.delivery_note
				))

	def sync_carton_status(self):
		if not self.carton_no:
			return
		from warehouse_manager.api import sync_carton_status_from_latest_log

		sync_carton_status_from_latest_log(self.carton_no)
