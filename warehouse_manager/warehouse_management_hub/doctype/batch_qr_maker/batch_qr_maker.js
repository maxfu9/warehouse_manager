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

		// Table Styling
		frm.fields_dict['items'].grid.wrapper.find('.grid-row').each(function(i, row) {
			let doc = frm.doc.items[i];
			if (doc && doc.status === 'Logged') {
				$(row).css('background-color', '#d4edda'); // Light green for logged
			} else if (doc && doc.status === 'Cancelled') {
				$(row).css('background-color', '#f8d7da'); // Light red for cancelled
			}
		});

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
