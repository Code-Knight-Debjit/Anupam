// Backup & restore, and the audit log — Admin only (the server enforces it; this is just the screen).
import { api } from '../api.js';
import { el, escapeHtml, fmtDateTime, toast, apiErrorMessage, renderTable, confirmDialog } from '../ui.js';

async function postFile(url, file, extra = {}) {
  const fd = new FormData();
  fd.append('file', file);
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  return api.post(url, fd);
}

export async function mountBackup(root) {
  const copies = await api.get('backup/safety-copies/');
  root.innerHTML = `
    <h2 style="margin-top:0;">Backup &amp; restore</h2>
    <div class="card" style="max-width:720px;">
      <h3>Download a backup</h3>
      <p class="sub">One file with every dataset (customers, contacts, documents, payments, tasks, attendance, lists, users…). It contains password hashes — keep it private. Uploaded images are not inside the file.</p>
      <a class="btn primary" href="/360/api/backup/export/">Download backup</a>
    </div>
    <div class="card" style="max-width:720px;margin-top:12px;">
      <h3>Restore from a backup</h3>
      <p class="sub">Restoring <strong>replaces all current data</strong>. A safety copy of the current data is saved first, and nothing changes if the file is damaged.</p>
      <div class="field"><input type="file" id="bk-file" accept="application/json,.json" aria-label="Backup file"></div>
      <div id="bk-info"></div>
      <div class="modal-actions" style="justify-content:flex-start;"><button class="btn" id="bk-describe">Check the file</button><button class="btn danger" id="bk-restore" disabled>Restore…</button></div>
    </div>
    <div class="card" style="max-width:720px;margin-top:12px;"><h3>Safety copies</h3>
      ${renderTable(['File', 'Size', ''], copies.results.map((c) => ({ File: escapeHtml(c.name), Size: `${Math.round(c.size / 1024)} KB`,
        '': `<a class="btn sm" href="/360/api/backup/safety-copies/${encodeURIComponent(c.name)}">Download</a>` })), { empty: 'No safety copies yet.' })}</div>`;
  const file = () => el('bk-file').files[0];
  el('bk-describe').onclick = async () => {
    if (!file()) { toast('Choose a backup file first.', 'error'); return; }
    try {
      const info = await postFile('backup/describe/', file());
      el('bk-info').innerHTML = `<p class="sub">Made ${escapeHtml(info.created_at || '?')} by ${escapeHtml(info.created_by || '?')} · ${info.users} users</p>
        ${renderTable(['Dataset', 'Records'], Object.entries(info.contains).map(([k, v]) => ({ Dataset: escapeHtml(k), Records: v })))}
        ${info.missing.length ? `<p class="sub" style="color:var(--error);">Not in this backup (they will be left empty): ${info.missing.map(escapeHtml).join(', ')}</p>` : ''}`;
      el('bk-restore').disabled = false;
    } catch (e) { toast(apiErrorMessage(e), 'error'); el('bk-restore').disabled = true; }
  };
  el('bk-restore').onclick = async () => {
    if (!await confirmDialog('Replace ALL current data with this backup? A safety copy is saved first.')) return;
    try {
      const res = await postFile('backup/restore/', file(), { confirm: 'yes' });
      toast(`Restored. Safety copy: ${res.safety_copy}`, 'success');
      mountBackup(root);
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
  };
}

export async function mountAuditLog(root) {
  const f = { action: '', from: '', to: '' };
  const load = async () => {
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
    const res = await api.get(`audit-log/?page_size=100${qs ? '&' + qs : ''}`);
    root.querySelector('#al-body').innerHTML = renderTable(['When', 'Who', 'Action', 'What', 'IP'], res.results.map((a) => ({
      When: fmtDateTime(a.at), Who: escapeHtml(a.username), Action: escapeHtml(a.action),
      What: escapeHtml([a.object_type, a.summary].filter(Boolean).join(' — ')), IP: escapeHtml(a.ip_address || '') })), { empty: 'Nothing logged yet.' })
      + `<p class="sub">${res.count} entries${res.num_pages > 1 ? ' (showing the newest 100 — filter or export for more)' : ''}</p>`;
  };
  root.innerHTML = `<h2 style="margin-top:0;">Audit log</h2>
    <div class="card"><div class="field-row">
      <div class="field"><label>Action starts with</label><input id="al-action" placeholder="login, user., approval…"></div>
      <div class="field"><label>From</label><input type="date" id="al-from"></div><div class="field"><label>To</label><input type="date" id="al-to"></div>
      <div class="field" style="align-self:flex-end;"><button class="btn" id="al-xlsx">Excel</button> <button class="btn" id="al-pdf">PDF</button></div></div></div>
    <div id="al-body" style="margin-top:12px;"></div>`;
  [['al-action', 'action'], ['al-from', 'from'], ['al-to', 'to']].forEach(([id, key]) => { el(id).onchange = () => { f[key] = el(id).value.trim(); load(); }; });
  const exportAs = (fmt) => { const qs = new URLSearchParams(Object.entries({ ...f, format: fmt }).filter(([, v]) => v)).toString(); window.location.href = `/360/api/audit-log/?${qs}`; };
  el('al-xlsx').onclick = () => exportAs('xlsx');
  el('al-pdf').onclick = () => exportAs('pdf');
  await load();
}
