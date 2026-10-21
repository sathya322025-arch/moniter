#!/usr/bin/env python3
"""
Secure Centralized Device Management & Real-Time Monitoring Portal
- Unique, secure enrollment link generation for authorized devices.
- Routine automatic reconnection without repeated user approval prompts.
- Telemetry: Device ID, hostname, IP address, OS, Browser & Version, Status.
- Real-time Server-Sent Events (SSE) broadcasting for instant status sync.
- Role-Based Access Control (ADMIN only for console and enrollment).
- Direct Remote Screen Assist for managed devices under Organization Policy.
- Visible session indicators, local Stop Sharing control, zero covert access.
- SQLite audit trail with automated retention limits.
- Playful minimal public landing page: Strictly 😊 with Yes & No buttons.
"""

import http.server
import socketserver
import json
import urllib.parse
import hashlib
import secrets
import sqlite3
import os
import sys
import time
import re
import threading
import queue
from datetime import datetime, timezone

# UTF-8 stdout configuration for Windows compatibility
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PORT = int(os.environ.get("PORT", 10001))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DB_FILE = os.path.join(BASE_DIR, "database.db")
AUDIT_LOG_FILE = os.path.join(BASE_DIR, "audit.log")

# ---------------------------------------------------------
# Password Security (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------
def hash_password(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return f"{salt}:{hashed}"

def verify_password(stored_hash, password):
    try:
        salt, expected_hash = stored_hash.split(":")
        calc_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return secrets.compare_digest(expected_hash, calc_hash)
    except Exception:
        return False

# ---------------------------------------------------------
# Database Initialization & Retention Policies
# ---------------------------------------------------------
MAX_RETENTION_RECORDS = 500

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Connection History Table (Automatic Device Registration)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connection_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            device_type TEXT NOT NULL,
            os_name TEXT NOT NULL,
            browser_name TEXT NOT NULL,
            browser_version TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            connected_at TEXT NOT NULL,
            last_activity_at TEXT NOT NULL,
            status TEXT NOT NULL,
            login_status TEXT DEFAULT 'Public Visitor'
        )
    """)

    # 3. Enrollment Tokens Table (Secure device provisioning)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enrollment_tokens (
            token TEXT PRIMARY KEY,
            created_by TEXT NOT NULL,
            policy_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at REAL NOT NULL,
            is_used INTEGER DEFAULT 0,
            used_by_device_id TEXT
        )
    """)

    # 4. Enrolled Managed Devices Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enrolled_devices (
            device_id TEXT PRIMARY KEY,
            device_auth_token TEXT UNIQUE NOT NULL,
            hostname TEXT NOT NULL,
            device_type TEXT NOT NULL,
            os_name TEXT NOT NULL,
            browser_name TEXT NOT NULL,
            browser_version TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            enrolled_at TEXT NOT NULL,
            policy_agreed_at TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            last_seen TEXT NOT NULL
        )
    """)

    # 5. Login Audit Records
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            role TEXT,
            status TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            device_type TEXT NOT NULL,
            os_name TEXT NOT NULL,
            browser_name TEXT NOT NULL,
            user_agent TEXT NOT NULL,
            timestamp_utc TEXT NOT NULL,
            details TEXT
        )
    """)

    # 6. Screen Sharing Audit Records
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS screen_share_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            admin_username TEXT NOT NULL,
            target_device_id TEXT NOT NULL,
            device_type TEXT NOT NULL,
            os_name TEXT NOT NULL,
            browser_name TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            started_at TEXT,
            ended_at TEXT,
            details TEXT
        )
    """)

    # 7. Sessions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """)

    # Seed Admin User if not exists
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_pass_hash = hash_password("qwertyuiolkjhgfdsxcv")
        cursor.execute("""
            INSERT INTO users (username, password_hash, full_name, role)
            VALUES (?, ?, ?, ?)
        """, ("admin", admin_pass_hash, "System Administrator", "ADMIN"))

    # Seed Regular Guest User if not exists
    cursor.execute("SELECT id FROM users WHERE username = 'guest_user'")
    if not cursor.fetchone():
        user_pass_hash = hash_password("UserPassword123!")
        cursor.execute("""
            INSERT INTO users (username, password_hash, full_name, role)
            VALUES (?, ?, ?, ?)
        """, ("guest_user", user_pass_hash, "Standard Mobile User", "USER"))

    conn.commit()
    conn.close()

def apply_retention_policy():
    """Prunes connection and audit records beyond retention limits to prevent unbounded growth."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM connection_history WHERE id NOT IN (
                SELECT id FROM connection_history ORDER BY id DESC LIMIT ?
            )
        """, (MAX_RETENTION_RECORDS,))

        cursor.execute("""
            DELETE FROM login_records WHERE id NOT IN (
                SELECT id FROM login_records ORDER BY id DESC LIMIT ?
            )
        """, (MAX_RETENTION_RECORDS,))

        cursor.execute("""
            DELETE FROM screen_share_audit WHERE id NOT IN (
                SELECT id FROM screen_share_audit ORDER BY id DESC LIMIT ?
            )
        """, (MAX_RETENTION_RECORDS,))

        cursor.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[RETENTION] Pruning error: {e}")

# ---------------------------------------------------------
# Telemetry: Device Type, OS, Browser & Version Parsing
# ---------------------------------------------------------
def parse_device_info(user_agent_str):
    ua = user_agent_str or ""

    # 1. Device Type
    device_type = "Laptop / Desktop"
    if re.search(r'iPad|Tablet|PlayBook|Silk', ua, re.I):
        device_type = "Tablet"
    elif re.search(r'Mobile|Android|iPhone|iPod|BlackBerry|IEMobile|Opera Mini', ua, re.I):
        device_type = "Mobile Phone"

    # 2. Operating System
    os_name = "Unknown OS"
    if "Windows NT 10.0" in ua or "Windows NT 11.0" in ua:
        os_name = "Windows 10/11"
    elif "Windows NT 6.3" in ua:
        os_name = "Windows 8.1"
    elif "Windows NT 6.1" in ua:
        os_name = "Windows 7"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "iPhone OS" in ua:
        m = re.search(r'iPhone OS (\d+[_\d]*)', ua)
        os_name = f"iOS {m.group(1).replace('_', '.')}" if m else "iOS (iPhone)"
    elif "iPad; CPU OS" in ua:
        m = re.search(r'CPU OS (\d+[_\d]*)', ua)
        os_name = f"iPadOS {m.group(1).replace('_', '.')}" if m else "iPadOS"
    elif "Android" in ua:
        m = re.search(r'Android (\d+(\.\d+)?)', ua)
        os_name = f"Android {m.group(1)}" if m else "Android"
    elif "Macintosh" in ua or "Mac OS X" in ua:
        m = re.search(r'Mac OS X (\d+[_\d]*)', ua)
        os_name = f"macOS {m.group(1).replace('_', '.')}" if m else "macOS"
    elif "Linux" in ua:
        os_name = "Linux"

    # 3. Browser Name & Browser Version
    browser_name = "Standard Browser"
    browser_version = "Unknown"

    if "Edg/" in ua:
        browser_name = "Microsoft Edge"
        m = re.search(r'Edg/([0-9.]+)', ua)
        if m: browser_version = m.group(1)
    elif "SamsungBrowser/" in ua:
        browser_name = "Samsung Internet"
        m = re.search(r'SamsungBrowser/([0-9.]+)', ua)
        if m: browser_version = m.group(1)
    elif "OPR/" in ua or "Opera/" in ua:
        browser_name = "Opera"
        m = re.search(r'(?:OPR|Opera)/([0-9.]+)', ua)
        if m: browser_version = m.group(1)
    elif "Firefox/" in ua:
        browser_name = "Mozilla Firefox"
        m = re.search(r'Firefox/([0-9.]+)', ua)
        if m: browser_version = m.group(1)
    elif "Chrome/" in ua and "Safari/" in ua:
        browser_name = "Google Chrome"
        m = re.search(r'Chrome/([0-9.]+)', ua)
        if m: browser_version = m.group(1)
    elif "Safari/" in ua and "Version/" in ua:
        browser_name = "Apple Safari"
        m = re.search(r'Version/([0-9.]+)', ua)
        if m: browser_version = m.group(1)
    elif "Safari/" in ua:
        browser_name = "Apple Safari"

    return {
        "device_type": device_type,
        "os_name": os_name,
        "browser_name": browser_name,
        "browser_version": browser_version
    }

# ---------------------------------------------------------
# Real-Time Device Registry & Server-Sent Events (SSE) Broker
# ---------------------------------------------------------
CONNECTED_DEVICES = {}
DEVICE_TIMEOUT = 25  # seconds for active online status
DEVICE_AWAY_TIMEOUT = 45 # seconds before considered disconnected

SCREEN_SESSIONS = {}

# Thread-safe SSE client subscription manager
SSE_SUBSCRIBERS = set()
SSE_LOCK = threading.Lock()

def broadcast_sse(event_type, payload):
    """Broadcasts a real-time event to all connected admin SSE clients."""
    data_str = json.dumps({"type": event_type, "payload": payload})
    msg = f"event: {event_type}\ndata: {data_str}\n\n".encode("utf-8")
    
    with SSE_LOCK:
        dead_queues = []
        for q in list(SSE_SUBSCRIBERS):
            try:
                q.put_nowait(msg)
            except (queue.Full, Exception):
                dead_queues.append(q)
        for dead in dead_queues:
            SSE_SUBSCRIBERS.discard(dead)

def format_utc_ts(ts):
    if not ts: return "-"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")

def check_device_enrollment(device_id):
    """Checks if a device is enrolled in the SQLite database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT hostname, status FROM enrolled_devices WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        conn.close()
        if row and row[1] == 'active':
            return True, row[0]
        return False, None
    except Exception:
        return False, None

def get_or_register_device(device_id, ip, user_agent, client_telemetry=None, is_managed=False, hostname=None):
    now = time.time()
    parsed = parse_device_info(user_agent)
    is_new = device_id not in CONNECTED_DEVICES

    if not is_managed:
        is_managed, db_hostname = check_device_enrollment(device_id)
        if is_managed:
            hostname = db_hostname

    if is_new:
        CONNECTED_DEVICES[device_id] = {
            "device_id": device_id,
            "hostname": hostname or device_id,
            "is_managed": is_managed,
            "ip_address": ip,
            "device_type": parsed["device_type"],
            "os_name": parsed["os_name"],
            "browser_name": parsed["browser_name"],
            "browser_version": parsed["browser_version"],
            "user_agent": (user_agent or "Unknown")[:140],
            "first_seen": now,
            "first_seen_utc": format_utc_ts(now),
            "last_seen": now,
            "last_seen_utc": format_utc_ts(now),
            "status": "online",
            "login_status": ("Managed Agent" if is_managed else "Public Visitor"),
            "pending_request": None,
            "active_session": None,
            "event_queue": [],
            "screen_res": (client_telemetry or {}).get("screen_res", "-")
        }

        # Record in connection history table
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO connection_history (
                    device_id, device_type, os_name, browser_name, browser_version,
                    ip_address, connected_at, last_activity_at, status, login_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, parsed["device_type"], parsed["os_name"],
                parsed["browser_name"], parsed["browser_version"],
                ip, format_utc_ts(now), format_utc_ts(now), "online",
                ("Managed Agent" if is_managed else "Public Visitor")
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB] Error recording connection: {e}")

    else:
        dev = CONNECTED_DEVICES[device_id]
        dev["last_seen"] = now
        dev["last_seen_utc"] = format_utc_ts(now)
        dev["ip_address"] = ip
        dev["device_type"] = parsed["device_type"]
        dev["os_name"] = parsed["os_name"]
        dev["browser_name"] = parsed["browser_name"]
        dev["browser_version"] = parsed["browser_version"]
        if is_managed:
            dev["is_managed"] = True
            dev["hostname"] = hostname or dev.get("hostname", device_id)
            dev["login_status"] = "Managed Agent"
        if client_telemetry and "screen_res" in client_telemetry:
            dev["screen_res"] = client_telemetry["screen_res"]

        if dev["status"] in ["disconnected", "away"]:
            dev["status"] = "online"

    return CONNECTED_DEVICES[device_id], is_new

def get_devices_summary():
    now = time.time()
    devices_list = []
    
    for d_id, d in list(CONNECTED_DEVICES.items()):
        elapsed = now - d["last_seen"]
        
        if d.get("status") == "sharing":
            status = "sharing"
        elif d.get("status") == "request_pending":
            status = "request_pending"
        elif elapsed <= DEVICE_TIMEOUT:
            status = "online"
        elif elapsed <= DEVICE_AWAY_TIMEOUT:
            status = "away"
        else:
            status = "disconnected"

        d["status"] = status
        
        if elapsed < 4:
            activity_str = "Just now"
        elif elapsed < 60:
            activity_str = f"{int(elapsed)}s ago"
        elif elapsed < 3600:
            activity_str = f"{int(elapsed // 60)}m ago"
        else:
            activity_str = f"{int(elapsed // 3600)}h ago"

        devices_list.append({
            "device_id": d["device_id"],
            "hostname": d.get("hostname", d["device_id"]),
            "is_managed": bool(d.get("is_managed", False)),
            "ip_address": d["ip_address"],
            "device_type": d["device_type"],
            "os_name": d["os_name"],
            "browser_name": d["browser_name"],
            "browser_version": d["browser_version"],
            "first_seen_utc": d["first_seen_utc"],
            "last_seen_utc": d["last_seen_utc"],
            "last_activity": activity_str,
            "login_status": d.get("login_status", "Public Visitor"),
            "status": status,
            "screen_res": d.get("screen_res", "-"),
            "active_session": d.get("active_session")
        })

    # Sort: managed online first, then unmanaged, then disconnected
    def sort_key(x):
        stat_rank = {"sharing": 0, "request_pending": 1, "online": 2, "away": 3, "disconnected": 4}.get(x["status"], 5)
        managed_rank = 0 if x["is_managed"] else 1
        return (managed_rank, stat_rank, x["device_id"])

    devices_list.sort(key=sort_key)
    return devices_list

def get_dashboard_metrics():
    now = time.time()
    online_count = sum(1 for d in CONNECTED_DEVICES.values() if now - d["last_seen"] <= DEVICE_TIMEOUT)
    total_tracked = len(CONNECTED_DEVICES)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM connection_history")
    total_connections = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM enrolled_devices WHERE status = 'active'")
    enrolled_devices_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE expires_at > ?", (now,))
    active_sessions = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM login_records WHERE status = 'SUCCESS'")
    successful_logins = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM screen_share_audit WHERE status = 'ACCEPTED'")
    screens_shared = cursor.fetchone()[0]
    conn.close()

    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    return {
        "system_status": "Healthy & Secure",
        "online_devices": online_count,
        "enrolled_devices": enrolled_devices_count,
        "total_connections": total_connections,
        "active_sessions": active_sessions,
        "successful_logins": successful_logins,
        "screens_shared": screens_shared,
        "total_tracked": total_tracked,
        "server_time": now_utc_str
    }

# ---------------------------------------------------------
# Background Inactivity & Disconnect Watcher Daemon
# ---------------------------------------------------------
def background_device_monitor():
    """Watches devices for inactivity/disconnections and broadcasts SSE updates."""
    last_retention_check = time.time()

    while True:
        time.sleep(3.5)
        now = time.time()
        state_changed = False

        for d_id, d in list(CONNECTED_DEVICES.items()):
            prev_status = d.get("status")
            elapsed = now - d["last_seen"]

            if prev_status == "sharing":
                continue

            if elapsed > DEVICE_AWAY_TIMEOUT and prev_status != "disconnected":
                d["status"] = "disconnected"
                state_changed = True
            elif elapsed > DEVICE_TIMEOUT and prev_status == "online":
                d["status"] = "away"
                state_changed = True

        # Prune very old offline visitor devices from memory (> 2 hours), but keep enrolled devices
        for d_id, d in list(CONNECTED_DEVICES.items()):
            if not d.get("is_managed") and (now - d["last_seen"] > 7200):
                del CONNECTED_DEVICES[d_id]
                state_changed = True

        if state_changed:
            broadcast_sse("devices_update", {
                "devices": get_devices_summary(),
                "metrics": get_dashboard_metrics()
            })

        # Run retention policy every 5 minutes
        if now - last_retention_check > 300:
            apply_retention_policy()
            last_retention_check = now

# ---------------------------------------------------------
# Audit Logger & Database Record Writer
# ---------------------------------------------------------
def record_login_audit(username, role, status, ip, user_agent, details=""):
    timestamp = datetime.now(timezone.utc).isoformat()
    dev_info = parse_device_info(user_agent)
    clean_ua = (user_agent or "Unknown")[:120].replace(",", ";")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO login_records (
                username, role, status, ip_address, 
                device_type, os_name, browser_name, 
                user_agent, timestamp_utc, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            username or "anonymous",
            role or "NONE",
            status,
            ip,
            dev_info["device_type"],
            dev_info["os_name"],
            f"{dev_info['browser_name']} {dev_info['browser_version']}",
            clean_ua,
            timestamp,
            details
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB audit write error: {e}")

def record_screen_audit(session_id, admin_user, device_id, status, started_at=None, ended_at=None, details=""):
    timestamp = datetime.now(timezone.utc).isoformat()
    dev = CONNECTED_DEVICES.get(device_id, {})

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM screen_share_audit WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()

        target_name = dev.get("hostname", device_id)

        if not row:
            cursor.execute("""
                INSERT INTO screen_share_audit (
                    session_id, admin_username, target_device_id,
                    device_type, os_name, browser_name, ip_address,
                    status, requested_at, started_at, ended_at, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                admin_user,
                target_name,
                dev.get("device_type", "Unknown"),
                dev.get("os_name", "Unknown"),
                f"{dev.get('browser_name', 'Unknown')} {dev.get('browser_version', '')}",
                dev.get("ip_address", "Unknown"),
                status,
                timestamp,
                started_at,
                ended_at,
                details
            ))
        else:
            update_clauses = ["status = ?", "details = ?"]
            params = [status, details]
            if started_at:
                update_clauses.append("started_at = ?")
                params.append(started_at)
            if ended_at:
                update_clauses.append("ended_at = ?")
                params.append(ended_at)
            params.append(session_id)

            cursor.execute(f"UPDATE screen_share_audit SET {', '.join(update_clauses)} WHERE session_id = ?", params)

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Screen audit error: {e}")

# ---------------------------------------------------------
# Session Management
# ---------------------------------------------------------
SESSION_LIFETIME = 3600 * 8  # 8 hours

def create_session(username, role):
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + SESSION_LIFETIME
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO sessions (session_token, username, role, expires_at)
        VALUES (?, ?, ?, ?)
    """, (token, username, role, expires_at))
    conn.commit()
    conn.close()
    return token

def get_session(token):
    if not token:
        return None
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT username, role, expires_at FROM sessions WHERE session_token = ?", (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    username, role, expires_at = row
    if time.time() > expires_at:
        destroy_session(token)
        return None

    return {"username": username, "role": role, "expires_at": expires_at}

def destroy_session(token):
    if not token:
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
    conn.commit()
    conn.close()

# ---------------------------------------------------------
# Login Rate Limiting (5 failed attempts per 5 minutes per IP)
# ---------------------------------------------------------
FAILED_LOGINS = {}
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 300

def is_rate_limited(ip):
    now = time.time()
    attempts = [t for t in FAILED_LOGINS.get(ip, []) if now - t < RATE_LIMIT_WINDOW]
    FAILED_LOGINS[ip] = attempts
    return len(attempts) >= RATE_LIMIT_MAX

def record_failed_login(ip):
    now = time.time()
    if ip not in FAILED_LOGINS:
        FAILED_LOGINS[ip] = []
    FAILED_LOGINS[ip].append(now)

def clear_failed_logins(ip):
    if ip in FAILED_LOGINS:
        del FAILED_LOGINS[ip]

# ---------------------------------------------------------
# Threaded HTTP Server Handler
# ---------------------------------------------------------
class PortalServerHandler(http.server.BaseHTTPRequestHandler):

    def get_client_ip(self):
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0]

    def get_session_token(self):
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        cookies = urllib.parse.parse_qs(cookie_header.replace(" ", ""))
        tokens = cookies.get("session_id")
        return tokens[0] if tokens else None

    def authenticate(self, required_role=None):
        token = self.get_session_token()
        session = get_session(token)
        if not session:
            return None, "UNAUTHENTICATED"
        if required_role and session.get("role") != required_role:
            return session, "FORBIDDEN"
        return session, "AUTHORIZED"

    def send_json(self, status_code, data, extra_headers=None):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def serve_file(self, file_path, content_type="text/html"):
        if not os.path.exists(file_path):
            self.send_error(404, "File Not Found")
            return
        with open(file_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(content)

    # -----------------------------------------------------
    # GET Handlers
    # -----------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        client_ip = self.get_client_ip()
        ua = self.headers.get("User-Agent", "")

        # 1. Device Heartbeat / Event Polling (Public / Unmanaged)
        if path == "/api/device/poll":
            device_id = query.get("device_id", [None])[0]
            if not device_id:
                self.send_json(400, {"error": "device_id required"})
                return

            dev, is_new = get_or_register_device(device_id, client_ip, ua)
            
            event = None
            if dev["event_queue"]:
                event = dev["event_queue"].pop(0)

            self.send_json(200, {
                "status": "ok",
                "device_id": device_id,
                "is_managed": bool(dev.get("is_managed", False)),
                "event": event
            })
            return

        # 2. Server-Sent Events (SSE) Real-Time Stream (ADMIN ONLY)
        if path == "/api/admin/events-stream":
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status != "AUTHORIZED":
                self.send_json(403 if auth_status == "FORBIDDEN" else 401, {"error": "Access Denied"})
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            client_queue = queue.Queue(maxsize=50)
            with SSE_LOCK:
                SSE_SUBSCRIBERS.add(client_queue)

            try:
                # Push initial snapshot immediately
                init_msg = json.dumps({
                    "type": "devices_update",
                    "payload": {
                        "devices": get_devices_summary(),
                        "metrics": get_dashboard_metrics()
                    }
                })
                self.wfile.write(f"event: devices_update\ndata: {init_msg}\n\n".encode("utf-8"))
                self.wfile.flush()

                while True:
                    try:
                        msg = client_queue.get(timeout=12)
                        self.wfile.write(msg)
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()

            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                with SSE_LOCK:
                    SSE_SUBSCRIBERS.discard(client_queue)
            return

        # 3. Verify Enrollment Token (Public - called by /enroll)
        if path == "/api/enroll/verify":
            token = query.get("token", [None])[0]
            if not token:
                self.send_json(400, {"error": "Token required"})
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT policy_name, expires_at, is_used FROM enrollment_tokens WHERE token = ?", (token,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                self.send_json(404, {"error": "Enrollment link not found or invalid"})
                return

            policy_name, expires_at, is_used = row
            if is_used:
                self.send_json(400, {"error": "This enrollment link has already been used"})
                return
            if time.time() > expires_at:
                self.send_json(400, {"error": "This enrollment link has expired"})
                return

            self.send_json(200, {
                "valid": True,
                "policy_name": policy_name
            })
            return

        # 4. WebRTC Signal Polling
        if path == "/api/webrtc/signal":
            session_id = query.get("session_id", [None])[0]
            role = query.get("role", [None])[0]

            if not session_id or session_id not in SCREEN_SESSIONS:
                self.send_json(404, {"error": "Session not found"})
                return

            sess = SCREEN_SESSIONS[session_id]

            if role == "admin":
                candidates = sess["candidates_user"]
                sess["candidates_user"] = []
                self.send_json(200, {
                    "session_id": session_id,
                    "status": sess["status"],
                    "offer": sess.get("offer"),
                    "candidates": candidates
                })
                return
            elif role == "user":
                candidates = sess["candidates_admin"]
                sess["candidates_admin"] = []
                self.send_json(200, {
                    "session_id": session_id,
                    "status": sess["status"],
                    "answer": sess.get("answer"),
                    "candidates": candidates
                })
                return

            self.send_json(400, {"error": "Invalid role"})
            return

        # 5. Protected API: Admin Connected Devices List (ADMIN ONLY)
        if path == "/api/admin/devices":
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status != "AUTHORIZED":
                self.send_json(403 if auth_status == "FORBIDDEN" else 401, {"error": "Access Denied"})
                return

            devices_list = get_devices_summary()
            self.send_json(200, {"devices": devices_list})
            return

        # 6. Protected API: Screen Share Audit History (ADMIN ONLY)
        if path == "/api/admin/screen-audit":
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status != "AUTHORIZED":
                self.send_json(403 if auth_status == "FORBIDDEN" else 401, {"error": "Access Denied"})
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT session_id, admin_username, target_device_id, device_type, 
                       os_name, browser_name, ip_address, status, requested_at, 
                       started_at, ended_at, details
                FROM screen_share_audit ORDER BY id DESC LIMIT 50
            """)
            rows = cursor.fetchall()
            conn.close()

            history = []
            for r in rows:
                history.append({
                    "session_id": r[0],
                    "admin": r[1],
                    "device_id": r[2],
                    "device_type": r[3],
                    "os": r[4],
                    "browser": r[5],
                    "ip": r[6],
                    "status": r[7],
                    "requested_at": r[8],
                    "started_at": r[9],
                    "ended_at": r[10],
                    "details": r[11]
                })
            self.send_json(200, {"audit": history})
            return

        # 7. Protected API: Admin Dashboard Stats (ADMIN ONLY)
        if path == "/api/admin/dashboard":
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status != "AUTHORIZED":
                self.send_json(403 if auth_status == "FORBIDDEN" else 401, {"error": "Access Denied"})
                return

            metrics = get_dashboard_metrics()
            self.send_json(200, metrics)
            return

        # 8. Protected API: Login Audit Records (ADMIN ONLY)
        if path == "/api/admin/login-records":
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status != "AUTHORIZED":
                self.send_json(403 if auth_status == "FORBIDDEN" else 401, {"error": "Access Denied"})
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, username, role, status, ip_address, 
                       device_type, os_name, browser_name, timestamp_utc, details
                FROM login_records ORDER BY id DESC LIMIT 50
            """)
            rows = cursor.fetchall()
            conn.close()

            records = []
            for r in rows:
                records.append({
                    "id": r[0], "username": r[1], "role": r[2], "status": r[3],
                    "ip_address": r[4], "device_type": r[5], "os_name": r[6],
                    "browser_name": r[7], "timestamp": r[8], "details": r[9]
                })

            self.send_json(200, {"records": records})
            return

        # 9. Protected API: Historical Connection Records (ADMIN ONLY)
        if path == "/api/admin/connection-history":
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status != "AUTHORIZED":
                self.send_json(403 if auth_status == "FORBIDDEN" else 401, {"error": "Access Denied"})
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, device_id, device_type, os_name, browser_name, browser_version, 
                       ip_address, connected_at, last_activity_at, status, login_status
                FROM connection_history ORDER BY id DESC LIMIT 50
            """)
            rows = cursor.fetchall()
            conn.close()

            history = []
            for r in rows:
                history.append({
                    "id": r[0],
                    "device_id": r[1],
                    "device_type": r[2],
                    "os_name": r[3],
                    "browser": f"{r[4]} {r[5]}",
                    "ip_address": r[6],
                    "connected_at": r[7],
                    "last_activity_at": r[8],
                    "status": r[9],
                    "login_status": r[10]
                })

            self.send_json(200, {"history": history})
            return

        # 10. API: Current User Profile
        if path == "/api/auth/me":
            session, auth_status = self.authenticate()
            if auth_status == "UNAUTHENTICATED":
                self.send_json(401, {"authenticated": False})
                return
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT full_name FROM users WHERE username = ?", (session["username"],))
            row = cursor.fetchone()
            conn.close()
            self.send_json(200, {
                "authenticated": True,
                "username": session["username"],
                "role": session["role"],
                "full_name": row[0] if row else session["username"]
            })
            return

        # 10. Device Enrollment Page
        if path in ["/enroll", "/enroll.html"]:
            self.serve_file(os.path.join(PUBLIC_DIR, "enroll.html"), "text/html")
            return

        # 11. Protected Admin Dashboard Page
        if path in ["/admin", "/admin.html"]:
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status == "UNAUTHENTICATED":
                self.send_response(302)
                self.send_header("Location", "/?access=login_required")
                self.end_headers()
                return
            if auth_status == "FORBIDDEN":
                record_login_audit(session["username"], session["role"], "FORBIDDEN", client_ip, ua, "Blocked from /admin page")
                self.serve_file(os.path.join(PUBLIC_DIR, "unauthorized.html"), "text/html")
                return

            self.serve_file(os.path.join(PUBLIC_DIR, "admin.html"), "text/html")
            return

        # 12. Static Files
        if path in ["/", "/index.html"]:
            self.serve_file(os.path.join(PUBLIC_DIR, "index.html"), "text/html")
            return
        elif path == "/css/style.css":
            self.serve_file(os.path.join(PUBLIC_DIR, "css", "style.css"), "text/css")
            return
        elif path == "/js/app.js":
            self.serve_file(os.path.join(PUBLIC_DIR, "js", "app.js"), "application/javascript")
            return
        elif path == "/unauthorized.html":
            self.serve_file(os.path.join(PUBLIC_DIR, "unauthorized.html"), "text/html")
            return

        self.send_error(404, "Page Not Found")

    # -----------------------------------------------------
    # POST Handlers
    # -----------------------------------------------------
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        client_ip = self.get_client_ip()
        ua = self.headers.get("User-Agent", "")

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            body = {}

        # 1. Admin Generates Secure Device Enrollment Link (ADMIN ONLY)
        if path == "/api/admin/generate-enrollment-token":
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status != "AUTHORIZED":
                self.send_json(403 if auth_status == "FORBIDDEN" else 401, {"error": "Access Denied"})
                return

            token = secrets.token_urlsafe(24)
            policy_name = body.get("policy_name", "Standard Organization Management Policy")
            now_iso = datetime.now(timezone.utc).isoformat()
            expires_at = time.time() + (3600 * 48) # 48 hours validity

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO enrollment_tokens (token, created_by, policy_name, created_at, expires_at, is_used)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (token, session["username"], policy_name, now_iso, expires_at))
            conn.commit()
            conn.close()

            # Build full enrollment URL
            host = self.headers.get("Host") or f"localhost:{PORT}"
            enroll_url = f"http://{host}/enroll?token={token}"

            self.send_json(200, {
                "token": token,
                "enroll_url": enroll_url,
                "expires_at": expires_at,
                "policy_name": policy_name
            })
            return

        # 2. Device Submits Enrollment Approval (/enroll)
        if path == "/api/enroll/approve":
            token = body.get("token")
            hostname = body.get("hostname", "").strip() or ("Host-" + secrets.token_hex(3))
            client_telemetry = body.get("telemetry") or {}

            if not token:
                self.send_json(400, {"error": "Enrollment token required"})
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT created_by, policy_name, expires_at, is_used FROM enrollment_tokens WHERE token = ?", (token,))
            row = cursor.fetchone()

            if not row or row[3] or (time.time() > row[2]):
                conn.close()
                self.send_json(400, {"error": "Invalid or expired enrollment token"})
                return

            created_by, policy_name, _, _ = row

            device_id = "mdev_" + secrets.token_hex(6)
            device_auth_token = secrets.token_urlsafe(32)
            parsed = parse_device_info(ua)
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            # Save enrolled managed device
            cursor.execute("""
                INSERT OR REPLACE INTO enrolled_devices (
                    device_id, device_auth_token, hostname, device_type, os_name,
                    browser_name, browser_version, ip_address, enrolled_at,
                    policy_agreed_at, status, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, device_auth_token, hostname, parsed["device_type"],
                parsed["os_name"], parsed["browser_name"], parsed["browser_version"],
                client_ip, now_str, now_str, "active", now_str
            ))

            # Mark token as used
            cursor.execute("UPDATE enrollment_tokens SET is_used = 1, used_by_device_id = ? WHERE token = ?", (device_id, token))
            conn.commit()
            conn.close()

            # Register in active memory registry
            get_or_register_device(device_id, client_ip, ua, client_telemetry, is_managed=True, hostname=hostname)

            # Broadcast SSE update to dashboard
            broadcast_sse("devices_update", {
                "devices": get_devices_summary(),
                "metrics": get_dashboard_metrics()
            })

            record_screen_audit("enroll_" + device_id, created_by, device_id, "ENROLLED", details=f"Approved enrollment for {hostname}")

            self.send_json(200, {
                "message": "Device successfully enrolled under organization policy",
                "device_id": device_id,
                "device_auth_token": device_auth_token,
                "hostname": hostname
            })
            return

        # 3. Managed Device Heartbeat (Routine automatic reconnection without user prompts)
        if path == "/api/managed-device/heartbeat":
            device_id = body.get("device_id")
            device_auth_token = body.get("device_auth_token")
            hostname = body.get("hostname")
            client_telemetry = body.get("telemetry")

            if not device_id or not device_auth_token:
                self.send_json(400, {"error": "Credentials required"})
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT hostname, status FROM enrolled_devices WHERE device_id = ? AND device_auth_token = ?", (device_id, device_auth_token))
            row = cursor.fetchone()
            conn.close()

            if not row or row[1] != 'active':
                self.send_json(401, {"error": "Device enrollment revoked or invalid", "revoked": True})
                return

            db_hostname = row[0]
            dev, _ = get_or_register_device(device_id, client_ip, ua, client_telemetry, is_managed=True, hostname=db_hostname)

            event = None
            if dev["event_queue"]:
                event = dev["event_queue"].pop(0)

            self.send_json(200, {
                "status": "ok",
                "enrolled": True,
                "hostname": db_hostname,
                "event": event
            })
            return

        # 4. Automatic Device Registration / Connection Ping (Public Visitor)
        if path == "/api/device/register":
            device_id = body.get("device_id") or ("dev_" + secrets.token_hex(6))
            client_telemetry = {
                "screen_res": body.get("screen_res", "-"),
                "touch": body.get("touch", False)
            }
            dev, is_new = get_or_register_device(device_id, client_ip, ua, client_telemetry)

            broadcast_sse("devices_update", {
                "devices": get_devices_summary(),
                "metrics": get_dashboard_metrics()
            })

            self.send_json(200, {
                "device_id": device_id,
                "is_managed": bool(dev.get("is_managed", False)),
                "ip_address": client_ip,
                "device_type": dev["device_type"],
                "os": dev["os_name"],
                "browser": dev["browser_name"],
                "browser_version": dev["browser_version"],
                "first_seen": dev["first_seen_utc"],
                "status": dev["status"]
            })
            return

        # 5. Admin Initiates Screen-View / Assistance Request (ADMIN ONLY)
        if path == "/api/admin/request-screen":
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status != "AUTHORIZED":
                self.send_json(403 if auth_status == "FORBIDDEN" else 401, {"error": "Access Denied"})
                return

            target_device_id = body.get("device_id")
            if not target_device_id or target_device_id not in CONNECTED_DEVICES:
                self.send_json(404, {"error": "Target device is not currently connected."})
                return

            dev = CONNECTED_DEVICES[target_device_id]
            if time.time() - dev["last_seen"] > DEVICE_TIMEOUT:
                self.send_json(400, {"error": "Device is offline or disconnected."})
                return

            session_id = secrets.token_hex(16)
            admin_user = session["username"]

            SCREEN_SESSIONS[session_id] = {
                "session_id": session_id,
                "admin_user": admin_user,
                "device_id": target_device_id,
                "status": "PENDING",
                "offer": None,
                "answer": None,
                "candidates_admin": [],
                "candidates_user": [],
                "created_at": time.time()
            }

            dev["status"] = "request_pending"
            dev["pending_request"] = session_id

            # If device is pre-enrolled under organization policy, route as managed_screen_assist!
            is_managed = bool(dev.get("is_managed", False))
            event_type = "managed_screen_assist" if is_managed else "screen_view_request"

            dev["event_queue"].append({
                "type": event_type,
                "session_id": session_id,
                "admin_user": admin_user,
                "is_managed": is_managed,
                "reason": "Organization administrative remote screen assistance"
            })

            record_screen_audit(session_id, admin_user, target_device_id, "REQUESTED", details=("Direct Assist under Org Policy" if is_managed else "Admin sent screen view request"))

            broadcast_sse("devices_update", {
                "devices": get_devices_summary(),
                "metrics": get_dashboard_metrics()
            })

            self.send_json(200, {
                "message": ("Direct assist sent to managed device" if is_managed else "Screen request sent to visitor"),
                "session_id": session_id,
                "device_id": target_device_id,
                "is_managed": is_managed,
                "status": "PENDING"
            })
            return

        # 6. Admin Revokes Device Enrollment (ADMIN ONLY)
        if path == "/api/admin/revoke-device":
            session, auth_status = self.authenticate(required_role="ADMIN")
            if auth_status != "AUTHORIZED":
                self.send_json(403 if auth_status == "FORBIDDEN" else 401, {"error": "Access Denied"})
                return

            device_id = body.get("device_id")
            if not device_id:
                self.send_json(400, {"error": "device_id required"})
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE enrolled_devices SET status = 'revoked' WHERE device_id = ?", (device_id,))
            conn.commit()
            conn.close()

            if device_id in CONNECTED_DEVICES:
                CONNECTED_DEVICES[device_id]["is_managed"] = False
                CONNECTED_DEVICES[device_id]["login_status"] = "Revoked"
                CONNECTED_DEVICES[device_id]["event_queue"].append({"type": "enrollment_revoked"})

            broadcast_sse("devices_update", {
                "devices": get_devices_summary(),
                "metrics": get_dashboard_metrics()
            })

            self.send_json(200, {"message": f"Device {device_id} enrollment revoked"})
            return

        # 7. User Device Responds to Screen Request
        if path == "/api/screen-request/respond":
            device_id = body.get("device_id")
            session_id = body.get("session_id")
            accepted = bool(body.get("accepted"))
            reason = body.get("reason", "")

            if not session_id or session_id not in SCREEN_SESSIONS:
                self.send_json(404, {"error": "Screen session not found or expired"})
                return

            sess = SCREEN_SESSIONS[session_id]
            dev = CONNECTED_DEVICES.get(device_id)

            if accepted:
                sess["status"] = "ACCEPTED"
                if dev:
                    dev["status"] = "sharing"
                    dev["active_session"] = session_id
                now_utc = datetime.now(timezone.utc).isoformat()
                record_screen_audit(session_id, sess["admin_user"], device_id, "ACCEPTED", started_at=now_utc, details="Screen session active under policy")
            else:
                sess["status"] = "DECLINED"
                if dev:
                    dev["status"] = "online"
                    dev["pending_request"] = None
                record_screen_audit(session_id, sess["admin_user"], device_id, "DECLINED", details=f"User declined: {reason}")

            broadcast_sse("devices_update", {
                "devices": get_devices_summary(),
                "metrics": get_dashboard_metrics()
            })
            broadcast_sse("screen_update", {"session_id": session_id, "status": sess["status"]})

            self.send_json(200, {"session_id": session_id, "status": sess["status"]})
            return

        # 8. WebRTC Signaling: Post SDP Offer / Answer / ICE Candidate
        if path == "/api/webrtc/signal":
            session_id = body.get("session_id")
            role = body.get("role")
            signal_type = body.get("type")

            if not session_id or session_id not in SCREEN_SESSIONS:
                self.send_json(404, {"error": "Session expired or invalid"})
                return

            sess = SCREEN_SESSIONS[session_id]

            if signal_type == "offer" and role == "user":
                sess["offer"] = body.get("offer")
                self.send_json(200, {"status": "offer_saved"})
                return

            elif signal_type == "answer" and role == "admin":
                sess["answer"] = body.get("answer")
                self.send_json(200, {"status": "answer_saved"})
                return

            elif signal_type == "candidate":
                candidate = body.get("candidate")
                if candidate:
                    if role == "user":
                        sess["candidates_user"].append(candidate)
                    elif role == "admin":
                        sess["candidates_admin"].append(candidate)
                self.send_json(200, {"status": "candidate_appended"})
                return

            self.send_json(400, {"error": "Invalid signaling payload"})
            return

        # 9. End WebRTC Screen Sharing Session
        if path == "/api/webrtc/end":
            session_id = body.get("session_id")

            if session_id and session_id in SCREEN_SESSIONS:
                sess = SCREEN_SESSIONS[session_id]
                sess["status"] = "ENDED"
                dev_id = sess["device_id"]
                if dev_id in CONNECTED_DEVICES:
                    CONNECTED_DEVICES[dev_id]["status"] = "online"
                    CONNECTED_DEVICES[dev_id]["active_session"] = None
                    CONNECTED_DEVICES[dev_id]["pending_request"] = None

                now_utc = datetime.now(timezone.utc).isoformat()
                record_screen_audit(session_id, sess["admin_user"], dev_id, "ENDED", ended_at=now_utc, details="Screen session terminated")

                broadcast_sse("devices_update", {
                    "devices": get_devices_summary(),
                    "metrics": get_dashboard_metrics()
                })
                broadcast_sse("screen_update", {"session_id": session_id, "status": "ENDED"})

                self.send_json(200, {"message": "Screen sharing session ended"})
                return

            self.send_json(200, {"message": "Session cleaned up"})
            return

        # 10. API: Login with Rate Limiting
        if path == "/api/auth/login":
            if is_rate_limited(client_ip):
                record_login_audit(body.get("username", "unknown"), "NONE", "RATE_LIMITED", client_ip, ua, "Blocked by rate limiter")
                self.send_json(429, {"error": "Too many failed attempts. Please wait 5 minutes."})
                return

            username = body.get("username", "").strip()
            password = body.get("password", "").strip()
            device_id = body.get("device_id")

            if not username or not password:
                self.send_json(400, {"error": "Username and password required"})
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash, full_name, role FROM users WHERE username = ?", (username,))
            user_row = cursor.fetchone()
            conn.close()

            if not user_row or not verify_password(user_row[0], password):
                record_failed_login(client_ip)
                record_login_audit(username, "NONE", "FAILED", client_ip, ua, "Invalid password/username")
                self.send_json(401, {"error": "Invalid username or password"})
                return

            clear_failed_logins(client_ip)
            full_name = user_row[1]
            role = user_row[2]
            session_token = create_session(username, role)
            record_login_audit(username, role, "SUCCESS", client_ip, ua, "Authentication successful")

            if device_id and device_id in CONNECTED_DEVICES:
                CONNECTED_DEVICES[device_id]["login_status"] = f"{username} ({role})"
                broadcast_sse("devices_update", {
                    "devices": get_devices_summary(),
                    "metrics": get_dashboard_metrics()
                })

            cookie_val = f"session_id={session_token}; Path=/; Max-Age={SESSION_LIFETIME}; HttpOnly; SameSite=Lax"
            self.send_json(200, {
                "message": "Login successful",
                "role": role,
                "username": username,
                "full_name": full_name,
                "redirect": "/admin" if role == "ADMIN" else None
            }, extra_headers={"Set-Cookie": cookie_val})
            return

        # 11. API: Logout
        if path == "/api/auth/logout":
            token = self.get_session_token()
            session = get_session(token)
            username = session["username"] if session else "unknown"
            role = session["role"] if session else "NONE"
            destroy_session(token)

            record_login_audit(username, role, "LOGOUT", client_ip, ua, "Session terminated")
            expired_cookie = "session_id=deleted; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
            self.send_json(200, {"message": "Logged out successfully"}, extra_headers={"Set-Cookie": expired_cookie})
            return

        self.send_error(404, "Endpoint Not Found")

# ---------------------------------------------------------
# Multi-Threaded HTTP Server Class
# ---------------------------------------------------------
class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

# ---------------------------------------------------------
# Server Bootstrap & Background Thread Launcher
# ---------------------------------------------------------
def run_server():
    init_db()
    apply_retention_policy()
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    os.makedirs(os.path.join(PUBLIC_DIR, "css"), exist_ok=True)
    os.makedirs(os.path.join(PUBLIC_DIR, "js"), exist_ok=True)

    monitor_thread = threading.Thread(target=background_device_monitor, daemon=True)
    monitor_thread.start()

    with ThreadedHTTPServer(("", PORT), PortalServerHandler) as httpd:
        print("=" * 65)
        print(f"[CENTRALIZED] Managed Device Portal Running on port {PORT}")
        print(f"--> Public Landing Page: http://localhost:{PORT}")
        print(f"--> Protected Admin Console: http://localhost:{PORT}/admin")
        print("=" * 65)
        print("Managed Device Workflow:")
        print("  1. Admin generates secure enrollment link in /admin")
        print("  2. Device approves enrollment once under Organization Policy")
        print("  3. Routine reconnects occur automatically without repeated prompts")
        print("  4. Admin can direct-assist and revoke devices at any time")
        print("=" * 65)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    run_server()
