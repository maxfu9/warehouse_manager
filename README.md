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
