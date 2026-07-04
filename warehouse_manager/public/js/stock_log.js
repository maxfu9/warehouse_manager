frappe.ui.form.on("Stock Log", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		const status = frm.doc.movement_status || "Logged";

		if (status === "Logged") {
			frm.add_custom_button(__("Verify"), () => update_stock_log_status(frm, {
				method: "warehouse_manager.api.verify_stock_log",
				label: __("Verification Note"),
				fieldname: "note",
				success_message: __("Stock movement verified"),
			}));
			frm.add_custom_button(__("Cancel"), () => update_stock_log_status(frm, {
				method: "warehouse_manager.api.cancel_stock_log",
				label: __("Cancellation Reason"),
				fieldname: "reason",
				success_message: __("Stock movement cancelled"),
			}), __("Actions"));
		}

		if (status === "Verified") {
			frm.add_custom_button(__("Cancel"), () => update_stock_log_status(frm, {
				method: "warehouse_manager.api.cancel_stock_log",
				label: __("Cancellation Reason"),
				fieldname: "reason",
				success_message: __("Stock movement cancelled"),
			}), __("Actions"));
		}

		if (status === "Cancelled") {
			frm.add_custom_button(__("Reopen"), () => {
				frappe.confirm(__("Reopen this cancelled stock movement?"), () => {
					frappe.call({
						method: "warehouse_manager.api.reopen_stock_log",
						args: { stock_log: frm.doc.name },
						freeze: true,
						callback() {
							frappe.show_alert({ message: __("Stock movement reopened"), indicator: "green" });
							frm.reload_doc();
						},
					});
				});
			});
		}
	},
});

function update_stock_log_status(frm, options) {
	frappe.prompt([
		{
			fieldname: options.fieldname,
			fieldtype: "Small Text",
			label: options.label,
		},
	], (values) => {
		frappe.call({
			method: options.method,
			args: {
				stock_log: frm.doc.name,
				[options.fieldname]: values[options.fieldname],
			},
			freeze: true,
			callback() {
				frappe.show_alert({ message: options.success_message, indicator: "green" });
				frm.reload_doc();
			},
		});
	}, options.label, __("Submit"));
}
