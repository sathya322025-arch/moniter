# 📱 Device Connection Monitoring Dashboard

A secure, responsive web application for centralized connection monitoring across **mobile phones, tablets, and laptops/desktops**.

---

## 🌟 Key Capabilities

### 1. Automatic Device Registration
- **Zero Approval Needed for Registration**: When a visitor opens the link, the server automatically records the connection event in the background without prompting the user for approval.
- **Telemetry Collected & Displayed**:
  - **Device Category**: Mobile Phone, Tablet, or Laptop / Desktop.
  - **Operating System**: Windows 10/11, macOS, iOS, Android, Linux.
  - **Browser & Version**: Google Chrome, Apple Safari, Microsoft Edge, Mozilla Firefox, Opera, Samsung Internet.
  - **Public IP Address**: Extracted from server-side connection headers (`X-Forwarded-For` or socket).
  - **Connection Date & Time**: Timestamped in UTC.
  - **Status & Last Seen**: Dynamic relative activity indicators (`Just now`, `5s ago`, `Online`, `Away`, `Disconnected`).
  - **Temporary Session Identifier**: Unique device ID assigned per session (`dev_xxxxxxxx`).

### 2. Administrator Dashboard
- **Protected Access**: Server-side Role-Based Access Control (`ADMIN` role required).
- **Searchable Device & Connection List**: Live search filter bar in the dashboard to filter devices instantly by Device ID, Hostname, IP address, OS, or Browser.
- **Historical Connection Logs**: Dedicated table tracking all historical automatic connection events with timestamps.
- **User Authentication & Login History**: Audit records of all login events (`SUCCESS`, `FAILED`, `RATE_LIMITED`).
- **Live Updates via Server-Sent Events (SSE)**: Updates in real-time as visitors connect or disconnect without manual page reloads.
- **Device Management & Enrollment**: Optional secure enrollment links for pre-approved managed devices with automatic routine reconnection and remote assistance under organization policy.

### 3. User Landing Page
- Minimal, responsive interface showing **only** the smiley emoji 😊 with **Yes** and **No** buttons.
- Transparent **Connection Privacy Notice** explaining that basic connection telemetry (device category, OS, browser, IP) is automatically logged for server monitoring.
- Clicking 😊 opens the Admin Authentication modal.

### 4. Security & Privacy
- **No Password Leaks**: Credentials are never logged in audit files or exposed in URLs. Passwords hashed with PBKDF2-HMAC-SHA256 (100,000 iterations).
- **Rate Limiting**: Protects login against brute-force attacks (5 failed attempts per 5 minutes per IP).
- **Data Minimization & Retention Policy**: Automated retention daemon prunes logs beyond 500 records.
- **No Covert Surveillance**: No camera, microphone, or private file access is requested or permitted.

### 5. Optional Screen Sharing
- Implemented as an independent, permission-based feature via native browser APIs (`getDisplayMedia`).
- Requires explicit user consent before screen sharing begins.
- Prominent floating sharing indicator (`🔴 Screen Sharing Active`) with an immediate **Stop Sharing** control.

---

## 🏗️ Architecture & Interaction Flow

```
                      Visitor Opens Link (http://...:10001)
                                      │
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
                 📱 Mobile Device            💻 Laptop Browser
                        │                           │
                        └─────────────┬─────────────┘
                                      ▼
                      1. AUTOMATIC BACKGROUND CONNECTION
                         • Telemetry captured (Category, OS, Browser, IP)
                         • Recorded in SQLite connection_history
                         • Real-time SSE push -> Admin Dashboard
                                      │
                                      ▼
                      2. PUBLIC LANDING PAGE (/)
                         • Interactive Smiley Emoji 😊
                         • Yes / No Buttons
                         • Transparent Connection Privacy Notice
                                      │
                         User clicks 😊 -> Admin Login
                                      │
                                      ▼
                      3. ADMIN DASHBOARD (/admin)
                         • Searchable Connected Devices Table (Live Filter)
                         • Historical Connection Logs Table
                         • User Authentication Audit Table
                         • Live Real-Time Feed (Server-Sent Events)
                                      │
                                      ▼
                      4. OPTIONAL PERMISSION-BASED SCREEN SHARING
                         • Admin clicks "Request Screen"
                         • Device gets consent dialog & native browser prompt
                         • WebRTC Peer-to-Peer live video stream
                         • Visible persistent banner with Stop Sharing button
```

---

## 🔑 Pre-Configured Test Credentials

| Username | Password | Role | Permissions |
| :--- | :--- | :--- | :--- |
| **`admin`** | **`qwertyuiolkjhgfdsxcv`** | `ADMIN` | Full access to Device Console, Live Search, Connection History, and Screen Requests |
| **`guest_user`** | **`UserPassword123!`** | `USER` | Denied access to admin dashboard (`403 Forbidden`) |

---

## 🚀 Running & Verification Steps

### 1. Server Status
The multi-threaded server daemon is currently running on port **`10001`**:
- **Public Portal**: `http://localhost:10001`
- **Admin Dashboard**: `http://localhost:10001/admin`

To launch manually in PowerShell:
```powershell
cd "C:\Users\MK\Documents\secure_admin_portal"
python server.py
```

### 2. Testing Automatic Connection & Search
1. Open [http://localhost:10001](http://localhost:10001) in an incognito window or mobile device.
2. In another tab, log in as `admin` at [http://localhost:10001/admin](http://localhost:10001/admin).
3. Notice the device appears **automatically** in the **Managed & Connected Devices** table with its category (📱 / 💻), OS, browser version, IP address, and connection timestamp.
4. **Test Live Search**: Type into the search bar (e.g. `Chrome`, `Mobile`, `iPhone`, or an IP address) to see the table filter instantly in real-time.
5. **View Connection History**: Scroll to the **Historical Device Connection Logs** table to see chronological records of all connection events.
6. **Test Screen Sharing**: Click **Request Screen** / **Remote Assist** to test permission-based screen streaming with the prominent indicator and stop controls.
