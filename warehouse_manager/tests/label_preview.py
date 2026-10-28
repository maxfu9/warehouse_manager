"""Render synthetic labels through the site's actual Jinja and PDF engines."""

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import frappe
from pypdf import PdfReader

from warehouse_manager.api import generate_qr_png_data_uri


def render_samples(output='/tmp/warehouse-label-preview.pdf', labels_per_page=2):
	labels_per_page = int(labels_per_page)
	assert labels_per_page in (2, 4, 6, 8)
	count = labels_per_page + 1
	folder = Path(frappe.get_app_path('warehouse_manager', 'warehouse_management_hub', 'print_format', 'batch_labels_a5'))
	template = (folder / 'batch_labels_a5.html').read_text()
	assert json.loads((folder / 'batch_labels_a5.json').read_text())['html'] == template
	rows = [SimpleNamespace(carton_no=f'CRT20261000{i}EU', status='Draft') for i in range(1, count + 1)]
	rows.append(SimpleNamespace(carton_no='CANCELLED-LABEL', status='Cancelled'))
	names = {
		'ITEM1': 'Rinza Large Single',
		'ITEM2': 'Rinza Small 2P - Premium Heavy Duty Warehouse Packaging',
		'ITEM3': 'LONG PRODUCT NAME ' * 7,
	}
	cartons = {row.carton_no: SimpleNamespace(name=row.carton_no, carton_no=row.carton_no,
		item=f'ITEM{((i - 1) % 3) + 1}', qty=144.0 if i != 2 else 24.5, uom='Piece', signed_data=row.carton_no)
		for i, row in enumerate(rows[:count], 1)}
	context = {
		'doc': SimpleNamespace(items=rows),
		'frappe': SimpleNamespace(get_doc=lambda dt, name: cartons[name],
			db=SimpleNamespace(get_value=lambda dt, name, field: names[name])),
		'generate_qr_png_data_uri': generate_qr_png_data_uri,
		'print_settings': {'warehouse_labels_per_page': labels_per_page},
	}
	content = frappe.render_template(template, context)
	assert content.count('class="qr-image"') == count
	assert content.count('class="label-outline"') == count
	assert content.count('class="label-cut-guide"') == count
	assert content.count('class="crop-mark ') == count * 4
	assert 'CANCELLED-LABEL' not in content
	assert '24.5' in content
	from frappe.utils.pdf import get_pdf, read_options_from_html

	html = '<html><head><meta charset="UTF-8"></head><body><div class="print-format">' + content + '</div></body></html>'
	_, options = read_options_from_html(html)
	assert all(options[f'margin-{side}'] == '5mm' for side in ('top', 'bottom', 'left', 'right'))
	pdf = get_pdf(html)
	pages = PdfReader(BytesIO(pdf)).pages
	assert len(pages) == 2, f'Expected two sheets for {count} labels at {labels_per_page}/page, got {len(pages)}'
	last_id = rows[count - 1].carton_no
	assert last_id not in pages[0].extract_text()
	assert last_id in pages[1].extract_text()
	Path(output).write_bytes(pdf)
	Path(output).with_suffix('.html').write_text(html)
	return {'status': 'passed', 'pages': len(pages), 'labels': count, 'labels_per_page': labels_per_page, 'output': output}


def render_all_layouts():
	return [render_samples(f'/tmp/warehouse-labels-{count}-per-page.pdf', count) for count in (2, 4, 6, 8)]


def verify_live():
	folder = Path(frappe.get_app_path('warehouse_manager', 'warehouse_management_hub', 'print_format', 'batch_labels_a5'))
	template = (folder / 'batch_labels_a5.html').read_text()
	assert frappe.db.get_value('Print Format', 'Batch Labels A5', 'html') == template
	return {'status': 'passed', 'format': 'Batch Labels A5', 'layout': '2, 4, 6 or 8 labels per A4; square PNG QR; adaptive product name'}
