/**
 * Subplot Dashboard — fetch-based CRUD for students, phones, schedule, reports.
 * Reads window.SUBPLOT_TOKEN (injected by dashboard.html template).
 */

// ── Auth helpers ─────────────────────────────────────────────────────────────

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    ...(window.SUBPLOT_TOKEN ? { 'Authorization': `Bearer ${window.SUBPLOT_TOKEN}` } : {}),
  };
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  return res;
}

// ── Modal helpers ─────────────────────────────────────────────────────────────

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = false;
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = true;
}

function closeOnBackdrop(event, id) {
  if (event.target === event.currentTarget) closeModal(id);
}

// ── Toast helper ──────────────────────────────────────────────────────────────

function showToast(id, message, isError = false) {
  const el = document.getElementById(id);
  if (!el) return;
  el.hidden = false;
  el.textContent = message;
  el.style.borderColor = isError ? 'rgba(239,68,68,0.3)' : 'rgba(16,185,129,0.3)';
  el.style.color = isError ? '#fca5a5' : '#6ee7b7';
  el.style.background = isError ? 'rgba(239,68,68,0.08)' : 'rgba(16,185,129,0.08)';
  setTimeout(() => { el.hidden = true; }, 5000);
}

// ── Students ──────────────────────────────────────────────────────────────────

async function loadStudents() {
  const list = document.getElementById('students-list');
  if (!list) return;

  try {
    const res = await apiFetch('/api/students');
    if (!res.ok) { list.innerHTML = '<div class="list-empty">Failed to load students.</div>'; return; }
    const students = await res.json();

    if (students.length === 0) {
      list.innerHTML = '<div class="list-empty">No students yet. Add one to get started.</div>';
      return;
    }

    list.innerHTML = students.map(s => {
      const statusClass = s.last_scrape_status === 'success' ? 'badge-green'
        : s.last_scrape_status === 'failed' ? 'badge-red' : 'badge-amber';
      const lastScrape = s.last_scrape_at
        ? new Date(s.last_scrape_at).toLocaleString()
        : 'Never';
      return `
        <div class="item-card" id="student-${s.id}">
          <div class="item-info">
            <div class="item-name">${escHtml(s.student_name)}</div>
            <div class="item-meta">
              ${escHtml(s.school_district)} · Student #${escHtml(s.student_number)} · School ${escHtml(s.school_code)}
              <br/>Last scraped: ${lastScrape}
            </div>
          </div>
          <div class="item-actions">
            <span class="item-badge ${statusClass}">${s.last_scrape_status}</span>
            <button class="btn btn-ghost btn-sm" onclick="testStudent('${s.id}', this)">Test</button>
            <button class="btn btn-danger" onclick="deleteStudent('${s.id}')">Remove</button>
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = '<div class="list-empty">Error loading students.</div>';
  }
}

async function deleteStudent(id) {
  if (!confirm('Remove this student?')) return;
  const res = await apiFetch(`/api/students/${id}`, { method: 'DELETE' });
  if (res.ok || res.status === 204) {
    document.getElementById(`student-${id}`)?.remove();
    await loadStudents();
  } else {
    alert('Failed to remove student.');
  }
}

async function testStudent(id, btn) {
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Testing…';
  try {
    const res = await apiFetch(`/api/students/${id}/test-connection`, { method: 'POST' });
    const data = await res.json();
    alert(data.success ? `✅ ${data.message}` : `❌ ${data.message}`);
    await loadStudents();
  } catch {
    alert('Test failed — network error.');
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

function initStudentForm() {
  const form = document.getElementById('add-student-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('add-student-btn');
    const err = document.getElementById('student-form-error');
    err.hidden = true;
    btn.disabled = true;
    btn.textContent = 'Adding…';

    const payload = {
      student_name: document.getElementById('s-name').value.trim(),
      school_district: document.getElementById('s-district').value.trim() || 'mdusd',
      aeries_email: document.getElementById('s-aeries-email').value.trim(),
      aeries_password: document.getElementById('s-aeries-pw').value,
      school_code: document.getElementById('s-school-code').value.trim(),
      student_number: document.getElementById('s-student-num').value.trim(),
      student_id: document.getElementById('s-student-id').value.trim(),
    };

    try {
      const res = await apiFetch('/api/students', { method: 'POST', body: JSON.stringify(payload) });
      if (res.ok) {
        form.reset();
        closeModal('student-modal');
        await loadStudents();
      } else {
        const body = await res.json();
        err.textContent = body.detail || 'Failed to add student.';
        err.hidden = false;
      }
    } catch {
      err.textContent = 'Network error. Please try again.';
      err.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Add Student';
    }
  });
}

// ── Phone Numbers ─────────────────────────────────────────────────────────────

let _pendingVerifyPhone = null;

async function loadPhones() {
  const list = document.getElementById('phones-list');
  if (!list) return;

  try {
    const res = await apiFetch('/api/phone-numbers');
    if (!res.ok) { list.innerHTML = '<div class="list-empty">Failed to load phone numbers.</div>'; return; }
    const phones = await res.json();

    if (phones.length === 0) {
      list.innerHTML = '<div class="list-empty">No phone numbers yet. Add one to receive SMS reports.</div>';
      return;
    }

    list.innerHTML = phones.map(p => {
      const badge = p.verified
        ? '<span class="item-badge badge-green">Verified</span>'
        : '<span class="item-badge badge-amber">Unverified</span>';
      const verifyBtn = !p.verified
        ? `<button class="btn btn-outline btn-sm" onclick="startVerify('${escHtml(p.phone_number)}')">Verify</button>`
        : '';
      return `
        <div class="item-card" id="phone-${p.id}">
          <div class="item-info">
            <div class="item-name">${escHtml(p.phone_number)}</div>
            <div class="item-meta">${p.verification_sent_at ? 'Code sent ' + new Date(p.verification_sent_at).toLocaleDateString() : ''}</div>
          </div>
          <div class="item-actions">
            ${badge}
            ${verifyBtn}
            <button class="btn btn-danger" onclick="deletePhone('${p.id}')">Remove</button>
          </div>
        </div>`;
    }).join('');
  } catch {
    list.innerHTML = '<div class="list-empty">Error loading phone numbers.</div>';
  }
}

function startVerify(phoneNumber) {
  _pendingVerifyPhone = phoneNumber;
  const sect = document.getElementById('verify-section');
  const inp = document.getElementById('verify-phone-number');
  if (sect && inp) {
    inp.value = phoneNumber;
    sect.hidden = false;
    document.getElementById('verify-code')?.focus();
  }
}

async function submitVerify() {
  const code = document.getElementById('verify-code')?.value.trim();
  const err = document.getElementById('verify-error');
  err.hidden = true;

  if (!_pendingVerifyPhone || !code) {
    err.textContent = 'Please enter the 6-digit code.';
    err.hidden = false;
    return;
  }

  try {
    const res = await apiFetch('/api/phone-numbers/verify', {
      method: 'POST',
      body: JSON.stringify({ phone_number: _pendingVerifyPhone, code }),
    });
    if (res.ok) {
      _pendingVerifyPhone = null;
      document.getElementById('verify-section').hidden = true;
      document.getElementById('verify-code').value = '';
      await loadPhones();
    } else {
      const body = await res.json();
      err.textContent = body.detail || 'Invalid code. Please try again.';
      err.hidden = false;
    }
  } catch {
    err.textContent = 'Network error.';
    err.hidden = false;
  }
}

async function deletePhone(id) {
  if (!confirm('Remove this phone number?')) return;
  const res = await apiFetch(`/api/phone-numbers/${id}`, { method: 'DELETE' });
  if (res.ok || res.status === 204) {
    await loadPhones();
  } else {
    alert('Failed to remove phone number.');
  }
}

function initPhoneForm() {
  const form = document.getElementById('add-phone-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('add-phone-btn');
    const err = document.getElementById('phone-form-error');
    err.hidden = true;
    btn.disabled = true;
    btn.textContent = 'Sending code…';

    const phoneNumber = document.getElementById('p-phone').value.trim();

    try {
      const res = await apiFetch('/api/phone-numbers', {
        method: 'POST',
        body: JSON.stringify({ phone_number: phoneNumber }),
      });
      if (res.ok) {
        form.reset();
        closeModal('phone-modal');
        await loadPhones();
        startVerify(phoneNumber);
      } else {
        const body = await res.json();
        err.textContent = body.detail || 'Failed to add phone number.';
        err.hidden = false;
      }
    } catch {
      err.textContent = 'Network error.';
      err.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Send Verification Code';
    }
  });
}

// ── Schedule ──────────────────────────────────────────────────────────────────

async function loadSchedule() {
  try {
    const res = await apiFetch('/api/schedule');
    if (!res.ok) return;
    const sched = await res.json();

    const timeEl = document.getElementById('sched-time');
    const tzEl = document.getElementById('sched-tz');
    const enabledEl = document.getElementById('sched-enabled');

    if (timeEl) timeEl.value = sched.delivery_time || '16:00';
    if (tzEl) tzEl.value = sched.timezone || 'America/Los_Angeles';
    if (enabledEl) enabledEl.checked = sched.enabled !== false;

    const days = sched.days_of_week || ['mon', 'tue', 'wed', 'thu', 'fri'];
    document.querySelectorAll('.day-chips input[type="checkbox"]').forEach(cb => {
      cb.checked = days.includes(cb.value);
    });
  } catch {
    // Silently ignore — schedule will just use form defaults
  }
}

async function saveSchedule() {
  const time = document.getElementById('sched-time')?.value || '16:00';
  const tz = document.getElementById('sched-tz')?.value || 'America/Los_Angeles';
  const enabled = document.getElementById('sched-enabled')?.checked !== false;
  const days = Array.from(document.querySelectorAll('.day-chips input:checked')).map(cb => cb.value);

  const result = document.getElementById('sched-result');
  result.hidden = true;

  try {
    const res = await apiFetch('/api/schedule', {
      method: 'PUT',
      body: JSON.stringify({ delivery_time: time, timezone: tz, days_of_week: days, enabled }),
    });
    if (res.ok) {
      result.hidden = false;
      result.textContent = '✓ Schedule saved successfully.';
      setTimeout(() => { result.hidden = true; }, 3000);
    } else {
      const body = await res.json();
      result.hidden = false;
      result.style.background = 'var(--danger-dim)';
      result.style.color = '#fca5a5';
      result.textContent = body.detail || 'Failed to save schedule.';
    }
  } catch {
    result.hidden = false;
    result.textContent = 'Network error.';
  }
}

// ── Reports ───────────────────────────────────────────────────────────────────

async function loadReports() {
  const list = document.getElementById('reports-list');
  if (!list) return;

  try {
    const res = await apiFetch('/api/reports');
    if (!res.ok) { list.innerHTML = '<div class="list-empty">Failed to load reports.</div>'; return; }
    const reports = await res.json();

    if (reports.length === 0) {
      list.innerHTML = '<div class="list-empty">No reports yet. Click "Send Test Report Now" to generate the first one.</div>';
      return;
    }

    list.innerHTML = reports.map(r => {
      const date = new Date(r.scraped_at).toLocaleString();
      const text = r.summary_text || '(no summary)';
      return `
        <div class="report-card">
          <div class="report-meta">
            <span class="report-student">Student ${escHtml(r.student_id.slice(0, 8))}…</span>
            <span class="report-date">${date}</span>
          </div>
          <div class="report-body">${escHtml(text)}</div>
        </div>`;
    }).join('');
  } catch {
    list.innerHTML = '<div class="list-empty">Error loading reports.</div>';
  }
}

async function sendNow() {
  const btn = document.getElementById('send-now-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Sending…';

  try {
    const res = await apiFetch('/api/reports/send-now', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      const summary = data.results?.map(r =>
        `${r.student}: ${r.status}${r.changes !== undefined ? ` (${r.changes} changes)` : ''}`
      ).join(', ') || 'Done.';
      showToast('send-now-result', `✓ ${summary}`);
      await loadReports();
      await loadStudents();
    } else {
      const body = await res.json().catch(() => ({}));
      showToast('send-now-result', body.detail || 'Send failed.', true);
    }
  } catch {
    showToast('send-now-result', 'Network error.', true);
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ Send Test Report Now';
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Only run dashboard logic if the dashboard elements are present
  if (document.getElementById('students-list')) {
    loadStudents();
    loadPhones();
    loadSchedule();
    loadReports();
    initStudentForm();
    initPhoneForm();
  }
});
