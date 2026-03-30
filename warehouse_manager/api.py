import frappe
import base64
import hashlib
import hmac
import json
import math
import os
from io import BytesIO
import pyqrcode
from frappe import _
from frappe.utils import cint, flt, now_datetime, time_diff_in_seconds
from hrms.hr.doctype.employee_checkin.employee_checkin import validate_active_employee

DEFAULT_SCAN_COOLDOWN_SECONDS = 60
DEFAULT_ALLOWED_RADIUS_METERS = 100
SIGNED_QR_PREFIX = "msqr1"
SETTINGS_DOCTYPE = "Manager Scanner Settings"


def get_warehouse_manager_settings():
	return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def validate_token(token):
	if not token:
		frappe.throw(_("Missing token"), frappe.PermissionError)

	manager_token = frappe.db.get_single_value(SETTINGS_DOCTYPE, "manager_token")
	if not manager_token or token != manager_token:
		frappe.throw(_("Invalid token"), frappe.PermissionError)


def get_scan_cooldown_seconds():
	settings = get_warehouse_manager_settings()
	return int(getattr(settings, "scan_cooldown_seconds", 0) or DEFAULT_SCAN_COOLDOWN_SECONDS)


def should_enforce_signed_qr_codes():
	settings = get_warehouse_manager_settings()
	return cint(getattr(settings, "enforce_signed_qr_codes", 0))


def is_location_validation_enabled():
	settings = get_warehouse_manager_settings()
	return cint(getattr(settings, "enable_location_validation", 0))


def get_qr_signing_secret():
	return frappe.local.conf.get("encryption_key") or frappe.local.conf.get("db_name") or "warehouse_manager"


def _urlsafe_b64encode(value):
	return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _urlsafe_b64decode(value):
	padding = "=" * (-len(value) % 4)
	return base64.urlsafe_b64decode((value + padding).encode())


def get_signed_qr_payload(employee_id):
	payload = {"employee": employee_id}
	payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
	payload_b64 = _urlsafe_b64encode(payload_json)
	signature = hmac.new(
		get_qr_signing_secret().encode(),
		payload_b64.encode(),
		hashlib.sha256,
	).hexdigest()
	return f"{SIGNED_QR_PREFIX}.{payload_b64}.{signature}"


def resolve_employee_id_from_scan(scan_data):
	if not scan_data:
		frappe.throw(_("Missing scan data"))

	scan_data = scan_data.strip()
	if scan_data.startswith(f"{SIGNED_QR_PREFIX}."):
		try:
			_prefix, payload_b64, signature = scan_data.split(".", 2)
		except ValueError:
			frappe.throw(_("Invalid signed QR format"))

		expected_signature = hmac.new(
			get_qr_signing_secret().encode(),
			payload_b64.encode(),
			hashlib.sha256,
		).hexdigest()
		if not hmac.compare_digest(signature, expected_signature):
			frappe.throw(_("Invalid or tampered QR code"))

		try:
			payload = json.loads(_urlsafe_b64decode(payload_b64).decode())
		except Exception:
			frappe.throw(_("Invalid QR payload"))

		employee_id = payload.get("employee")
		if not employee_id:
			frappe.throw(_("Employee information missing in QR code"))
		return employee_id

	if should_enforce_signed_qr_codes():
		frappe.throw(_("Only signed QR codes are allowed"))

	return scan_data


def get_distance_in_meters(latitude_1, longitude_1, latitude_2, longitude_2):
	earth_radius = 6371000
	lat1 = math.radians(latitude_1)
	lat2 = math.radians(latitude_2)
	lat_delta = math.radians(latitude_2 - latitude_1)
	lon_delta = math.radians(longitude_2 - longitude_1)

	a = (
		math.sin(lat_delta / 2) ** 2
		+ math.cos(lat1) * math.cos(lat2) * math.sin(lon_delta / 2) ** 2
	)
	c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
	return earth_radius * c


def validate_scan_location(latitude=None, longitude=None):
	if not is_location_validation_enabled():
		return

	settings = get_warehouse_manager_settings()
	raw_allowed_latitude = getattr(settings, "allowed_latitude", None)
	raw_allowed_longitude = getattr(settings, "allowed_longitude", None)
	allowed_radius_meters = cint(
		getattr(settings, "allowed_radius_meters", 0) or DEFAULT_ALLOWED_RADIUS_METERS
	)

	if raw_allowed_latitude in (None, "") or raw_allowed_longitude in (None, ""):
		frappe.throw(_("Scanner location validation is enabled but coordinates are not configured"))

	if latitude is None or longitude is None:
		frappe.throw(_("Location is required for this scanner"))

	allowed_latitude = flt(raw_allowed_latitude)
	allowed_longitude = flt(raw_allowed_longitude)
	latitude = flt(latitude)
	longitude = flt(longitude)
	distance = get_distance_in_meters(allowed_latitude, allowed_longitude, latitude, longitude)
	if distance > allowed_radius_meters:
		frappe.throw(
			_("You are {0}m away from the allowed scan location. Maximum allowed distance is {1}m.").format(
				int(distance), allowed_radius_meters
			)
		)


def get_next_log_type(employee):
	last_log_type = frappe.db.get_value(
		"Employee Checkin",
		{"employee": employee},
		"log_type",
		order_by="time desc, creation desc",
	)
	return "OUT" if last_log_type == "IN" else "IN"


def validate_scan_cooldown(employee):
	scan_cooldown_seconds = get_scan_cooldown_seconds()
	last_checkin = frappe.db.get_value(
		"Employee Checkin",
		{"employee": employee},
		["time", "log_type"],
		as_dict=True,
		order_by="time desc, creation desc",
	)
	if not last_checkin or not last_checkin.time:
		return

	elapsed_seconds = time_diff_in_seconds(now_datetime(), last_checkin.time)
	if elapsed_seconds >= scan_cooldown_seconds:
		return

	wait_seconds = int(scan_cooldown_seconds - max(elapsed_seconds, 0))
	last_action = _("checked in") if last_checkin.log_type == "IN" else _("checked out") if last_checkin.log_type == "OUT" else _("scanned")
	unit = _("second") if wait_seconds == 1 else _("seconds")
	frappe.throw(
		_("Already {0}. Please wait {1} {2} before scanning again.").format(
			last_action, wait_seconds, unit
		)
	)


def get_employee_scan_context(scan_data):
	employee_id = resolve_employee_id_from_scan(scan_data)
	employee = frappe.db.get_value(
		"Employee",
		{"name": employee_id},
		["name", "employee_name", "department", "designation", "image"],
		as_dict=True,
	)
	if not employee:
		frappe.throw(_("Employee {0} not found").format(employee_id))

	validate_active_employee(employee.name)
	next_log_type = get_next_log_type(employee.name)
	return employee, next_log_type


def get_employee_image_url(image_path, token):
	if not image_path:
		return None
	if image_path.startswith("/files/") or image_path.startswith("http://") or image_path.startswith("https://"):
		return image_path
	if image_path.startswith("/private/files/"):
		return f"/api/method/warehouse_manager.api.get_employee_image?token={token}&file_path={image_path}"
	return image_path


@frappe.whitelist(allow_guest=True)
def get_scanner_config(token=None):
	validate_token(token)
	return {
		"scan_cooldown_seconds": get_scan_cooldown_seconds(),
		"location_validation_enabled": bool(is_location_validation_enabled()),
	}


@frappe.whitelist(allow_guest=True)
def get_employee_preview(scan_data=None, employee_id=None, token=None):
	validate_token(token)
	scan_data = scan_data or employee_id
	if not scan_data:
		frappe.throw(_("Employee ID is required"))

	employee, next_log_type = get_employee_scan_context(scan_data)
	return {
		"employee_id": employee.name,
		"employee_name": employee.employee_name,
		"department": employee.department,
		"designation": employee.designation,
		"image": get_employee_image_url(employee.image, token),
		"next_log_type": next_log_type,
	}


@frappe.whitelist(allow_guest=True)
def get_employee_image(file_path=None, token=None):
	validate_token(token)
	if not file_path or not file_path.startswith("/private/files/"):
		frappe.throw(_("Invalid image path"))

	absolute_path = frappe.get_site_path(file_path.lstrip("/"))
	if not os.path.exists(absolute_path):
		frappe.throw(_("Employee image not found"))

	with open(absolute_path, "rb") as image_file:
		content = image_file.read()

	frappe.local.response.filename = os.path.basename(file_path)
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


@frappe.whitelist(allow_guest=True)
def get_recent_scans(token=None, limit=5):
	validate_token(token)
	limit = max(1, min(int(limit or 5), 20))

	return frappe.get_all(
		"Employee Checkin",
		fields=["employee", "employee_name", "log_type", "time"],
		order_by="time desc, creation desc",
		limit_page_length=limit,
	)


@frappe.whitelist(allow_guest=True)
def mark_attendance(scan_data=None, employee_id=None, log_type=None, token=None, latitude=None, longitude=None):
	"""
	Mark employee attendance via QR scan.
	Guest accessible if the token matches the Warehouse Management Hub Token.
	"""
	validate_token(token)

	scan_data = scan_data or employee_id
	if not scan_data:
		frappe.throw(_("Employee ID is required"))

	try:
		employee, resolved_log_type = get_employee_scan_context(scan_data)
		validate_scan_location(latitude=latitude, longitude=longitude)
		validate_scan_cooldown(employee.name)

		doc = frappe.new_doc("Employee Checkin")
		doc.employee = employee.name
		doc.employee_name = employee.employee_name
		doc.time = now_datetime()
		doc.log_type = resolved_log_type
		doc.latitude = flt(latitude) if latitude is not None else None
		doc.longitude = flt(longitude) if longitude is not None else None
		doc.insert(ignore_permissions=True)

		return {
			"status": "success",
			"log_type": resolved_log_type,
			"message": _("Attendance marked as {0} for {1}").format(
				resolved_log_type, doc.employee_name or doc.employee
			),
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Warehouse Management Hub Error"))
		return {
			"status": "error",
			"message": str(e)
		}

@frappe.whitelist(allow_guest=True)
def get_scanner_page(token=None):
	"""
	Returns the raw scanner HTML.
	Bypasses all layout/theme engine.
	"""
	try:
		validate_token(token)
	except Exception:
		return "<h1>Invalid token</h1>"
		
	app_path = frappe.get_app_path('warehouse_manager')
	# We'll use a version of scanner.html that is truly standalone
	html_path = os.path.join(app_path, 'www', 'scanner.html')
	if not os.path.exists(html_path):
		html_path = os.path.join(app_path, 'warehouse_manager', 'www', 'scanner.html')
	
	if not os.path.exists(html_path):
		return f"<h1>Error: scanner.html not found at {html_path}</h1>"
		
	html = frappe.read_file(html_path)
	
	# Inject CSRF token and Site Name for PWA context
	html = html.replace('{{ csrf_token }}', frappe.session.csrf_token or '')
	
	from werkzeug.wrappers import Response
	return Response(html, mimetype='text/html')

@frappe.whitelist()
def create_fallback_web_page():
	"""
	Create a Web Page that redirects to our raw API view.
	Also ensures default settings are initialized.
	"""
	# Initialize Settings
	if not frappe.db.exists(SETTINGS_DOCTYPE):
		doc = frappe.get_doc({
			"doctype": SETTINGS_DOCTYPE,
			"manager_token": "manager123",
			"scan_cooldown_seconds": 60,
			"allowed_radius_meters": 100
		})
		doc.insert(ignore_permissions=True)
		frappe.db.commit()

	name = frappe.db.get_value('Web Page', {'route': 'scanner'}, 'name')
	if name:
		doc = frappe.get_doc('Web Page', name)
	else:
		doc = frappe.new_doc('Web Page')
		doc.title = 'Warehouse Management Hub Redirect'
		doc.route = 'scanner'
		
	doc.published = 1
	doc.full_width = 1
	doc.show_title = 0
	# Redirect via JS
	redirect_html = """
	<script>
		const urlParams = new URLSearchParams(window.location.search);
		const token = urlParams.get('token') || 'manager123';
		window.location.href = '/api/method/warehouse_manager.api.get_scanner_page?token=' + token;
	</script>
	<p>Redirecting to scanner...</p>
	"""
	# Frappe stores HTML pages in `main_section_html` when `content_type` is `HTML`.
	doc.main_section = redirect_html
	doc.main_section_html = redirect_html
	doc.content_type = 'HTML'
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	
	return f"Web Page '{doc.name}' and Settings initialized."

def generate_qr_svg(data):
	"""Generate an inline SVG QR code string. Safe to call from Jinja print templates."""
	if not data:
		return ""
	qr = pyqrcode.create(str(data), error="L")
	stream = BytesIO()
	qr.svg(stream, scale=5, background="white", module_color="black")
	return stream.getvalue().decode()


@frappe.whitelist(allow_guest=True)
def get_meta_lists():
	return {
		"customers": frappe.get_all("Customer", pluck="name", order_by="name asc", limit=500),
		"suppliers": frappe.get_all("Supplier", pluck="name", order_by="name asc", limit=500)
	}


@frappe.whitelist(allow_guest=True)
def log_batch(cartons, passcode, mode=None, customer=None, source_type=None, supplier=None):
	# 1. Verify Passcode
	settings = frappe.get_single("Stock Log Settings")
	if passcode != settings.get_password("passcode"):
		frappe.throw(_("Invalid Passcode"), frappe.PermissionError)

	# 2. Parse Cartons
	if isinstance(cartons, str):
		cartons = json.loads(cartons)

	results = []
	logs_created = 0
	errors = []

	for doc in cartons:
		try:
			# Handle both new RAW ID (String) and Legacy JSON format
			if isinstance(doc, str):
				# It is a raw ID like CRT2026030043EU
				carton_no = doc
				record = frappe.get_doc("Carton QR", carton_no)
				item_code = record.item
				qty = record.qty
				uom = record.uom
				signature = None # Skip signature for raw internal scans
			else:
				# Legacy JSON format
				item_code = doc.get("item")
				carton_no = doc.get("carton_no")
				qty = doc.get("qty")
				uom = doc.get("uom")
				signature = doc.get("signature")

				# 3. Verify HMAC (only for JSON payload)
				message = f"{item_code}|{carton_no}|{qty}".encode()
				key = settings.get_password("hmac_secret").encode()
				expected_signature = hmac.new(key, message, hashlib.sha256).hexdigest()

				if signature != expected_signature:
					errors.append(f"Invalid signature for carton {carton_no}")
					continue

			# 4. Auto In/Out Logic
			previous_logs = frappe.get_all("Stock Log", filters={"carton_no": carton_no}, order_by="creation asc")
			
			log_type = "In"
			if len(previous_logs) == 1:
				log_type = "Out"
			elif len(previous_logs) >= 2:
				raise Exception(f"Carton {carton_no} already processed (In & Out)")

			# 4.1. Explicit Mode Check to avoid duplicate 'In' or 'Out'
			current_status = frappe.get_value("Carton QR", carton_no, "status")
			if mode == "In" and current_status == "In Stock":
				raise Exception(f"Carton {carton_no} is already IN STOCK")
			if mode == "Out" and current_status == "Dispatched":
				raise Exception(f"Carton {carton_no} is already DISPATCHED")

			# 5. Mode Enforcement
			if mode and mode != log_type:
				if mode == "In":
					raise Exception(f"Carton {carton_no} is already In-Stock. Switch to Outbound to dispatch.")
				else:
					raise Exception(f"Carton {carton_no} is NOT in-stock yet. Log Inbound first.")

			# 6. Fetch Batch from Carton QR record
			batch = frappe.db.get_value("Carton QR", {"carton_no": carton_no}, "batch")

			# 7. Create Log
			item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
			new_log = frappe.get_doc({
				"doctype": "Stock Log",
				"item": item_code,
				"carton_no": carton_no,
				"batch": batch,
				"type": log_type,
				"qty": qty,
				"uom": uom,
				"customer": customer if log_type == "Out" else None,
				"source_type": source_type if log_type == "In" else None,
				"supplier": supplier if (log_type == "In" and source_type == "Purchase") else None,
				"scan_time": frappe.utils.now_datetime()
			})
			new_log.insert(ignore_permissions=True)
			logs_created += 1
			results.append({
				"carton_no": carton_no, 
				"type": log_type, 
				"item": item_code,
				"item_name": item_name
			})

			# 8. Sync Status to Carton and Batch Item
			new_status = "In Stock" if log_type == "In" else "Dispatched"
			frappe.db.set_value("Carton QR", carton_no, "status", new_status)
			
			if batch:
				frappe.db.sql("""
					UPDATE `tabBatch QR Maker Item` 
					SET status = %s 
					WHERE parent = %s AND carton_no = %s
				""", (new_status, batch, carton_no))
				
				# Recalculate summary counts for the parent batch
				scanned = frappe.db.count("Batch QR Maker Item", {"parent": batch, "status": "In Stock"})
				dispatched = frappe.db.count("Batch QR Maker Item", {"parent": batch, "status": "Dispatched"})
				
				# Get total count to check for completion
				total_cartons = frappe.db.get_value("Batch QR Maker", batch, "no_of_cartons")
				
				update_values = {
					"scanned_cartons": scanned,
					"dispatched_cartons": dispatched
				}
				
				if dispatched >= total_cartons:
					update_values["status"] = "Closed"
				
				frappe.db.set_value("Batch QR Maker", batch, update_values, update_modified=False)

		except Exception as e:
			name_to_report = carton_no if 'carton_no' in locals() else str(doc)
			errors.append(f"Error processing {name_to_report}: {str(e)}")

	frappe.db.commit()

	return {
		"status": "success" if not errors else "partial_success",
		"logs_created": logs_created,
		"errors": errors,
		"results": results
	}

@frappe.whitelist()
def generate_qr_data(item_code, carton_no, qty):
	# Utility for admin to generate signed QR data
	settings = frappe.get_single("Stock Log Settings")
	message = f"{item_code}|{carton_no}|{qty}".encode()
	key = settings.get_password("hmac_secret").encode()
	signature = hmac.new(key, message, hashlib.sha256).hexdigest()
	
	return {
		"item": item_code,
		"carton_no": carton_no,
		"qty": qty,
		"signature": signature
	}

@frappe.whitelist(allow_guest=True)
def check_carton_statuses(cartons):
	"""Check if the provided cartons are for In or Out movement."""
	if isinstance(cartons, str):
		cartons = json.loads(cartons)

	statuses = []
	for c in cartons:
		carton_no = c.get("carton_no")
		log_count = frappe.db.count("Stock Log", filters={"carton_no": carton_no})
		
		# If 0 = New (In), If 1 = Previously Logged (Out), If 2+ = Done
		move_type = "In"
		if log_count == 1:
			move_type = "Out"
		elif log_count >= 2:
			move_type = "Done"
		
		statuses.append({
			"carton_no": carton_no,
			"move_type": move_type
		})
	
	return statuses
