function apply_item_row_colors(frm) {
	const statusColors = {
		'In Stock': '#e8f7ee',
		'Dispatched': '#eef4ff',
		'Cancelled': '#fdebec',
		'Draft': '#f7f8fa',
		'Generated': '#fff8e6'
	};
	(frm.fields_dict.items.grid.grid_rows || []).forEach((gridRow) => {
		if (!gridRow || !gridRow.doc || !gridRow.row) {
			return;
		}
		const background = statusColors[gridRow.doc.status] || '#ffffff';
		$(gridRow.row).css('background-color', background);
	});
}

function render_items_carton_total(frm) {
	const totalCartons = (frm.doc.items || []).filter(item => item.status !== 'Cancelled').length;
	const wrapper = frm.fields_dict.items.grid.wrapper;
	wrapper.find('.batch-items-total-row').remove();

	const totalRow = $(`
		<div class="batch-items-total-row" style="
			display:flex;
			align-items:center;
			justify-content:flex-end;
			gap:12px;
			padding:10px 18px 12px;
			border-top:1px solid var(--border-color);
			background:#fafbfc;
			font-weight:700;
			color:var(--text-color);
		">
			<span style="opacity:.75;">Total CTN (excluding cancelled labels)</span>
			<span>${format_number(totalCartons)}</span>
		</div>
	`);

	wrapper.find('.grid-body').after(totalRow);
}

function open_batch_label_print(frm, labelsPerPage, triggerPrint) {
	const count = [2, 4, 6, 8].includes(Number(labelsPerPage)) ? Number(labelsPerPage) : 2;
	localStorage.setItem('warehouse_labels_per_page', String(count));
	const query = new URLSearchParams({
		doctype: frm.doctype,
		name: frm.docname,
		format: 'Batch Labels A5',
		no_letterhead: '1',
		trigger_print: triggerPrint ? '1' : '0',
		settings: JSON.stringify({warehouse_labels_per_page: count})
	});
	if (frappe.boot.lang) query.set('_lang', frappe.boot.lang);
	window.location.href = frappe.urllib.get_full_url('/printview?' + query.toString());
}

function show_batch_label_options(frm) {
	const saved = localStorage.getItem('warehouse_labels_per_page');
	const descriptions = {
		2: __('Large: 200 x 143 mm, 84 mm QR. Two labels per A4 sheet.'),
		4: __('Medium: 100 x 143 mm, 72 mm QR. Four labels per A4 sheet.'),
		6: __('Small: 100 x 95 mm, 50 mm QR. Six labels per A4 sheet.'),
		8: __('Compact: 100 x 71 mm, 36 mm QR. Eight labels per A4 sheet.')
	};
	let dialog;
	dialog = new frappe.ui.Dialog({
		title: __('Print Carton Labels'),
		fields: [
			{fieldname: 'labels_per_page', fieldtype: 'Select', label: __('Labels per A4 Page'),
				options: '2\n4\n6\n8', reqd: 1, default: ['2', '4', '6', '8'].includes(saved) ? saved : '2',
				onchange() {
					if (dialog && dialog.fields_dict.layout_info) updateDescription();
				}},
			{fieldname: 'layout_info', fieldtype: 'HTML'}
		],
		primary_action_label: __('Print'),
		primary_action(values) {
			dialog.hide();
			open_batch_label_print(frm, values.labels_per_page, true);
		},
		secondary_action_label: __('Preview'),
		secondary_action() {
			const values = dialog.get_values();
			if (!values) return;
			dialog.hide();
			open_batch_label_print(frm, values.labels_per_page, false);
		}
	});
	function updateDescription() {
		const count = Number(dialog.get_value('labels_per_page')) || 2;
		dialog.fields_dict.layout_info.$wrapper.empty()
			.append($('<p>').text(descriptions[count]))
			.append($('<p class="text-muted">').text(__('Use A4 paper and actual size / 100%. Cancelled labels are excluded.')));
	}
	dialog.show();
	updateDescription();
}

frappe.ui.form.on('Batch QR Maker', {
	refresh: function(frm) {
		const scanned = cint(frm.doc.scanned_cartons || 0);
		const dispatched = cint(frm.doc.dispatched_cartons || 0);
		const remaining = Math.max(scanned - dispatched, 0);
		if (frm.doc.remaining_stock !== remaining) {
			frm.doc.remaining_stock = remaining;
			frm.refresh_field('remaining_stock');
		}

		// Force the correct print format to be selected by default
		if (frm.doc.docstatus === 1) {
			frm.set_df_property('items', 'print_hide', 1); // Hide the table in standard prints too
		}
		// DRAFT Status (Docstatus 0)
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			if (frm.doc.status === 'Draft') {
				frm.add_custom_button(__('Generate Cartons'), function() {
					frm.call('generate_cartons').then(r => {
						if (!r.exc) {
							frappe.show_alert({
								message: __('Generated {0} cartons successfully!').format(frm.doc.no_of_cartons),
								indicator: 'green'
							});
							frm.reload_doc();
						}
					});
				}).addClass('btn-primary');
			}
		}

		// SUBMITTED Status (Docstatus 1)
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__('Print Labels'), function() {
				show_batch_label_options(frm);
			}).addClass('btn-primary').css({'background-color': '#1a73e8', 'color': 'white', 'font-weight': 'bold'});

			if (frm.doc.status === 'Generated') {
				// Only for Managers
				if (frappe.user_roles.includes('Stock Manager') || frappe.user_roles.includes('System Manager')) {
					frm.add_custom_button(__('Close Batch'), function() {
						frappe.confirm(__('Are you sure? This will delete any labels that were NOT scanned.'), function() {
							frm.call('close_batch').then(r => {
								if (!r.exc) {
									frappe.show_alert({ message: r.message, indicator: 'blue' });
									frm.reload_doc();
								}
							});
						});
					}).addClass('btn-danger');
				}
			}
		}

		apply_item_row_colors(frm);
		render_items_carton_total(frm);

		if (frm.doc.docstatus > 0) {
			frm.set_intro(
				__('Stock Snapshot: {0} received CTN, {2} dispatched CTN, {1} in stock CTN, {3} cancelled labels.', [
					scanned,
					remaining,
					dispatched,
					cint(frm.doc.cancelled_cartons || 0)
				]),
				remaining > 0 ? 'blue' : 'orange'
			);
		} else {
			frm.set_intro(__('Generate cartons and submit the batch to start tracking stock movement.'), 'blue');
		}
	},
	before_print: function(frm) {
		if (frm.doc.docstatus === 1) {
			frm.print_preview.print_format = 'Batch Labels A5';
		}
	}
});

frappe.ui.form.on('Batch QR Maker Item', {
	form_render: function(frm) {
		apply_item_row_colors(frm);
		render_items_carton_total(frm);
	}
});
