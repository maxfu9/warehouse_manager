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

function render_items_qty_total(frm) {
	const totalQty = (frm.doc.items || []).reduce((sum, item) => {
		if (!item || item.status === 'Cancelled') {
			return sum;
		}
		return sum + flt(item.qty || 0);
	}, 0);
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
			<span style="opacity:.75;">Total Qty</span>
			<span>${format_number(totalQty)}</span>
		</div>
	`);

	wrapper.find('.grid-body').after(totalRow);
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
			// Explicit Print Button for A5 Labels
			frm.add_custom_button(__('Print Labels (A5)'), function() {
				const url = frappe.urllib.get_full_url(
					'/printview?doctype=' +
						encodeURIComponent(frm.doctype) +
						'&name=' +
						encodeURIComponent(frm.docname) +
						'&trigger_print=1' +
						'&format=' +
						encodeURIComponent('Batch Labels A5') +
						'&no_letterhead=1' +
						(frappe.boot.lang ? '&_lang=' + encodeURIComponent(frappe.boot.lang) : '')
				);
				window.location.href = url;
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
		render_items_qty_total(frm);

		if (frm.doc.docstatus > 0) {
			frm.set_intro(
				__('Stock Snapshot: {0} in stock, {1} remaining, {2} dispatched, {3} cancelled.', [
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
		render_items_qty_total(frm);
	}
});
