import frappe
import json
import hmac
import hashlib
from frappe.model.document import Document
from warehouse_manager.api import generate_qr_svg

class CartonQR(Document):
	def validate(self):
		if not self.carton_no:
			self.carton_no = self.name

		# 1. Simplify the QR code to just the ID for instant hardware scanning
		self.signed_data = self.name
		
		# 2. Generate and set QR Display SVG
		self.qr_display = f"""
			<div class="text-center p-4" style="background: white; border: 1px solid #ddd; border-radius: 8px;">
				{generate_qr_svg(self.signed_data)}
				<div class="mt-2 text-muted small">{self.carton_no}</div>
			</div>
		"""

	def generate_qr_data(self):
		settings = frappe.get_single("Stock Log Settings")
		message = f"{self.item}|{self.carton_no}|{self.qty}".encode()
		
		# hmac_secret is a Password field, so we use get_password
		secret = settings.get_password("hmac_secret")
		if not secret:
			frappe.throw("HMAC Secret not set in Stock Log Settings")
			
		key = secret.encode()
		signature = hmac.new(key, message, hashlib.sha256).hexdigest()
		
		return {
			"item": self.item,
			"carton_no": self.carton_no,
			"qty": self.qty,
			"uom": self.uom,
			"signature": signature
		}
