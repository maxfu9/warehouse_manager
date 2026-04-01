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
import json
import hashlib
import hmac
import math
import base64

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
		frappe.throw(_("Security Error: {0}").format(str(e)), frappe.PermissionError)


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
			"message": str(e)
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
		processed_logs = frappe.get_all("Stock Log", 
			filters={"delivery_note": dn_id, "type": "Out"}, 
			fields=["item", "qty"]
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
		frappe.log_error(f"DN Details Error: {str(e)}", "Scanner API")
		return {
			"status": "error",
			"message": str(e)
		}


@frappe.whitelist(allow_guest=True)
def handle_stock_log(**kwargs):
	"""Enhanced processor with Deep Trace for debugging DN bypass."""
	try:
		# 1. Parameter Extraction (Robust Capture)
		params = frappe._dict(kwargs)
		if not params: params = frappe.form_dict
		
		manager_token = params.get("manager_token")
		scan_data = params.get("scan_data")
		log_type = params.get("log_type")
		delivery_note = params.get("delivery_note")
		customer = params.get("customer")
		item_code = params.get("item_code")
		source_type = params.get("source_type")
		supplier = params.get("supplier")
		
		validate_token(manager_token)
		
		if not scan_data:
			frappe.throw(_("Scan data missing"))
		
		# 2. Logic Check & Context Resolution
		carton_no = scan_data
		if '|' in scan_data:
			parts = scan_data.split('|')
			if len(parts) >= 3:
				item_code, carton_no, qty_val = parts[0], parts[1], flt(parts[2])
		
		if frappe.db.exists("Carton QR", carton_no):
			c = frappe.get_doc("Carton QR", carton_no)
			item_code = c.item if not item_code else item_code
			qty = c.qty
		else:
			qty = 1 

		# Resolved Item Code
		curr_item = str(item_code or "").strip().upper()

		# CRITICAL: If no item code resolved, we can't process further
		if not curr_item or curr_item == "":
			if not params.get("item_code"):
				return {
					"status": "error", 
					"message": _("New Carton {0}: Item code unknown. Please select a Product.").format(carton_no),
					"needs_item_selection": True
				}

		# 3. DEEP TRACE: GLOBAL DELIVERY NOTE LOCKDOWN
		if delivery_note:
			# Normalize DN ID
			clean_dn = unquote((delivery_note or "").strip())
			if "/" in clean_dn:
				match = re.search(r"(?:Delivery Note|delivery-note)/([^?/\s]+)", clean_dn, re.IGNORECASE)
				if match: clean_dn = match.group(1)
			
			# Fetch all items in this DN (Case-Insensitive list)
			dn_results = frappe.get_all("Delivery Note Item", filters={"parent": clean_dn}, fields=["item_code"])
			dn_items = [i.item_code.strip().upper() for i in dn_results]
			
			# FINAL TRACE: Show exactly what is being matched

			if curr_item not in dn_items:
				mismatch_err = _("WRONG PRODUCT: Item {0} not matched with DN {1}").format(curr_item, clean_dn)
				frappe.throw(mismatch_err)
			
			# QUANTITY HARD BLOCK: Don't allow more scans than required by DN
			# We filter by parent and item_code because multiple rows of the same item are summed by Frappe in get_value or logic
			target_qty = frappe.db.get_value("Delivery Note Item", 
											  {"parent": clean_dn, "item_code": curr_item}, "qty") or 0
			current_scans = frappe.db.count("Stock Log", 
											 {"delivery_note": clean_dn, "item": curr_item, "type": "Out"})
			
			if current_scans >= flt(target_qty):
				frappe.throw(_("TARGET REACHED: Item {0} is already fully picked ({1}/{1} cartons).").format(curr_item, int(target_qty)))

		# 4. Standard Sequence Checks
		current_status = frappe.db.get_value("Carton QR", carton_no, "status") or "New"
		if log_type == "In" and current_status in ["In Stock", "Dispatched"]:
			frappe.throw(_("Sequence Error: Carton {0} is currently {1}. Cannot scan 'In' again.").format(carton_no, current_status))
		
		if log_type == "Out" and current_status != "In Stock":
			if current_status == "Dispatched":
				frappe.throw(_("Sequence Error: Carton {0} has already been Dispatched.").format(carton_no))
			else:
				frappe.throw(_("Sequence Error: Carton {0} must be marked as 'In Stock' before it can be Dispatched (Current: {1}).").format(carton_no, current_status))
		
		# For Pick & Scan, it is ALWAYS an outbound log
		final_type = log_type or ("Out" if (current_status == "In Stock" or delivery_note) else "In")
		if delivery_note:
			final_type = "Out"

		# 5. Create Log
		item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
		batch = frappe.db.get_value("Carton QR", carton_no, "batch")
		
		doc = frappe.new_doc("Stock Log")
		doc.update({
			"item": item_code,
			"carton_no": carton_no,
			"batch": batch,
			"type": final_type,
			"qty": qty,
			"delivery_note": clean_dn if (final_type == "Out" and 'clean_dn' in locals()) else (delivery_note if final_type == "Out" else None),
			"customer": customer if final_type == "Out" else None,
			"source_type": source_type if final_type == "In" else None,
			"supplier": supplier if (final_type == "In" and source_type == "Purchase") else None,
			"scan_time": now_datetime()
		})
		doc.insert(ignore_permissions=True)

		# 6. Update or Create Status
		new_status = "In Stock" if final_type == "In" else "Dispatched"
		
		# Propagate to THE specific carton/batch record itself
		if frappe.db.exists("Carton QR", carton_no):
			frappe.db.set_value("Carton QR", carton_no, "status", new_status)
		
		# Propagate to ALL individual cartons linked to this batch ID
		# This ensures that scanning a Batch QR for "Inbound" marks all its contents as "In Stock"
		frappe.db.set_value("Carton QR", {"batch": (carton_no or "").strip()}, "status", new_status, update_modified=True)

		if not frappe.db.exists("Carton QR", carton_no) and final_type == "In":
			# Auto-create tracking record for NEW cartons
			new_c = frappe.new_doc("Carton QR")
			new_c.update({
				"name": carton_no,
				"item": item_code,
				"carton_no": carton_no,
				"status": new_status,
				"qty": qty,
				"creation_type": "Scanner"
			})
			new_c.insert(ignore_permissions=True)
		
		# REAL-TIME BATCH SYNC: Propagate to the Batch QR Maker items/counts
		batch_id = frappe.db.get_value("Carton QR", carton_no, "batch")
		if batch_id and frappe.db.exists("Batch QR Maker", batch_id):
			update_batch_maker_status(batch_id, carton_no, new_status)

		return {
			"status": "success",
			"item": item_code or carton_no,
			"item_name": item_name or item_code or carton_no,
			"qty": qty,
			"log_type": final_type,
			"current_status": new_status,
			"carton_no": carton_no
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), _("Stock Log Action Error"))
		return {
			"status": "error",
			"message": str(e)
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
		for scan in (cartons or []):
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
			"carton_no": (last_res.get("carton_no") if last_res else None) or (scan.get('scan_data') if isinstance(scan, dict) else scan)
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), _("Batch Scan Error"))
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def revert_stock_log(token, carton_no, delivery_note):
	"""Deletes the latest "Out" log for a carton/DN to support scanner 'Undo'."""
	validate_token(token)
	
	filters = {"carton_no": (carton_no or "").strip(), "type": "Out"}
	if delivery_note:
		filters["delivery_note"] = (delivery_note or "").strip()
		
	latest_log = frappe.get_all("Stock Log", 
								 filters=filters, 
								 order_by="creation desc", 
								 limit=1)
	if not latest_log:
		frappe.throw(_("No matching scan found to undo for carton {0}").format(carton_no))
	
	# Delete Log
	frappe.delete_doc("Stock Log", latest_log[0].name, ignore_permissions=True)
	
	# Revert Carton Status back to "In Stock"
	if frappe.db.exists("Carton QR", carton_no):
		frappe.db.set_value("Carton QR", carton_no, "status", "In Stock")
	
	return {"status": "success", "message": _("Scan undone successfully.")}


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

		log_count = frappe.db.count("Stock Log", filters={"carton_no": carton_no})
		move_type = "In" if log_count == 0 else "Out" if log_count == 1 else "Done"
		
		statuses.append({
			"carton_no": carton_no,
			"move_type": move_type,
			"item": record.item,
			"item_name": frappe.db.get_value("Item", record.item, "item_name") or record.item,
			"qty": record.qty,
			"uom": record.uom,
			"current_status": record.status
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

@frappe.whitelist()
def has_app_permission():
	"""
	Permission check for the Warehouse Hub app in Frappe Desk.
	Standard Desk users are allowed; Guest users are not.
	"""
	if frappe.session.user == "Guest":
		return False
	return True

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
		
		# 2. Update the parent status counts (Optimistic update)
		# We'll let the user click 'Close' for final reconciliation, 
		# but we can update the counts here for the live dashboard.
		if status == "In Stock":
			frappe.db.sql("UPDATE `tabBatch QR Maker` SET scanned_cartons = scanned_cartons + 1 WHERE name = %s", (batch_id,))
		elif status == "Dispatched":
			frappe.db.sql("UPDATE `tabBatch QR Maker` SET dispatched_cartons = dispatched_cartons + 1 WHERE name = %s", (batch_id,))
			
		# 3. Notify the Desk UI via Websockets
		frappe.publish_realtime('batch_status_update', {
			'batch_id': batch_id,
			'carton_no': carton_no,
			'status': status
		})
	except Exception as e:
		frappe.log_error(f"Batch UI Sync Error: {str(e)}", "Warehouse API")
