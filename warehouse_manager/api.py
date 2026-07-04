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
from urllib.parse import unquote
import re

DEFAULT_SCAN_COOLDOWN_SECONDS = 60
DEFAULT_ALLOWED_RADIUS_METERS = 100
SIGNED_QR_PREFIX = "msqr1"
SETTINGS_DOCTYPE = "Stock Log Settings"


def get_warehouse_manager_settings():
	return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def validate_token(token=None):
	if not token:
		if frappe.session.user != "Guest":
			return True
		frappe.throw(_("Missing scanner passcode"), frappe.PermissionError)

	try:
		token = str(token).strip()
		settings = get_warehouse_manager_settings()
		stored_passcode = (settings.get_password("passcode") or "").strip()
		
		if not stored_passcode:
			frappe.throw(_("Passcode not set in {0}").format(SETTINGS_DOCTYPE), frappe.PermissionError)
			
		if token != stored_passcode:
			frappe.throw(_("Invalid Passcode. Please check {0} in ERPNext.").format(SETTINGS_DOCTYPE), frappe.PermissionError)
	except frappe.ValidationError as e:
		raise e
	except Exception as e:
		if "Invalid Passcode" in str(e) or "not set" in str(e):
			raise e
		frappe.log_error(frappe.get_traceback(), _("Warehouse Scanner Security Error"))
		frappe.throw(_("Unable to validate scanner passcode"), frappe.PermissionError)


def get_public_error_message(error, fallback=None):
	"""Return scanner-safe messages without exposing unexpected internals."""
	if isinstance(error, (frappe.ValidationError, frappe.PermissionError)):
		return frappe.as_unicode(error)
	return fallback or _("Unable to process scanner request. Please try again or contact support.")


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

	private_files_path = os.path.abspath(frappe.get_site_path("private", "files"))
	absolute_path = os.path.abspath(frappe.get_site_path(file_path.lstrip("/")))
	if os.path.commonpath([private_files_path, absolute_path]) != private_files_path:
		frappe.throw(_("Invalid image path"))

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
		frappe.db.commit()

		return {
			"status": "success",
			"log_type": resolved_log_type,
			"employee_name": doc.employee_name or doc.employee,
			"message": _("Attendance marked as {0} for {1}").format(
				resolved_log_type, doc.employee_name or doc.employee
			),
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Warehouse Management Hub Error"))
		return {
			"status": "error",
			"message": get_public_error_message(e)
		}


@frappe.whitelist(allow_guest=True)
def get_scanner_page(token=None):
	app_path = frappe.get_app_path('warehouse_manager')
	html_path = os.path.join(app_path, 'www', 'scanner.html')
	if not os.path.exists(html_path):
		html_path = os.path.join(app_path, 'warehouse_manager', 'www', 'scanner.html')
	
	if not os.path.exists(html_path):
		return f"<h1>Error: scanner.html not found</h1>"
		
	html = frappe.read_file(html_path)
	html = html.replace('{{ csrf_token }}', frappe.session.csrf_token or '')
	from werkzeug.wrappers import Response
	return Response(html, mimetype='text/html')


@frappe.whitelist(allow_guest=True)
def get_meta_lists(token=None):
	validate_token(token)
	return {
		"customers": frappe.get_all("Customer", pluck="name", order_by="name asc", limit=500),
		"suppliers": frappe.get_all("Supplier", pluck="name", order_by="name asc", limit=500),
		"items": frappe.get_all("Item", filters={"disabled": 0, "is_stock_item": 1}, fields=["name", "item_name"], order_by="name asc", limit=1000)
	}


@frappe.whitelist(allow_guest=True)
def get_delivery_note_details(token, dn_id):
	try:
		if not token or token == "null" or token == "undefined":
			frappe.throw(_("Scanner passcode is required. Please log in again."), frappe.PermissionError)
			
		validate_token(token)
		dn_id = unquote((dn_id or "").strip())
		
		# Extract DN ID from URL if necessary
		if "/" in dn_id:
			match = re.search(r"(?:Delivery Note|delivery-note)/([^?/\s]+)", dn_id, re.IGNORECASE)
			if match:
				dn_id = match.group(1)

		if not frappe.db.exists("Delivery Note", dn_id):
			frappe.throw(_("Delivery Note {0} not found in database").format(dn_id))

		dn = frappe.get_doc("Delivery Note", dn_id)
		if dn.docstatus == 2:
			frappe.throw(_("Delivery Note {0} is cancelled").format(dn_id))

		items = {}
		for item in dn.items:
			if item.item_code not in items:
				items[item.item_code] = {"item_code": item.item_code, "qty": 0, "item_name": item.item_name, "scanned_qty": 0}
			items[item.item_code]["qty"] += flt(item.qty)

		# Use Stock Log (actual scanner logs) to find already processed items
		processed_logs = frappe.db.sql(
			"""
			SELECT item, qty
			FROM `tabStock Log`
			WHERE delivery_note = %(delivery_note)s
				AND type = 'Out'
				AND IFNULL(movement_status, 'Logged') != 'Cancelled'
			""",
			{"delivery_note": dn_id},
			as_dict=True,
		)
		for log in processed_logs:
			if log.item in items:
				# COUNT records (scans) instead of summing qty to match carton workflow
				items[log.item]["scanned_qty"] += 1

		# SMART VALIDATION: Check if DN is already fully scanned (all items met target scan count)
		if items:
			all_done = True
			for code, it in items.items():
				if flt(it["scanned_qty"]) < flt(it["qty"]):
					all_done = False
					break
			
			if all_done:
				frappe.throw(_("ALREADY DISPATCHED: Delivery Note {0} has already been fully scanned.").format(dn_id))

		return {
			"dn_id": dn_id,
			"customer": dn.customer,
			"items": items
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Scanner Delivery Note Details Error")
		return {
			"status": "error",
			"message": get_public_error_message(e)
		}


def normalize_delivery_note_id(delivery_note):
	clean_dn = unquote((delivery_note or "").strip())
	if "/" in clean_dn:
		match = re.search(r"(?:Delivery Note|delivery-note)/([^?/\s]+)", clean_dn, re.IGNORECASE)
		if match:
			clean_dn = match.group(1)
	return clean_dn


def get_locked_carton(carton_no):
	if not carton_no:
		return None

	rows = frappe.db.sql(
		"""
		SELECT name, item, qty, uom, status, batch
		FROM `tabCarton QR`
		WHERE name = %(carton_no)s
		FOR UPDATE
		""",
		{"carton_no": carton_no},
		as_dict=True,
	)
	return rows[0] if rows else None


def get_delivery_note_item_targets(delivery_note):
	rows = frappe.db.sql(
		"""
		SELECT item_code, SUM(qty) AS qty
		FROM `tabDelivery Note Item`
		WHERE parent = %(delivery_note)s
		GROUP BY item_code
		""",
		{"delivery_note": delivery_note},
		as_dict=True,
	)
	return {
		(row.item_code or "").strip().upper(): flt(row.qty)
		for row in rows
		if row.item_code
	}


def get_active_out_scan_count(delivery_note, item_code):
	if not delivery_note or not item_code:
		return 0

	return frappe.db.sql(
		"""
		SELECT COUNT(*)
		FROM `tabStock Log`
		WHERE delivery_note = %(delivery_note)s
			AND item = %(item_code)s
			AND type = 'Out'
			AND IFNULL(movement_status, 'Logged') != 'Cancelled'
		""",
		{"delivery_note": delivery_note, "item_code": item_code},
	)[0][0]


def get_stock_status_for_log_type(log_type):
	return "In Stock" if log_type == "In" else "Dispatched"


def sync_carton_status_from_latest_log(carton_no):
	"""Rebuild Carton QR and batch status from non-cancelled Stock Logs."""
	carton_no = (carton_no or "").strip()
	if not carton_no:
		return None

	latest_log = frappe.db.sql(
		"""
		SELECT type
		FROM `tabStock Log`
		WHERE carton_no = %(carton_no)s
			AND IFNULL(movement_status, 'Logged') != 'Cancelled'
		ORDER BY IFNULL(scan_time, creation) DESC, creation DESC
		LIMIT 1
		""",
		{"carton_no": carton_no},
		as_dict=True,
	)
	new_status = get_stock_status_for_log_type(latest_log[0].type) if latest_log else "Draft"

	if frappe.db.exists("Carton QR", carton_no):
		frappe.db.set_value("Carton QR", carton_no, "status", new_status, update_modified=True)
		batch_id = frappe.db.get_value("Carton QR", carton_no, "batch")
		if batch_id:
			update_batch_maker_status(batch_id, carton_no, new_status)

	if frappe.db.exists("Batch QR Maker", carton_no) or frappe.db.exists("Carton QR", {"batch": carton_no}):
		frappe.db.set_value("Carton QR", {"batch": carton_no}, "status", new_status, update_modified=True)
		if frappe.db.exists("Batch QR Maker", carton_no):
			frappe.db.sql(
				"""
				UPDATE `tabBatch QR Maker Item`
				SET status = %(status)s
				WHERE parent = %(batch_id)s
				""",
				{"status": new_status, "batch_id": carton_no},
			)
			recalculate_batch_maker_counts(carton_no)

	return new_status


def require_stock_manager():
	roles = set(frappe.get_roles())
	if not roles.intersection({"System Manager", "Stock Manager"}):
		frappe.throw(_("Only Stock Managers can perform this action"), frappe.PermissionError)


def get_stock_log_for_action(stock_log):
	if not stock_log:
		frappe.throw(_("Stock Log is required"))
	doc = frappe.get_doc("Stock Log", stock_log)
	doc.check_permission("write")
	return doc


def validate_stock_log_reopen(doc):
	if not doc.carton_no:
		return

	carton = frappe.db.get_value("Carton QR", doc.carton_no, ["name", "status"], as_dict=True)
	if carton:
		if doc.type == "In" and carton.status == "In Stock":
			frappe.throw(_("Carton {0} is already In Stock").format(doc.carton_no))
		if doc.type == "In" and carton.status == "Dispatched" and doc.source_type != "Return Stock":
			frappe.throw(_("Use Return Stock to receive dispatched carton {0}").format(doc.carton_no))
		if doc.type == "Out" and carton.status != "In Stock":
			frappe.throw(_("Carton {0} must be In Stock before reopening this dispatch").format(doc.carton_no))

	if doc.type == "Out" and doc.delivery_note:
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
			{"carton_no": doc.carton_no, "delivery_note": doc.delivery_note, "name": doc.name},
		)
		if duplicate_scan:
			frappe.throw(_("Carton {0} is already active against Delivery Note {1}").format(
				doc.carton_no, doc.delivery_note
			))


def update_stock_log_movement_status(stock_log, movement_status, note=None):
	require_stock_manager()
	doc = get_stock_log_for_action(stock_log)
	if doc.posted_stock_entry and movement_status == "Cancelled":
		frappe.throw(_("Cancel the linked Stock Entry {0} before cancelling this Stock Log").format(doc.posted_stock_entry))

	current_status = doc.movement_status or "Logged"
	if current_status == movement_status:
		return {"status": "success", "movement_status": current_status}

	if movement_status == "Verified" and current_status != "Logged":
		frappe.throw(_("Only Logged stock movements can be verified"))
	if movement_status == "Logged" and current_status != "Cancelled":
		frappe.throw(_("Only cancelled stock movements can be reopened"))
	if movement_status == "Logged":
		validate_stock_log_reopen(doc)

	doc.movement_status = movement_status
	if note:
		doc.validation_message = note
	doc.save()
	new_carton_status = sync_carton_status_from_latest_log(doc.carton_no)
	frappe.db.commit()
	return {
		"status": "success",
		"movement_status": doc.movement_status,
		"carton_status": new_carton_status,
	}


@frappe.whitelist()
def verify_stock_log(stock_log, note=None):
	return update_stock_log_movement_status(stock_log, "Verified", note)


@frappe.whitelist()
def cancel_stock_log(stock_log, reason=None):
	return update_stock_log_movement_status(stock_log, "Cancelled", reason)


@frappe.whitelist()
def reopen_stock_log(stock_log):
	return update_stock_log_movement_status(stock_log, "Logged")


@frappe.whitelist(allow_guest=True)
def handle_stock_log(**kwargs):
	"""Create a Stock Log from scanner input with DN, carton, and duplicate safeguards."""
	try:
		params = frappe._dict(kwargs)
		if not params:
			params = frappe.form_dict

		manager_token = params.get("manager_token")
		scan_data = params.get("scan_data")
		log_type = params.get("log_type")
		delivery_note = params.get("delivery_note")
		customer = params.get("customer")
		item_code = params.get("item_code")
		source_type = params.get("source_type")
		supplier = params.get("supplier")
		clean_dn = None
		qty_from_scan = None

		validate_token(manager_token)

		if not scan_data:
			frappe.throw(_("Scan data missing"))

		carton_no = scan_data
		if "|" in scan_data:
			parts = scan_data.split("|")
			if len(parts) >= 3:
				item_code, carton_no, qty_from_scan = parts[0], parts[1], flt(parts[2])

		carton_no = (carton_no or "").strip()
		c = get_locked_carton(carton_no)
		if c:
			item_code = c.item if not item_code else item_code
			qty = flt(c.qty)
			uom = c.uom or frappe.db.get_value("Item", c.item, "stock_uom")
		else:
			qty = qty_from_scan or 1
			uom = frappe.db.get_value("Item", item_code, "stock_uom") if item_code else None

		curr_item = str(item_code or "").strip().upper()
		if not curr_item:
			if not params.get("item_code"):
				return {
					"status": "error",
					"message": _("New Carton {0}: Item code unknown. Please select a Product.").format(carton_no),
					"needs_item_selection": True,
				}

		if delivery_note:
			clean_dn = normalize_delivery_note_id(delivery_note)
			if not frappe.db.exists("Delivery Note", clean_dn):
				frappe.throw(_("Delivery Note {0} not found in database").format(clean_dn))
			if frappe.db.get_value("Delivery Note", clean_dn, "docstatus") == 2:
				frappe.throw(_("Delivery Note {0} is cancelled").format(clean_dn))

			dn_items = get_delivery_note_item_targets(clean_dn)
			if curr_item not in dn_items:
				frappe.throw(_("WRONG PRODUCT: Item {0} not matched with DN {1}").format(curr_item, clean_dn))

			target_qty = dn_items[curr_item]
			current_scans = get_active_out_scan_count(clean_dn, item_code)
			if current_scans >= flt(target_qty):
				frappe.throw(_("TARGET REACHED: Item {0} is already fully picked ({1}/{1} cartons).").format(curr_item, int(target_qty)))

		current_status = (c.status if c else None) or "New"
		if log_type == "In" and current_status == "In Stock":
			frappe.throw(_("Sequence Error: Carton {0} is currently {1}. Cannot scan 'In' again.").format(carton_no, current_status))
		if log_type == "In" and current_status == "Dispatched" and source_type != "Return Stock":
			frappe.throw(_("Sequence Error: Carton {0} is dispatched. Use Return Stock to receive it back.").format(carton_no))

		if log_type == "Out" and current_status != "In Stock":
			if current_status == "Dispatched":
				frappe.throw(_("Sequence Error: Carton {0} has already been Dispatched.").format(carton_no))
			frappe.throw(_("Sequence Error: Carton {0} must be marked as 'In Stock' before it can be Dispatched (Current: {1}).").format(carton_no, current_status))

		final_type = log_type or ("Out" if (current_status == "In Stock" or delivery_note) else "In")
		if delivery_note:
			final_type = "Out"

		if final_type == "Out" and clean_dn:
			duplicate_scan = frappe.db.sql(
				"""
				SELECT name
				FROM `tabStock Log`
				WHERE carton_no = %(carton_no)s
					AND delivery_note = %(delivery_note)s
					AND type = 'Out'
					AND IFNULL(movement_status, 'Logged') != 'Cancelled'
				LIMIT 1
				""",
				{"carton_no": carton_no, "delivery_note": clean_dn},
			)
			if duplicate_scan:
				frappe.throw(_("DUPLICATE SCAN: Carton {0} is already scanned against Delivery Note {1}.").format(carton_no, clean_dn))

		item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
		batch = c.batch if c else frappe.db.get_value("Carton QR", carton_no, "batch")

		doc = frappe.new_doc("Stock Log")
		doc.update({
			"item": item_code,
			"carton_no": carton_no,
			"batch": batch,
			"type": final_type,
			"qty": qty,
			"uom": uom,
			"delivery_note": clean_dn if final_type == "Out" else None,
			"customer": customer if (final_type == "Out" or (final_type == "In" and source_type == "Return Stock")) else None,
			"source_type": source_type if final_type == "In" else None,
			"supplier": supplier if (final_type == "In" and source_type == "Purchase") else None,
			"movement_status": "Logged",
			"scan_time": now_datetime(),
		})
		# Scanner token validation is the trust boundary for guest stock scans;
		# stock operators do not need Desk create permission for each scan row.
		doc.insert(ignore_permissions=True)

		new_status = get_stock_status_for_log_type(final_type)

		if not c and not frappe.db.exists("Carton QR", carton_no) and final_type == "In":
			new_c = frappe.new_doc("Carton QR")
			new_c.update({
				"name": carton_no,
				"item": item_code,
				"carton_no": carton_no,
				"status": new_status,
				"qty": qty,
				"uom": uom,
				"creation_type": "Scanner",
			})
			# New inbound cartons are created by a validated scanner session.
			new_c.insert(ignore_permissions=True)

		new_status = sync_carton_status_from_latest_log(carton_no) or new_status

		return {
			"status": "success",
			"item": item_code or carton_no,
			"item_name": item_name or item_code or carton_no,
			"qty": qty,
			"log_type": final_type,
			"current_status": new_status,
			"carton_no": carton_no,
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), _("Stock Log Action Error"))
		return {
			"status": "error",
			"message": get_public_error_message(e),
		}


@frappe.whitelist(allow_guest=True)
def log_batch():
	params = frappe.form_dict
	cartons = params.get("cartons")
	if isinstance(cartons, str): cartons = json.loads(cartons)
	
	passcode = params.get("passcode")
	mode = params.get("mode")
	customer = params.get("customer")
	delivery_note = params.get("delivery_note")
	
	try:
		frappe.db.begin()
		last_res = None
		last_scan = None
		if not cartons:
			frappe.throw(_("No cartons were provided for batch scan"))

		for scan in (cartons or []):
			last_scan = scan
			last_res = handle_stock_log(
				scan_data=scan.get('scan_data') if isinstance(scan, dict) else scan,
				log_type=mode,
				manager_token=passcode,
				customer=customer,
				delivery_note=delivery_note
			)
			# If handle_stock_log returns an error status (instead of throwing)
			if isinstance(last_res, dict) and last_res.get("status") == "error":
				frappe.db.rollback()
				return last_res

		frappe.db.commit()
		return {
			"status": "success", 
			"message": _("Logged item: {0}").format(last_res.get("item_name") if last_res else ""),
			"item_name": (last_res.get("item_name") if last_res else None) or (last_res.get("item") if last_res else None),
			"item": (last_res.get("item") if last_res else None),
			"qty": last_res.get("qty") if last_res else 0,
			"log_type": last_res.get("log_type") if last_res else mode,
			"carton_no": (last_res.get("carton_no") if last_res else None) or (last_scan.get('scan_data') if isinstance(last_scan, dict) else last_scan)
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), _("Batch Scan Error"))
		return {"status": "error", "message": get_public_error_message(e)}


@frappe.whitelist(allow_guest=True)
def revert_stock_log(token, carton_no, delivery_note):
	"""Cancel the latest Out log for scanner Undo while preserving audit history."""
	validate_token(token)

	clean_dn = normalize_delivery_note_id(delivery_note) if delivery_note else None
	latest_log = frappe.db.sql(
		"""
		SELECT name
		FROM `tabStock Log`
		WHERE carton_no = %(carton_no)s
			AND type = 'Out'
			AND IFNULL(movement_status, 'Logged') != 'Cancelled'
			AND (%(delivery_note)s IS NULL OR delivery_note = %(delivery_note)s)
		ORDER BY creation DESC
		LIMIT 1
		""",
		{"carton_no": (carton_no or "").strip(), "delivery_note": clean_dn},
		as_dict=True,
	)
	if not latest_log:
		frappe.throw(_("No matching scan found to undo for carton {0}").format(carton_no))

	latest_doc = frappe.get_doc("Stock Log", latest_log[0].name)
	latest_doc.movement_status = "Cancelled"
	latest_doc.validation_message = _("Cancelled by scanner undo")
	# Scanner token validation is the trust boundary for undo; stock operators can reverse
	# scanner mistakes without requiring Desk write permission on Stock Log.
	latest_doc.save(ignore_permissions=True)
	new_status = sync_carton_status_from_latest_log(latest_doc.carton_no)
	frappe.db.commit()
	return {
		"status": "success",
		"message": _("Scan undone successfully."),
		"carton_status": new_status,
	}


@frappe.whitelist(allow_guest=True)
def check_carton_statuses(cartons, token=None):
	validate_token(token)
	if isinstance(cartons, str): cartons = json.loads(cartons)
	statuses = []
	for c in (cartons or []):
		scan_data = c.get("carton_no") if isinstance(c, dict) else c
		
		# Resolve the true Carton No from potential pipe format
		carton_no = scan_data
		if '|' in scan_data:
			parts = scan_data.split('|')
			if len(parts) >= 2:
				carton_no = parts[1]
		
		# Fetch record details via get_all for maximum compatibility 
		res = frappe.get_all("Carton QR", 
							 filters={"name": carton_no}, 
							 fields=["item", "qty", "uom", "status"], 
							 limit_page_length=1)
		record = res[0] if res else None
		
		if not record:
			# Even if record is missing, return a structure so the frontend knows it's a NEW carton (Inbound)
			statuses.append({
				"carton_no": carton_no, 
				"move_type": "In", 
				"current_status": "New",
				"item": "Unknown",
				"item_name": "New Item/Carton",
				"qty": 1,
				"is_new": True
			})
			continue

		active_log = frappe.db.sql(
			"""
			SELECT type
			FROM `tabStock Log`
			WHERE carton_no = %(carton_no)s
				AND IFNULL(movement_status, 'Logged') != 'Cancelled'
			ORDER BY IFNULL(scan_time, creation) DESC, creation DESC
			LIMIT 1
			""",
			{"carton_no": carton_no},
			as_dict=True,
		)
		current_status = record.status or sync_carton_status_from_latest_log(carton_no) or "Draft"
		if current_status == "In Stock":
			move_type = "Out"
		elif current_status == "Dispatched":
			move_type = "In"
		else:
			move_type = "In"
		
		statuses.append({
			"carton_no": carton_no,
			"move_type": move_type,
			"latest_movement_type": active_log[0].type if active_log else None,
			"item": record.item,
			"item_name": frappe.db.get_value("Item", record.item, "item_name") or record.item,
			"qty": record.qty,
			"uom": record.uom,
			"current_status": current_status
		})
	return statuses


@frappe.whitelist(allow_guest=True)
def get_customers(token=None):
	validate_token(token)
	return frappe.get_all("Customer", fields=["name"], order_by="name asc", limit=500)


@frappe.whitelist(allow_guest=True)
def get_suppliers(token=None):
	validate_token(token)
	return frappe.get_all("Supplier", fields=["name"], order_by="name asc", limit=500)


def update_carton_status_from_log(carton_no, log_type):
	new_status = "In Stock" if log_type == "In" else "Dispatched"
	frappe.db.set_value("Carton QR", carton_no, "status", new_status)


@frappe.whitelist(allow_guest=True)
def generate_qr_svg(data, scale=5):
	"""Generates an SVG QR code for the given data. Used in Jinja templates."""
	if not data:
		return ""
	
	import pyqrcode
	from io import BytesIO
	
	qr = pyqrcode.create(data)
	buffer = BytesIO()
	qr.svg(buffer, scale=scale)
	return buffer.getvalue().decode()


def generate_qr_png_data_uri(data, scale=8):
	"""Generates a PNG QR code data URI for print-safe rendering."""
	if not data:
		return ""

	import pyqrcode
	from io import BytesIO

	qr = pyqrcode.create(data, error="M")
	buffer = BytesIO()
	qr.png(buffer, scale=scale, quiet_zone=4)
	encoded = base64.b64encode(buffer.getvalue()).decode()
	return f"data:image/png;base64,{encoded}"

@frappe.whitelist()
def has_app_permission():
	"""
	Permission check for the Warehouse Hub app in Frappe Desk.
	Only warehouse operators and system managers should see the Desk app.
	"""
	if frappe.session.user == "Guest":
		return False
	roles = set(frappe.get_roles())
	return bool(roles.intersection({"System Manager", "Stock Manager"}))


@frappe.whitelist()
def get_delivery_note_cartons(delivery_note):
	"""Return cartons dispatched against a Delivery Note with Carton QR linkage."""
	delivery_note = (delivery_note or "").strip()
	if not delivery_note:
		frappe.throw(_("Delivery Note is required"))

	if not frappe.db.exists("Delivery Note", delivery_note):
		frappe.throw(_("Delivery Note {0} not found").format(delivery_note))
	frappe.get_doc("Delivery Note", delivery_note).check_permission("read")

	logs = frappe.db.sql(
		"""
		SELECT
			sl.carton_no,
			MAX(sl.item) AS item,
			MAX(item.item_name) AS item_name,
			MAX(sl.batch) AS batch,
			MAX(sl.qty) AS qty,
			MAX(carton_qr.name) AS carton_qr_name
		FROM `tabStock Log` sl
		LEFT JOIN `tabItem` item
			ON item.name = sl.item
		LEFT JOIN `tabCarton QR` carton_qr
			ON carton_qr.name = sl.carton_no
		WHERE sl.delivery_note = %(delivery_note)s
			AND sl.type = 'Out'
			AND IFNULL(sl.carton_no, '') != ''
		GROUP BY sl.carton_no
		ORDER BY sl.carton_no ASC
		""",
		{"delivery_note": delivery_note},
		as_dict=True,
	)

	return {
		"delivery_note": delivery_note,
		"count": len(logs),
		"cartons": logs,
	}


def recalculate_batch_maker_counts(batch_id):
	if not batch_id or not frappe.db.exists("Batch QR Maker", batch_id):
		return

	counts = frappe.db.sql(
		"""
		SELECT
			SUM(CASE WHEN status IN ('In Stock', 'Dispatched') THEN 1 ELSE 0 END) AS scanned,
			SUM(CASE WHEN status = 'Dispatched' THEN 1 ELSE 0 END) AS dispatched,
			SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled
		FROM `tabBatch QR Maker Item`
		WHERE parent = %(batch_id)s
		""",
		{"batch_id": batch_id},
		as_dict=True,
	)[0]

	scanned = cint(counts.scanned)
	dispatched = cint(counts.dispatched)
	cancelled = cint(counts.cancelled)
	frappe.db.set_value(
		"Batch QR Maker",
		batch_id,
		{
			"scanned_cartons": scanned,
			"dispatched_cartons": dispatched,
			"cancelled_cartons": cancelled,
			"remaining_stock": max(scanned - dispatched, 0),
		},
		update_modified=True,
	)

def update_batch_maker_status(batch_id, carton_no, status):
	"""
	Propagates status updates from the scanner to the Batch QR Maker dashboard.
	Uses direct SQL for speed during high-frequency scans.
	"""
	if not batch_id: return
	
	try:
		# 1. Update the child table row for this specific carton
		frappe.db.sql("""
			UPDATE `tabBatch QR Maker Item` 
			SET status = %s 
			WHERE parent = %s AND carton_no = %s
		""", (status, batch_id, carton_no))
		recalculate_batch_maker_counts(batch_id)
			
		# 3. Notify the Desk UI via Websockets
		frappe.publish_realtime('batch_status_update', {
			'batch_id': batch_id,
			'carton_no': carton_no,
			'status': status
		})
	except Exception as e:
		frappe.log_error(f"Batch UI Sync Error: {str(e)}", "Warehouse API")
