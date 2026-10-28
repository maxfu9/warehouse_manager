# Warehouse Management Hub 📦

A unified, production-grade logistics and workforce management PWA for Frappe & ERPNext.

## 🌟 Key Features

### 🏢 Warehouse & Inventory (New)
- **Unified Scanner**: A single, mobile-first interface for both **Workforce Attendance** and **Inventory Logistics**.
- **Scan-to-Log**: Inbound and Outbound movement tracking for cartons/products.
- **Smart Batch Management**: Automatically closes `Batch QR Maker` status when all cartons are dispatched.
- **Manual Entry Support**: A floating manual ID entrance for damaged QR codes.
- **Duplicate Prevention**: Backend logic blocks already-processed cartons in the same session.

### 🛡️ Workforce Security
- **Smart Attendance Logic**: Automatically detects **IN/OUT** status based on the employee's last check-in.
- **QR Security (Signed Payloads)**: Uses **HMAC-SHA256** to sign QR codes, preventing unauthorized or tampered scans.
- **GPS Geo-fencing**: Enforces location validation (Haversine distance) for workforce scans.
- **Scan Cooldown**: Protects against duplicate/accidental double-scans.
- **Visual & Audio Feedback**: Real-time employee info cards and distinct success/error tones.
- **Zero Login for Managers**: Guest-accessible via secure, token-based URL parameters.

## 🚀 Installation

1. **Prerequisites**: Ensure `hrms` and `erpnext` are installed on your site.
2. **Get the App**:
```bash
bench get-app https://github.com/maxfu9/warehouse_manager
bench --site [your-site] install-app warehouse_manager
bench --site [your-site] migrate
```

## ⚙️ Configuration

### Frappe v16 Desk

Install and migration create the **Warehouse Hub** Desk icon and its sidebar.
The sidebar includes the dashboard, scanner, carton and batch operations, all
five warehouse reports, and both settings pages. Access follows the existing
System Manager / Stock Manager roles and document permissions.

After updating an existing v16 site, run from the bench directory:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
bench restart
```

Reload Desk in the browser to refresh navigation. To repair only the Desk
records, run `bench --site <site-name> execute warehouse_manager.setup.setup_v16_desk`.
Frappe v15 continues to use the workspace; the v16 Desk setup is skipped there.

### Carton label printing

**Print Labels** offers 2, 4, 6 or 8 labels per A4 sheet with 5mm printer
margins, remembers the last choice, and supports Preview and Print. QR sizes
are 84, 72, 50 and 36mm respectively, including their quiet zones. Each label
has a carton ID, adaptive product name, and packing contents marked `/ CTN`.
Rounded inner borders frame each label; dashed outer guides and corner crop
marks show the cut positions on every occupied label cell.
Cancelled labels are excluded. Use actual size / 100% in the printer dialog.

The HTML source and JSON export must stay identical. After editing the HTML,
run `node scripts/sync_label_template.cjs`. Migration refreshes the live standard
Print Format. A synthetic PDF can be checked with
`bench --site <site-name> execute warehouse_manager.tests.label_preview.render_samples`.

### Work Order production labels

On a Work Order, **Warehouse Labels > Allow Carton Labels** permits carton batches.
Each **Manufacture Stock Entry** has a **Generate Carton Labels** checkbox,
unchecked by default. Check it only for complete packed cartons; leave it off
for parts or intermediate production. Submitting a checked entry creates and
submits one Batch QR Maker linked to that Work Order and Stock Entry. Each completed
finished-good unit in the entry's stock UOM creates one carton QR; partial
production entries get separate batches. Fractional carton counts are rejected.
Scrap and process loss do not generate labels.

Qty per Carton and Contents UOM are optional label information (default quantity
1); they never convert the carton count. Generated cartons remain Draft until
inbound scanning. Retrying the same entry reuses its batch. Cancelling manufacture
cancels unused labels; received/dispatched cartons must be reversed first.
Existing submitted manufacturing entries are not automatically backfilled.

Both Work Order and Stock Entry show a Warehouse connection to their batches.

Warehouse stock is measured in **cartons (CTN)**. Inventory and batch reports
use current Carton QR status, with batch-table fallback where tracking records
are missing. Packing quantity stays on labels and carton records for reference;
it does not determine available carton counts. Cancelled labels are excluded.
Movement and customer reports describe recorded history; missing historical
dispatches are flagged as exceptions rather than fabricated.

### Saved scanner sessions and exceptions

New scans are linked to an open **Warehouse Scan Session**, independently for
inbound lots and outbound dispatches. Refreshing or changing modes restores
totals from active Stock Logs. Close Lot / Start New Dispatch closes the saved
session; finishing a DN keeps the dispatch session available for the next DN.
Scanner Control > Resume Saved Session accepts an open Session ID from Desk.
Existing browser-only scans remain visible until the first new session; older
Stock Logs are not assigned to invented historical sessions.

**Warehouse Exceptions** lists carton status mismatches, missing tracking
records, missing partners/sources, and inactive stock. It shows up to 500 rows
and supports item, carton, and inactivity filters. Cancelled Stock Logs are
excluded from operational reports and saved-session totals.

Regression checks:

```bash
python3 -m unittest discover -s warehouse_manager/tests -p 'test_*.py'
node warehouse_manager/tests/test_scanner_controls.cjs
bench --site <site-name> execute warehouse_manager.tests.stock_regressions.run
```

The database regression uses connection-local temporary tables and leaves
production warehouse records untouched.

1. **Setup Token**: Go to **Manager Scanner Settings** and set a `Manager Token` (e.g., `company123`).
2. **Access URL**: The system will automatically generate a friendly URL for your device.
3. **Inventory Settings**: Configure your Item Codes and cartons in the **Warehouse Management Hub** module.

## 📱 Usage

Managers can access the unified hub at:
`https://your-site.com/stock-scanner?token=YOUR_TOKEN`

The scanner will automatically:
1. Load the **Unified Scanner Interface**.
2. Allow switching between **Workforce** and **Inventory** tabs.
3. Show real-time session statistics (Total scanned items vs Target).

## 🛠️ Technical Details

- **Bypass Engine**: Serving raw HTML via a direct Werkzeug `Response` to ensure zero interference from Frappe Website Theme layouts.
- **API Proxy**: Secure proxy for private files (`/private/files/`) so guest scanners can see employee photos safely.
- **App Namespace**: `warehouse_manager` (formerly `qr_attendance`).

### License

MIT
