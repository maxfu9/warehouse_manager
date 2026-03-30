# Manager QR Scanner 🛡️

A production-grade, high-security QR scanner for employee attendance, designed explicitly for ERPNext & HRMS.

## 🌟 Key Features

- **Isolated Scanner UI**: A dedicated, mobile-first interface that bypasses ERPNext theme conflicts for zero rendering issues.
- **Smart Attendance Logic**: Automatically detects **IN/OUT** status based on the employee's last check-in.
- **QR Security (Signed Payloads)**: Uses **HMAC-SHA256** to sign QR codes. Prevents unauthorized scans or tampered QR codes.
- **GPS Geo-fencing**: Enforces location validation (Haversine distance) to ensure scans occur at specified coordinates.
- **Scan Cooldown**: Configurable protection against duplicate/accidental double-scans.
- **Visual & Audio Feedback**: Real-time employee info cards (with private image support) and distinct success/error tones.
- **Zero Login for Managers**: Guest-accessible via secure, token-based URL parameters.

## 🚀 Installation

1. **Install HRMS**: This app requires the `hrms` app to be installed on your site.
2. **Get the App**:
```bash
bench get-app https://github.com/maxfu9/QR-attendance
bench --site [your-site] install-app warehouse_manager
bench --site [your-site] migrate
```

## ⚙️ Configuration

1. **Setup Token**: Go to **Manager Scanner Settings** and set a `Manager Token` (e.g., `company123`).
2. **Enable Features**:
    - **Scan Cooldown**: Set minimum seconds between scans (default 60s).
    - **Location Validation**: Add your office Latitude/Longitude and allowed radius (meters).
    - **Security**: Toggle **Enforce Signed QR Codes** for maximum security.
3. **Print QR Cards**: Use the provided **Employee QR Card** print format in the Employee doctype. It automatically generates the secure, signed payload.

## 📱 Usage

Managers can access the scanner at:
`https://your-site.com/scanner?token=YOUR_TOKEN`

The scanner will automatically:
1. Handle the redirect to the isolated view.
2. Load configurations and recent logs.
3. Validate location and QR signatures in real-time.

## 🛠️ Technical Details

- **Bypass Engine**: Uses a direct Werkzeug `Response` object to serve raw HTML, ensuring zero interference from Frappe Website Theme layouts.
- **API Proxy**: Includes a secure proxy for private files (`/private/files/`) so guest scanners can see employee photos without being logged into the Desk.
- **Logic**: Built on top of the native HRMS `Employee Checkin` logic.

### License

MIT
