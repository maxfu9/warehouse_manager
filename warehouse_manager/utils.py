import frappe
from frappe.utils import cint, flt

from warehouse_manager.api import SETTINGS_DOCTYPE, get_signed_qr_payload


def get_employee_card_settings():
    defaults = {
        "card_design_preset": "Modern",
        "card_badge_label": "",
        "show_company_name": 1,
        "show_photo": 1,
        "show_employee_id": 1,
        "show_designation": 1,
        "show_department": 1,
        "show_qr_title": 1,
        "qr_title_text": "Scan to Mark Attendance",
        "show_qr_subtitle": 1,
        "qr_subtitle_text": "Use the manager scanner to check in or out",
        "card_width_inches": 3.5,
        "card_height_inches": 2.0,
        "qr_size_inches": 1.18,
        "print_margin_inches": 0.08,
    }
    check_fields = {
        "show_company_name",
        "show_photo",
        "show_employee_id",
        "show_designation",
        "show_department",
        "show_qr_title",
        "show_qr_subtitle",
    }
    float_fields = {
        "card_width_inches",
        "card_height_inches",
        "qr_size_inches",
        "print_margin_inches",
    }

    try:
        settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
    except Exception:
        return defaults

    values = {}
    for key, default in defaults.items():
        value = getattr(settings, key, None)
        if value in (None, ""):
            values[key] = default
        elif key in check_fields:
            values[key] = bool(cint(value))
        elif key in float_fields:
            values[key] = flt(value)
        else:
            values[key] = value

    values["card_badge_label"] = (values.get("card_badge_label") or "").strip()
    values["qr_title_text"] = (values.get("qr_title_text") or "").strip()
    values["qr_subtitle_text"] = (values.get("qr_subtitle_text") or "").strip()
    values["card_design_preset"] = (values.get("card_design_preset") or "Modern").strip() or "Modern"

    return values
