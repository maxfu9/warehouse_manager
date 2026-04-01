frappe.ui.form.on('Batch QR Maker', {
	refresh: function(frm) {
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
				// Use set_route to force the specific print format
				frappe.set_route('print', frm.doctype, frm.docname, 'Batch Labels A5');
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
	}
});
