frappe.ui.form.on("Manager Scanner Settings", {
    refresh(frm) {
        renderScannerAccessUrl(frm);
    },
    manager_token(frm) {
        renderScannerAccessUrl(frm);
    }
});

function renderScannerAccessUrl(frm) {
    const field = frm.get_field("scanner_access_url_html");
    if (!field || !field.$wrapper) {
        return;
    }

    const token = (frm.doc.manager_token || "").trim();
    if (!token) {
        field.$wrapper.html(`
            <div class="text-muted small" style="padding: 8px 0;">
                Set the manager scanner token to generate the access URL.
            </div>
        `);
        return;
    }

    const url = `${window.location.origin}/stock-scanner?token=${encodeURIComponent(token)}`;
    const escapedUrl = frappe.utils.escape_html(url);

    field.$wrapper.html(`
        <div style="padding: 8px 0 2px;">
            <div style="font-size: 12px; color: #6b7280; margin-bottom: 8px;">Open this URL on the manager scanner device.</div>
            <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <a href="${escapedUrl}" target="_blank" rel="noopener noreferrer" style="word-break: break-all; font-weight: 600;">${escapedUrl}</a>
                <button type="button" class="btn btn-xs btn-secondary copy-scanner-url">Copy</button>
            </div>
        </div>
    `);

    field.$wrapper.find('.copy-scanner-url').on('click', () => {
        frappe.utils.copy_to_clipboard(url);
        frappe.show_alert({ message: __('Scanner access URL copied'), indicator: 'green' });
    });
}
