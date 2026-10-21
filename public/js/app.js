/**
 * Centralized Device Management Frontend Controller
 * - Enrolled Managed Devices: Automatic reconnection without repeated approval prompts
 * - Direct Remote Screen Assist for managed devices under Organization Policy
 * - Admin Enrollment Generator: Secure link generation & one-click copy
 * - Real-Time Server-Sent Events (SSE) synchronization
 * - Public Visitors: Minimal playful landing page (😊 + Yes / No)
 */

document.addEventListener('DOMContentLoaded', () => {
  const isDashboard = window.location.pathname === '/admin' || window.location.pathname === '/admin.html';
  const isEnrollPage = window.location.pathname === '/enroll' || window.location.pathname === '/enroll.html';

  if (isDashboard) {
    initAdminDashboard();
  } else if (!isEnrollPage) {
    initSmileyInterface();
    initLoginModal();
    initClientDeviceAgent();
  }
});

// ============================================================================
// 1. PLAYFUL SMILEY INTERFACE (STRICTLY 😊 WITH YES & NO)
// ============================================================================
function initSmileyInterface() {
  const btnSmiley = document.getElementById('btnSmiley');
  const btnYes = document.getElementById('btnYes');
  const btnNo = document.getElementById('btnNo');
  const btnReset = document.getElementById('btnResetSmiley');
  const choiceRow = document.getElementById('choiceButtonsRow');
  const messageArea = document.getElementById('friendlyMessageArea');
  const messageText = document.getElementById('friendlyMessageText');

  // YES Button: Friendly response
  if (btnYes) {
    btnYes.addEventListener('click', () => {
      if (choiceRow) choiceRow.classList.add('hidden');
      if (messageArea && messageText) {
        messageText.textContent = "Yay! Hope you have a wonderful and awesome day! 🌟😊";
        messageArea.classList.remove('hidden');
      }
    });
  }

  // NO Button: Friendly comfort response
  if (btnNo) {
    btnNo.addEventListener('click', () => {
      if (choiceRow) choiceRow.classList.add('hidden');
      if (messageArea && messageText) {
        messageText.textContent = "Sending you warm smiles and positive vibes! Take it easy today! 💛";
        messageArea.classList.remove('hidden');
      }
    });
  }

  // RESET Button: Restores Yes / No options
  if (btnReset) {
    btnReset.addEventListener('click', () => {
      if (messageArea) messageArea.classList.add('hidden');
      if (choiceRow) choiceRow.classList.remove('hidden');
    });
  }

  // SMILEY EMOJI: Hidden portal entrance to Admin Login
  if (btnSmiley) {
    btnSmiley.addEventListener('click', (e) => {
      e.preventDefault();
      openLoginModal();
    });

    btnSmiley.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openLoginModal();
      }
    });
  }
}

// ============================================================================
// 2. ADMIN LOGIN MODAL
// ============================================================================
function initLoginModal() {
  const loginModal = document.getElementById('loginModal');
  const btnCloseModal = document.getElementById('btnCloseModal');
  const adminForm = document.getElementById('adminLoginForm');
  const statusBox = document.getElementById('statusMessage');

  if (btnCloseModal && loginModal) {
    btnCloseModal.addEventListener('click', () => closeLoginModal());
  }

  if (loginModal) {
    loginModal.addEventListener('click', (e) => {
      if (e.target === loginModal) closeLoginModal();
    });
  }

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && loginModal && !loginModal.classList.contains('hidden')) {
      closeLoginModal();
    }
  });

  if (adminForm) {
    adminForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const usernameInput = document.getElementById('username');
      const passwordInput = document.getElementById('password');
      const btnSubmit = document.getElementById('btnLogin');

      const username = usernameInput ? usernameInput.value.trim() : '';
      const password = passwordInput ? passwordInput.value : '';

      if (!username || !password) return;

      btnSubmit.disabled = true;
      const originalText = btnSubmit.querySelector('.btn-text') ? btnSubmit.querySelector('.btn-text').textContent : 'Sign In';
      if (btnSubmit.querySelector('.btn-text')) {
        btnSubmit.querySelector('.btn-text').textContent = 'Validating...';
      }
      if (statusBox) statusBox.classList.add('hidden');

      try {
        const response = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username,
            password,
            device_id: localStorage.getItem('managed_device_id') || sessionStorage.getItem('portal_device_id') || undefined
          })
        });

        const data = await response.json();

        if (response.ok) {
          if (data.role === 'ADMIN') {
            window.location.href = data.redirect || '/admin';
          } else {
            if (statusBox) {
              statusBox.className = 'alert-box alert-warning';
              statusBox.innerHTML = `
                <strong>Access Restricted</strong><br>
                Authenticated as regular user <code>${escapeHtml(data.username)}</code>. Administrator role required for dashboard.
              `;
              statusBox.classList.remove('hidden');
            }
            btnSubmit.disabled = false;
            if (btnSubmit.querySelector('.btn-text')) {
              btnSubmit.querySelector('.btn-text').textContent = originalText;
            }
          }
        } else {
          if (statusBox) {
            statusBox.className = 'alert-box alert-danger';
            statusBox.textContent = `❌ ${data.error || 'Authentication failed'}`;
            statusBox.classList.remove('hidden');
          }
          btnSubmit.disabled = false;
          if (btnSubmit.querySelector('.btn-text')) {
            btnSubmit.querySelector('.btn-text').textContent = originalText;
          }
        }
      } catch (err) {
        console.error('Login request error:', err);
        if (statusBox) {
          statusBox.className = 'alert-box alert-danger';
          statusBox.textContent = '❌ Server connection error.';
          statusBox.classList.remove('hidden');
        }
        btnSubmit.disabled = false;
        if (btnSubmit.querySelector('.btn-text')) {
          btnSubmit.querySelector('.btn-text').textContent = originalText;
        }
      }
    });
  }
}

function openLoginModal() {
  const loginModal = document.getElementById('loginModal');
  const usernameInput = document.getElementById('username');
  if (loginModal) {
    loginModal.classList.remove('hidden');
    if (usernameInput) {
      setTimeout(() => usernameInput.focus(), 100);
    }
  }
}

function closeLoginModal() {
  const loginModal = document.getElementById('loginModal');
  if (loginModal) loginModal.classList.add('hidden');
}

function fillCredentials(username, password) {
  const u = document.getElementById('username');
  const p = document.getElementById('password');
  if (u && p) {
    u.value = username;
    p.value = password;
  }
}

// ============================================================================
// 3. CLIENT DEVICE AGENT (AUTOMATIC RECONNECTION & DIRECT SCREEN ASSIST)
// ============================================================================
let userDeviceId = null;
let userHeartbeatInterval = null;
let userSignalingInterval = null;
let userScreenStream = null;
let userPeerConnection = null;
let currentScreenSessionId = null;

const rtcConfig = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' }
  ]
};

function initClientDeviceAgent() {
  const isManaged = localStorage.getItem('is_managed_device') === 'true';

  if (isManaged) {
    initManagedDeviceAgent();
  } else {
    initVisitorDeviceAgent();
  }

  // Setup stop sharing banner button
  const btnStopBanner = document.getElementById('btnUserStopSharing');
  if (btnStopBanner) {
    btnStopBanner.addEventListener('click', () => {
      stopUserScreenSharing(currentScreenSessionId, "Stopped via notification banner");
    });
  }
}

/**
 * ENROLLED MANAGED DEVICE AGENT:
 * Automatically reconnects without repeated user approval prompts.
 * Direct remote screen assist under Organization Policy.
 */
function initManagedDeviceAgent() {
  userDeviceId = localStorage.getItem('managed_device_id');
  const deviceAuthToken = localStorage.getItem('managed_device_token');
  const hostname = localStorage.getItem('managed_hostname') || userDeviceId;

  if (!userDeviceId || !deviceAuthToken) {
    initVisitorDeviceAgent();
    return;
  }

  // 1. Initial Heartbeat ping
  sendManagedHeartbeat(userDeviceId, deviceAuthToken, hostname);

  // 2. Periodic routine heartbeat (Every 3 seconds)
  if (userHeartbeatInterval) clearInterval(userHeartbeatInterval);
  userHeartbeatInterval = setInterval(() => {
    sendManagedHeartbeat(userDeviceId, deviceAuthToken, hostname);
  }, 3000);
}

async function sendManagedHeartbeat(deviceId, authToken, hostname) {
  try {
    const res = await fetch('/api/managed-device/heartbeat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: deviceId,
        device_auth_token: authToken,
        hostname: hostname,
        telemetry: {
          screen_res: `${window.screen.width}x${window.screen.height}`,
          touch: ('ontouchstart' in window) || (navigator.maxTouchPoints > 0)
        }
      })
    });

    const data = await res.json();

    if (data.revoked) {
      // Enrollment was revoked by administrator
      localStorage.removeItem('is_managed_device');
      localStorage.removeItem('managed_device_token');
      localStorage.removeItem('managed_device_id');
      clearInterval(userHeartbeatInterval);
      initVisitorDeviceAgent();
      return;
    }

    if (data.event) {
      if (data.event.type === 'managed_screen_assist') {
        // DIRECT SCREEN ASSIST UNDER PRE-APPROVED ORG POLICY (No manual accept/decline modal required!)
        handleDirectManagedScreenAssist(data.event);
      } else if (data.event.type === 'enrollment_revoked') {
        localStorage.removeItem('is_managed_device');
        localStorage.removeItem('managed_device_token');
        clearInterval(userHeartbeatInterval);
        initVisitorDeviceAgent();
      }
    }

  } catch (err) {
    console.debug('Managed device heartbeat error:', err);
  }
}

/**
 * Direct Remote Screen Assist for Enrolled Managed Devices:
 * Fulfills screen request directly under the pre-agreed organization policy.
 */
async function handleDirectManagedScreenAssist(event) {
  currentScreenSessionId = event.session_id;

  const banner = document.getElementById('userSharingBanner');
  const bannerText = document.getElementById('userBannerText');

  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    console.warn("Screen sharing not supported by browser");
    await respondToScreenRequest(false, "Browser getDisplayMedia not supported");
    return;
  }

  try {
    // Directly prompt the browser's native display capture selector (Under Organization Policy)
    userScreenStream = await navigator.mediaDevices.getDisplayMedia({
      video: { cursor: "always" },
      audio: false
    });
  } catch (err) {
    console.warn("Screen selection was cancelled by user:", err);
    await respondToScreenRequest(false, "User canceled screen selection");
    return;
  }

  // Notify server of active session
  await respondToScreenRequest(true, "Managed remote assist activated under organization policy");

  // Show persistent management session banner
  if (banner) {
    if (bannerText) {
      bannerText.textContent = "🔴 MANAGED DEVICE ASSIST ACTIVE - Under Organization Monitoring Policy";
    }
    banner.classList.remove('hidden');
  }

  // Setup WebRTC peer connection
  setupUserWebRTCStream();
}

/**
 * UNMANAGED VISITOR DEVICE AGENT:
 * Routine automatic registration with harmless landing page.
 * Uses manual consent modal if administrator requests screen viewing.
 */
function initVisitorDeviceAgent() {
  userDeviceId = sessionStorage.getItem('portal_device_id');
  if (!userDeviceId) {
    userDeviceId = 'dev_' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36).substring(4);
    sessionStorage.setItem('portal_device_id', userDeviceId);
  }

  const telemetry = {
    screen_res: (window.screen ? `${window.screen.width}x${window.screen.height}` : '-'),
    touch: ('ontouchstart' in window) || (navigator.maxTouchPoints > 0)
  };

  // Register device automatically
  registerVisitorDevice(telemetry);

  if (userHeartbeatInterval) clearInterval(userHeartbeatInterval);
  userHeartbeatInterval = setInterval(pollVisitorDeviceEvents, 3000);

  // Setup Consent Dialog buttons
  const btnAccept = document.getElementById('btnAcceptScreenShare');
  const btnDecline = document.getElementById('btnDeclineScreenShare');

  if (btnAccept) {
    btnAccept.addEventListener('click', onVisitorAcceptScreenShare);
  }

  if (btnDecline) {
    btnDecline.addEventListener('click', onVisitorDeclineScreenShare);
  }
}

async function registerVisitorDevice(telemetry) {
  try {
    await fetch('/api/device/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: userDeviceId,
        screen_res: telemetry.screen_res,
        touch: telemetry.touch
      })
    });
  } catch (err) {
    console.debug('Visitor registration error:', err);
  }
}

async function pollVisitorDeviceEvents() {
  if (!userDeviceId) return;

  try {
    const res = await fetch(`/api/device/poll?device_id=${encodeURIComponent(userDeviceId)}`);
    if (!res.ok) return;

    const data = await res.json();
    const event = data.event;

    if (event && event.type === 'screen_view_request') {
      currentScreenSessionId = event.session_id;
      const modal = document.getElementById('consentModal');
      const adminNameSpan = document.getElementById('reqAdminName');
      const consentPromptText = document.getElementById('consentPromptText');

      if (adminNameSpan) adminNameSpan.textContent = event.admin_user || 'admin';
      if (consentPromptText) {
        consentPromptText.innerHTML = `Administrator <strong>${escapeHtml(event.admin_user || 'admin')}</strong> is requesting permission to view your screen for assistance.`;
      }
      if (modal) modal.classList.remove('hidden');
    }
  } catch (err) {
    console.debug('Device poll error:', err);
  }
}

async function onVisitorAcceptScreenShare() {
  const modal = document.getElementById('consentModal');
  const banner = document.getElementById('userSharingBanner');
  const bannerText = document.getElementById('userBannerText');

  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    alert("Screen sharing is not supported by this browser or operating system.");
    await respondToScreenRequest(false, "Browser does not support getDisplayMedia");
    if (modal) modal.classList.add('hidden');
    return;
  }

  try {
    userScreenStream = await navigator.mediaDevices.getDisplayMedia({
      video: { cursor: "always" },
      audio: false
    });
  } catch (err) {
    await respondToScreenRequest(false, "User canceled screen selection");
    if (modal) modal.classList.add('hidden');
    return;
  }

  await respondToScreenRequest(true, "User granted consent via dialog");

  if (modal) modal.classList.add('hidden');
  if (banner) {
    if (bannerText) bannerText.textContent = "🔴 Screen Sharing Active with Administrator";
    banner.classList.remove('hidden');
  }

  setupUserWebRTCStream();
}

async function onVisitorDeclineScreenShare() {
  const modal = document.getElementById('consentModal');
  if (modal) modal.classList.add('hidden');
  await respondToScreenRequest(false, "User declined request");
  currentScreenSessionId = null;
}

async function setupUserWebRTCStream() {
  try {
    userPeerConnection = new RTCPeerConnection(rtcConfig);

    userScreenStream.getTracks().forEach(track => {
      userPeerConnection.addTrack(track, userScreenStream);
    });

    userPeerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        fetch('/api/webrtc/signal', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: currentScreenSessionId,
            role: 'user',
            type: 'candidate',
            candidate: event.candidate
          })
        }).catch(console.error);
      }
    };

    const offer = await userPeerConnection.createOffer();
    await userPeerConnection.setLocalDescription(offer);

    await fetch('/api/webrtc/signal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentScreenSessionId,
        role: 'user',
        type: 'offer',
        offer: userPeerConnection.localDescription
      })
    });

    startUserSignalingPoll(currentScreenSessionId);

    const videoTrack = userScreenStream.getVideoTracks()[0];
    if (videoTrack) {
      videoTrack.onended = () => {
        stopUserScreenSharing(currentScreenSessionId, "Native browser stop sharing clicked");
      };
    }

  } catch (err) {
    console.error("WebRTC stream negotiation error:", err);
    stopUserScreenSharing(currentScreenSessionId, "WebRTC initialization error: " + err.message);
  }
}

async function respondToScreenRequest(accepted, reason) {
  if (!currentScreenSessionId || !userDeviceId) return;

  try {
    await fetch('/api/screen-request/respond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: userDeviceId,
        session_id: currentScreenSessionId,
        accepted: accepted,
        reason: reason || ''
      })
    });
  } catch (err) {
    console.error('Respond to request error:', err);
  }
}

function startUserSignalingPoll(sessionId) {
  if (userSignalingInterval) clearInterval(userSignalingInterval);

  userSignalingInterval = setInterval(async () => {
    if (!sessionId) {
      clearInterval(userSignalingInterval);
      return;
    }

    try {
      const res = await fetch(`/api/webrtc/signal?session_id=${encodeURIComponent(sessionId)}&role=user`);
      if (!res.ok) return;

      const data = await res.json();

      if (data.status === 'ENDED') {
        stopUserScreenSharing(sessionId, "Session ended by administrator");
        return;
      }

      if (data.answer && userPeerConnection && !userPeerConnection.remoteDescription) {
        await userPeerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
      }

      if (data.candidates && data.candidates.length > 0 && userPeerConnection) {
        for (const cand of data.candidates) {
          try {
            await userPeerConnection.addIceCandidate(new RTCIceCandidate(cand));
          } catch (e) {}
        }
      }
    } catch (err) {
      console.debug('User signaling poll error:', err);
    }
  }, 1200);
}

async function stopUserScreenSharing(sessionId, reason) {
  if (userSignalingInterval) {
    clearInterval(userSignalingInterval);
    userSignalingInterval = null;
  }

  if (userScreenStream) {
    userScreenStream.getTracks().forEach(track => {
      try { track.stop(); } catch (e) {}
    });
    userScreenStream = null;
  }

  if (userPeerConnection) {
    try { userPeerConnection.close(); } catch (e) {}
    userPeerConnection = null;
  }

  const banner = document.getElementById('userSharingBanner');
  if (banner) banner.classList.add('hidden');

  if (sessionId) {
    try {
      await fetch('/api/webrtc/end', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          device_id: userDeviceId,
          reason: reason || 'Stopped by user'
        })
      });
    } catch (e) {}
  }

  currentScreenSessionId = null;
}

// ============================================================================
// 4. ADMIN DASHBOARD, REAL-TIME SSE & ENROLLMENT CONTROLLER
// ============================================================================
let adminActiveSessionId = null;
let adminPeerConnection = null;
let adminSignalingInterval = null;
let adminEventSource = null;
let adminDevicesFallbackInterval = null;

function initAdminDashboard() {
  const btnLogout = document.getElementById('btnLogout');
  if (btnLogout) {
    btnLogout.addEventListener('click', async () => {
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
      } catch (e) {
        console.error('Logout error:', e);
      }
      window.location.href = '/';
    });
  }

  const btnRefreshDevices = document.getElementById('btnRefreshDevices');
  if (btnRefreshDevices) {
    btnRefreshDevices.addEventListener('click', () => loadConnectedDevices());
  }

  const btnRefreshScreenAudit = document.getElementById('btnRefreshScreenAudit');
  if (btnRefreshScreenAudit) {
    btnRefreshScreenAudit.addEventListener('click', () => loadScreenAuditRecords());
  }

  const btnRefreshLogins = document.getElementById('btnRefreshLogins');
  if (btnRefreshLogins) {
    btnRefreshLogins.addEventListener('click', () => loadLoginRecords());
  }

  const btnRefreshConnHistory = document.getElementById('btnRefreshConnHistory');
  if (btnRefreshConnHistory) {
    btnRefreshConnHistory.addEventListener('click', () => loadConnectionHistory());
  }

  const searchInput = document.getElementById('deviceSearchInput');
  if (searchInput) {
    searchInput.addEventListener('input', () => filterAndRenderDevices());
  }

  const btnEndRemote = document.getElementById('btnEndRemoteScreen');
  if (btnEndRemote) {
    btnEndRemote.addEventListener('click', () => endAdminScreenViewing());
  }

  // Enrollment Link Generator Modal buttons
  initEnrollmentGenerator();

  // Load and verify Admin
  verifyAdminAndLoadDashboard();
}

function initEnrollmentGenerator() {
  const btnOpenModal = document.getElementById('btnOpenEnrollModal');
  const btnOpenModalTop = document.getElementById('btnGenerateLinkTop');
  const btnCloseModal = document.getElementById('btnCloseEnrollModal');
  const modal = document.getElementById('enrollModal');
  const btnCreate = document.getElementById('btnCreateEnrollToken');
  const btnCopy = document.getElementById('btnCopyEnrollLink');
  const linkInput = document.getElementById('enrollLinkInput');
  const copyFeedback = document.getElementById('copyFeedback');
  const linkSection = document.getElementById('generatedLinkSection');

  function openModal() {
    if (modal) {
      modal.classList.remove('hidden');
      if (linkSection) linkSection.classList.add('hidden');
      if (copyFeedback) copyFeedback.classList.add('hidden');
    }
  }

  function closeModal() {
    if (modal) modal.classList.add('hidden');
  }

  if (btnOpenModal) btnOpenModal.addEventListener('click', openModal);
  if (btnOpenModalTop) btnOpenModalTop.addEventListener('click', openModal);
  if (btnCloseModal) btnCloseModal.addEventListener('click', closeModal);

  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
  }

  if (btnCreate) {
    btnCreate.addEventListener('click', async () => {
      btnCreate.disabled = true;
      btnCreate.textContent = 'Generating Secure Link...';

      try {
        const res = await fetch('/api/admin/generate-enrollment-token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ policy_name: 'Standard Organization Management Policy' })
        });

        const data = await res.json();

        if (res.ok) {
          if (linkInput) linkInput.value = data.enroll_url;
          if (linkSection) linkSection.classList.remove('hidden');
          if (copyFeedback) copyFeedback.classList.add('hidden');
        } else {
          alert(`Error generating link: ${data.error || 'Server error'}`);
        }
      } catch (err) {
        alert('Network error while generating enrollment link');
      } finally {
        btnCreate.disabled = false;
        btnCreate.textContent = 'Generate Another Link';
      }
    });
  }

  if (btnCopy && linkInput) {
    btnCopy.addEventListener('click', () => {
      if (!linkInput.value) return;
      navigator.clipboard.writeText(linkInput.value).then(() => {
        if (copyFeedback) copyFeedback.classList.remove('hidden');
      }).catch(() => {
        linkInput.select();
        document.execCommand('copy');
        if (copyFeedback) copyFeedback.classList.remove('hidden');
      });
    });
  }
}

async function verifyAdminAndLoadDashboard() {
  const userLabel = document.getElementById('adminUserLabel');

  try {
    const meRes = await fetch('/api/auth/me');
    if (!meRes.ok) {
      window.location.href = '/?access=login_required';
      return;
    }

    const me = await meRes.json();
    if (me.role !== 'ADMIN') {
      window.location.href = '/unauthorized.html';
      return;
    }

    if (userLabel) {
      userLabel.textContent = `👤 ${me.full_name || me.username} (${me.role})`;
    }

    loadDashboardStats();
    loadConnectedDevices();
    loadScreenAuditRecords();
    loadLoginRecords();
    loadConnectionHistory();

    setupAdminSSE();

    if (adminDevicesFallbackInterval) clearInterval(adminDevicesFallbackInterval);
    adminDevicesFallbackInterval = setInterval(() => {
      loadConnectedDevices(true);
      loadDashboardStats();
    }, 4500);

  } catch (err) {
    console.error('Auth verification error:', err);
    window.location.href = '/';
  }
}

function setupAdminSSE() {
  if (adminEventSource) {
    try { adminEventSource.close(); } catch (e) {}
  }

  const sseBadge = document.getElementById('sseStatusBadge');

  try {
    adminEventSource = new EventSource('/api/admin/events-stream');

    adminEventSource.onopen = () => {
      if (sseBadge) {
        sseBadge.className = 'badge-live-stream';
        sseBadge.innerHTML = '⚡ Live Real-Time Feed';
      }
    };

    adminEventSource.addEventListener('devices_update', (event) => {
      try {
        const payload = JSON.parse(event.data);
        const data = payload.payload || payload;
        if (data.devices) {
          allLoadedDevices = data.devices;
          filterAndRenderDevices();
        }
        if (data.metrics) {
          renderDashboardMetrics(data.metrics);
        }
        const lastSyncEl = document.getElementById('lastSyncTime');
        if (lastSyncEl) {
          const nowStr = new Date().toLocaleTimeString();
          lastSyncEl.textContent = `Real-time sync: ${nowStr}`;
        }
      } catch (e) {
        console.error('SSE devices_update parse error:', e);
      }
    });

    adminEventSource.addEventListener('screen_update', () => {
      loadScreenAuditRecords();
      loadConnectedDevices(true);
    });

    adminEventSource.onerror = () => {
      if (sseBadge) {
        sseBadge.className = 'badge-status badge-away';
        sseBadge.innerHTML = '⚠️ Reconnecting Real-Time...';
      }
    };

  } catch (err) {
    console.warn('SSE stream error, fallback polling active:', err);
  }
}

function renderDashboardMetrics(metrics) {
  const statStatus = document.getElementById('statStatus');
  const statEnrolled = document.getElementById('statEnrolledDevices');
  const statOnline = document.getElementById('statOnlineDevices');
  const statScreens = document.getElementById('statScreensShared');

  if (statStatus) statStatus.textContent = metrics.system_status || 'Healthy & Secure';
  if (statEnrolled) statEnrolled.textContent = metrics.enrolled_devices !== undefined ? metrics.enrolled_devices : '-';
  if (statOnline) statOnline.textContent = metrics.online_devices !== undefined ? metrics.online_devices : '-';
  if (statScreens) statScreens.textContent = metrics.screens_shared !== undefined ? metrics.screens_shared : '0';
}

async function loadDashboardStats() {
  try {
    const res = await fetch('/api/admin/dashboard');
    if (!res.ok) return;
    const data = await res.json();
    renderDashboardMetrics(data);
  } catch (e) {
    console.debug('Dashboard stats load error:', e);
  }
}

async function loadConnectedDevices(isSilent = false) {
  const tableBody = document.getElementById('devicesTableBody');
  if (!tableBody) return;

  try {
    const res = await fetch('/api/admin/devices');
    if (!res.ok) {
      if (!isSilent) {
        tableBody.innerHTML = '<tr><td colspan="10" class="text-center">Failed to load connected devices list.</td></tr>';
      }
      return;
    }

    const data = await res.json();
    allLoadedDevices = data.devices || [];
    filterAndRenderDevices();

  } catch (err) {
    if (!isSilent) {
      tableBody.innerHTML = '<tr><td colspan="10" class="text-center">Error scanning for devices.</td></tr>';
    }
  }
}

let allLoadedDevices = [];

function filterAndRenderDevices() {
  const searchInput = document.getElementById('deviceSearchInput');
  const query = (searchInput ? searchInput.value : '').toLowerCase().trim();

  let filtered = allLoadedDevices;
  if (query) {
    filtered = allLoadedDevices.filter(d => 
      (d.hostname || '').toLowerCase().includes(query) ||
      (d.device_id || '').toLowerCase().includes(query) ||
      (d.ip_address || '').toLowerCase().includes(query) ||
      (d.os_name || '').toLowerCase().includes(query) ||
      (d.browser_name || '').toLowerCase().includes(query) ||
      (d.device_type || '').toLowerCase().includes(query)
    );
  }
  renderConnectedDevicesTable(filtered);
}

function renderConnectedDevicesTable(devices) {
  const tableBody = document.getElementById('devicesTableBody');
  if (!tableBody) return;

  if (devices.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="10" class="text-center" style="padding: 28px;">
          <div style="font-size: 1.15rem; margin-bottom: 6px;">📱 No devices currently connected</div>
          <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 12px;">
            Open an enrollment link on an authorized device or share the public link.
          </div>
          <button onclick="document.getElementById('btnOpenEnrollModal').click()" class="btn-sm" style="background: var(--success); color: white; border: none;">
            + Generate Enrollment Link
          </button>
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = devices.map(d => {
    let icon = '💻';
    if (d.device_type === 'Mobile Phone') icon = '📱';
    if (d.device_type === 'Tablet') icon = '📟';

    // Status Badge
    let statusBadge = `<span class="badge-status badge-online">Online</span>`;
    if (d.status === 'away') {
      statusBadge = `<span class="badge-status badge-away">Away</span>`;
    } else if (d.status === 'disconnected') {
      statusBadge = `<span class="badge-status badge-disconnected">Disconnected</span>`;
    } else if (d.status === 'request_pending') {
      statusBadge = `<span class="badge-status badge-pending">Connecting...</span>`;
    } else if (d.status === 'sharing') {
      statusBadge = `<span class="badge-status badge-sharing">Sharing Live</span>`;
    }

    // Management Badge
    let mgmtBadge = `<span class="badge-status badge-visitor">Public Visitor</span>`;
    let displayName = `<code>${escapeHtml(d.device_id)}</code>`;

    if (d.is_managed) {
      mgmtBadge = `<span class="badge-status badge-auth" title="Pre-Approved Under Org Policy">🛡️ Managed</span>`;
      displayName = `<strong>${escapeHtml(d.hostname)}</strong><br><small style="color:var(--text-muted); font-size:0.7rem;"><code>${escapeHtml(d.device_id)}</code></small>`;
    }

    // Action Buttons
    let actionHtml = '';
    if (d.status === 'disconnected') {
      actionHtml = `<span style="font-size:0.75rem; color: var(--text-muted);">Offline</span>`;
    } else if (d.status === 'sharing') {
      actionHtml = `<span style="font-size:0.78rem; color: #34D399; font-weight:700;">Stream Active</span>`;
    } else if (d.status === 'request_pending') {
      actionHtml = `<span style="font-size:0.78rem; color: #FBBF24;">Connecting...</span>`;
    } else {
      if (d.is_managed) {
        actionHtml = `
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn-req-screen" style="background: linear-gradient(135deg, #10B981, #059669);" onclick="adminDirectScreenAssist('${escapeHtml(d.device_id)}', '${escapeHtml(d.hostname)}')">
              Remote Assist
            </button>
            <button class="btn-sm" style="background: transparent; border: 1px solid #EF4444; color: #F87171; padding: 6px 10px; font-size: 0.72rem;" onclick="adminRevokeDevice('${escapeHtml(d.device_id)}')">
              Revoke
            </button>
          </div>
        `;
      } else {
        actionHtml = `
          <button class="btn-req-screen" onclick="adminRequestScreen('${escapeHtml(d.device_id)}')">
            Request Screen
          </button>
        `;
      }
    }

    const browserDisplay = d.browser_version && d.browser_version !== 'Unknown' 
      ? `${escapeHtml(d.browser_name)} <span style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(d.browser_version)}</span>`
      : escapeHtml(d.browser_name);

    return `
      <tr>
        <td>${displayName}</td>
        <td>${mgmtBadge}</td>
        <td>${icon} ${escapeHtml(d.device_type)}</td>
        <td>${escapeHtml(d.os_name)}</td>
        <td>${browserDisplay}</td>
        <td><code>${escapeHtml(d.ip_address)}</code></td>
        <td style="font-size:0.78rem; color:#CBD5E1;">${escapeHtml(d.first_seen_utc || '-')}</td>
        <td style="font-weight:600;">${escapeHtml(d.last_activity || 'Just now')}</td>
        <td>${statusBadge}</td>
        <td>${actionHtml}</td>
      </tr>
    `;
  }).join('');
}

// Global hooks for inline onclick in table
window.adminDirectScreenAssist = async function(deviceId, hostname) {
  if (!deviceId) return;

  const viewerSection = document.getElementById('remoteScreenSection');
  const deviceInfoSub = document.getElementById('remoteScreenDeviceInfo');
  const resBadge = document.getElementById('remoteResBadge');

  if (deviceInfoSub) {
    deviceInfoSub.textContent = `Initiating direct remote assist with managed device ${hostname || deviceId}...`;
  }
  if (resBadge) {
    resBadge.textContent = 'Connecting via Org Policy';
  }
  if (viewerSection) {
    viewerSection.classList.remove('hidden');
  }

  try {
    const res = await fetch('/api/admin/request-screen', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: deviceId })
    });

    const data = await res.json();

    if (!res.ok) {
      alert(`Could not initiate remote assist: ${data.error || 'Unknown error'}`);
      if (viewerSection) viewerSection.classList.add('hidden');
      loadConnectedDevices();
      return;
    }

    adminActiveSessionId = data.session_id;

    if (deviceInfoSub) {
      deviceInfoSub.textContent = `Awaiting video stream from managed device ${hostname || deviceId}...`;
    }

    initAdminWebRTCReceiver(adminActiveSessionId, hostname || deviceId);
    loadConnectedDevices();
    loadScreenAuditRecords();

  } catch (err) {
    console.error('Remote assist error:', err);
    alert('Server communication error.');
    if (viewerSection) viewerSection.classList.add('hidden');
  }
};

window.adminRequestScreen = async function(deviceId) {
  if (!deviceId) return;

  const viewerSection = document.getElementById('remoteScreenSection');
  const deviceInfoSub = document.getElementById('remoteScreenDeviceInfo');
  const resBadge = document.getElementById('remoteResBadge');

  if (deviceInfoSub) {
    deviceInfoSub.textContent = `Sending screen view request to device ${deviceId}...`;
  }
  if (resBadge) {
    resBadge.textContent = 'Awaiting Consent';
  }
  if (viewerSection) {
    viewerSection.classList.remove('hidden');
  }

  try {
    const res = await fetch('/api/admin/request-screen', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: deviceId })
    });

    const data = await res.json();

    if (!res.ok) {
      alert(`Could not request screen view: ${data.error || 'Unknown error'}`);
      if (viewerSection) viewerSection.classList.add('hidden');
      loadConnectedDevices();
      return;
    }

    adminActiveSessionId = data.session_id;
    initAdminWebRTCReceiver(adminActiveSessionId, deviceId);
    loadConnectedDevices();
    loadScreenAuditRecords();

  } catch (err) {
    console.error('Request screen error:', err);
    alert('Server communication error.');
    if (viewerSection) viewerSection.classList.add('hidden');
  }
};

window.adminRevokeDevice = async function(deviceId) {
  if (!deviceId) return;
  if (!confirm(`Are you sure you want to revoke management enrollment for device ${deviceId}?`)) {
    return;
  }

  try {
    const res = await fetch('/api/admin/revoke-device', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: deviceId })
    });

    const data = await res.json();
    if (res.ok) {
      loadConnectedDevices();
      loadDashboardStats();
    } else {
      alert(`Revocation failed: ${data.error || 'Server error'}`);
    }
  } catch (err) {
    alert('Network error while revoking device');
  }
};

function initAdminWebRTCReceiver(sessionId, targetDisplayName) {
  if (adminPeerConnection) {
    try { adminPeerConnection.close(); } catch (e) {}
  }

  adminPeerConnection = new RTCPeerConnection(rtcConfig);

  adminPeerConnection.ontrack = (event) => {
    const video = document.getElementById('remoteScreenVideo');
    const resBadge = document.getElementById('remoteResBadge');
    const deviceInfoSub = document.getElementById('remoteScreenDeviceInfo');

    if (video && event.streams && event.streams[0]) {
      video.srcObject = event.streams[0];
      if (resBadge) resBadge.textContent = '🟢 Live Stream 60 FPS';
      if (deviceInfoSub) deviceInfoSub.textContent = `Streaming screen from managed device: ${targetDisplayName}`;
    }
  };

  adminPeerConnection.onicecandidate = (event) => {
    if (event.candidate) {
      fetch('/api/webrtc/signal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          role: 'admin',
          type: 'candidate',
          candidate: event.candidate
        })
      }).catch(console.error);
    }
  };

  startAdminSignalingPoll(sessionId, targetDisplayName);
}

function startAdminSignalingPoll(sessionId, targetDisplayName) {
  if (adminSignalingInterval) clearInterval(adminSignalingInterval);

  adminSignalingInterval = setInterval(async () => {
    if (!sessionId) {
      clearInterval(adminSignalingInterval);
      return;
    }

    try {
      const res = await fetch(`/api/webrtc/signal?session_id=${encodeURIComponent(sessionId)}&role=admin`);
      if (!res.ok) return;

      const data = await res.json();
      const status = data.status;

      if (status === 'DECLINED') {
        clearInterval(adminSignalingInterval);
        alert(`Target device (${targetDisplayName}) declined the screen view request.`);
        cleanupAdminRemoteViewer();
        loadConnectedDevices();
        loadScreenAuditRecords();
        return;
      }

      if (status === 'ENDED') {
        clearInterval(adminSignalingInterval);
        cleanupAdminRemoteViewer();
        loadConnectedDevices();
        loadScreenAuditRecords();
        return;
      }

      if (data.offer && adminPeerConnection && !adminPeerConnection.remoteDescription) {
        await adminPeerConnection.setRemoteDescription(new RTCSessionDescription(data.offer));
        const answer = await adminPeerConnection.createAnswer();
        await adminPeerConnection.setLocalDescription(answer);

        await fetch('/api/webrtc/signal', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            role: 'admin',
            type: 'answer',
            answer: adminPeerConnection.localDescription
          })
        });

        const deviceInfoSub = document.getElementById('remoteScreenDeviceInfo');
        if (deviceInfoSub) deviceInfoSub.textContent = `Remote assist active with ${targetDisplayName}...`;
      }

      if (data.candidates && data.candidates.length > 0 && adminPeerConnection) {
        for (const cand of data.candidates) {
          try {
            await adminPeerConnection.addIceCandidate(new RTCIceCandidate(cand));
          } catch (e) {}
        }
      }

    } catch (err) {
      console.debug('Admin signaling poll error:', err);
    }
  }, 1200);
}

async function endAdminScreenViewing() {
  const sessionId = adminActiveSessionId;
  cleanupAdminRemoteViewer();

  if (sessionId) {
    try {
      await fetch('/api/webrtc/end', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      });
    } catch (e) {}
  }

  loadConnectedDevices();
  loadScreenAuditRecords();
  loadDashboardStats();
}

function cleanupAdminRemoteViewer() {
  if (adminSignalingInterval) {
    clearInterval(adminSignalingInterval);
    adminSignalingInterval = null;
  }

  if (adminPeerConnection) {
    try { adminPeerConnection.close(); } catch (e) {}
    adminPeerConnection = null;
  }

  const video = document.getElementById('remoteScreenVideo');
  if (video) video.srcObject = null;

  const viewerSection = document.getElementById('remoteScreenSection');
  if (viewerSection) viewerSection.classList.add('hidden');

  adminActiveSessionId = null;
}

// ============================================================================
// 5. AUDIT RECORDS LOADERS (SCREEN SHARING & LOGIN AUDIT)
// ============================================================================
async function loadScreenAuditRecords() {
  const tableBody = document.getElementById('screenAuditTableBody');
  if (!tableBody) return;

  try {
    const res = await fetch('/api/admin/screen-audit');
    if (!res.ok) {
      tableBody.innerHTML = '<tr><td colspan="8" class="text-center">Failed to load screen audit history.</td></tr>';
      return;
    }

    const data = await res.json();
    const list = data.audit || [];

    if (list.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="8" class="text-center">No screen sharing requests recorded yet.</td></tr>';
      return;
    }

    tableBody.innerHTML = list.map(item => {
      let badgeClass = 'badge-pending';
      if (item.status === 'ACCEPTED' || item.status === 'ENROLLED') badgeClass = 'badge-accepted';
      if (item.status === 'DECLINED') badgeClass = 'badge-declined';
      if (item.status === 'ENDED') badgeClass = 'badge-success';

      const reqTime = (item.requested_at || '').replace('T', ' ').replace('Z', '');
      const startTime = item.started_at ? item.started_at.replace('T', ' ').replace('Z', '') : '-';
      const endTime = item.ended_at ? item.ended_at.replace('T', ' ').replace('Z', '') : '-';

      return `
        <tr>
          <td>${escapeHtml(reqTime)}</td>
          <td><strong>${escapeHtml(item.admin)}</strong></td>
          <td><code>${escapeHtml(item.device_id)}</code></td>
          <td>${escapeHtml(item.device_type)} (${escapeHtml(item.os)})</td>
          <td><span class="badge-status ${badgeClass}">${escapeHtml(item.status)}</span></td>
          <td>${escapeHtml(startTime)}</td>
          <td>${escapeHtml(endTime)}</td>
          <td>${escapeHtml(item.details || '-')}</td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    tableBody.innerHTML = '<tr><td colspan="8" class="text-center">Network error loading screen audit.</td></tr>';
  }
}

async function loadLoginRecords() {
  const tableBody = document.getElementById('loginTableBody');
  if (!tableBody) return;

  try {
    const res = await fetch('/api/admin/login-records');
    if (!res.ok) {
      tableBody.innerHTML = '<tr><td colspan="8" class="text-center">Failed to load login audit records.</td></tr>';
      return;
    }

    const data = await res.json();
    const records = data.records || [];

    if (records.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="8" class="text-center">No login audit records found.</td></tr>';
      return;
    }

    tableBody.innerHTML = records.map(r => {
      const isSuccess = r.status === 'SUCCESS';
      const badgeClass = isSuccess ? 'badge-success' : 'badge-failed';
      const cleanTime = (r.timestamp || '').replace('T', ' ').replace('Z', '');
      return `
        <tr>
          <td>${escapeHtml(cleanTime)}</td>
          <td><strong>${escapeHtml(r.username)}</strong></td>
          <td><code>${escapeHtml(r.role || 'NONE')}</code></td>
          <td><span class="badge-status ${badgeClass}">${escapeHtml(r.status)}</span></td>
          <td>${escapeHtml(r.device_type)}</td>
          <td>${escapeHtml(r.os_name)}</td>
          <td>${escapeHtml(r.browser_name)}</td>
          <td><code>${escapeHtml(r.ip_address)}</code></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tableBody.innerHTML = '<tr><td colspan="8" class="text-center">Network error loading records.</td></tr>';
  }
}

async function loadConnectionHistory() {
  const tableBody = document.getElementById('connHistoryTableBody');
  if (!tableBody) return;

  try {
    const res = await fetch('/api/admin/connection-history');
    if (!res.ok) {
      tableBody.innerHTML = '<tr><td colspan="8" class="text-center">Failed to load connection history.</td></tr>';
      return;
    }

    const data = await res.json();
    const history = data.history || [];

    if (history.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="8" class="text-center">No connection history recorded yet.</td></tr>';
      return;
    }

    tableBody.innerHTML = history.map(h => {
      let icon = '💻';
      if (h.device_type === 'Mobile Phone') icon = '📱';
      if (h.device_type === 'Tablet') icon = '📟';

      return `
        <tr>
          <td><code>${escapeHtml(h.device_id)}</code></td>
          <td>${icon} ${escapeHtml(h.device_type)}</td>
          <td>${escapeHtml(h.os_name)}</td>
          <td>${escapeHtml(h.browser)}</td>
          <td><code>${escapeHtml(h.ip_address)}</code></td>
          <td style="font-size:0.78rem;">${escapeHtml(h.connected_at)}</td>
          <td style="font-size:0.78rem;">${escapeHtml(h.last_activity_at)}</td>
          <td><span class="badge-status badge-online">${escapeHtml(h.status)}</span></td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    tableBody.innerHTML = '<tr><td colspan="8" class="text-center">Network error loading connection history.</td></tr>';
  }
}

// Utility: HTML Escaping
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
