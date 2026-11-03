// Backup & restore, and the audit log — Admin only (the server enforces it; this is just the screen).
import { api } from '../api.js';
import { el, escapeHtml, fmtDateTime, apiErrorMessage, renderTable, customConfirm } from '../ui.js';
import { loadBootstrap } from '../state.js';
import { mountRefView } from '../customer_common.js';

async function postFile(url, file, extra = {}) {
  const fd = new FormData();
  fd.append('file', file);
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  return api.post(url, fd);
}

const COUNT_LABELS = [['customers', 'Customers'], ['contacts', 'Contacts'], ['interactions', 'Interactions'], ['sales_documents', 'Sales documents'], ['payments', 'Payments'], ['tasks', 'Tasks'], ['users', 'Users'], ['branches', 'Branches']];

/** The Backup & restore page of the reference: a download panel with what a backup holds, and a restore panel. */
export async function mountBackup(root) {
  mountRefView(root, 'view-backup');
  const paintSummary = async () => {
    const s = await api.get('backup/summary/');
    el('backupSummary').innerHTML = COUNT_LABELS.map(([k, l]) => `<span style="display:inline-block;background:var(--accent-bg);border-radius:12px;padding:3px 11px;margin:0 6px 6px 0;font-size:12.5px;"><b>${s.counts[k]}</b> ${l}</span>`).join('')
      + `<div class="sub" style="margin-top:4px;">${s.last_backup_at ? 'Last backup downloaded: ' + new Date(s.last_backup_at).toLocaleString('en-IN') : 'No backup has been downloaded from this app yet — please take one.'}</div>`;
  };
  await paintSummary();
  el('backupBtn').onclick = () => {
    const a = document.createElement('a'); a.href = '/360/api/backup/export/'; a.download = ''; document.body.appendChild(a); a.click(); document.body.removeChild(a);
    el('backupHint').textContent = 'Backup downloaded. Keep it somewhere safe (not only on this computer).';
    setTimeout(paintSummary, 1500);
  };

  let described = null;
  const describeText = (d) => `${d.counts.customers} customers, ${d.counts.contacts} contacts, ${d.counts.sales_documents} sales documents, ${d.counts.payments} payments, ${d.counts.tasks} tasks, ${d.counts.users} users`
    + (d.created_at ? ` — backed up ${new Date(d.created_at).toLocaleString('en-IN')}` : '');
  el('restoreFileInput').onchange = async () => {
    described = null; el('restoreHint').textContent = '';
    const file = el('restoreFileInput').files[0]; if (!file) return;
    try {
      described = await postFile('backup/describe/', file);
      el('restoreHint').innerHTML = `This file has: <b>${escapeHtml(describeText(described))}</b>.`
        + (described.missing.length ? `<br>It is an older backup, so these are not in it and will be left empty: ${escapeHtml(described.missing.join(', '))}.` : '');
    } catch (e) { el('restoreHint').textContent = "That doesn't look like an Anupam 360 backup file."; }
  };
  el('restoreBtn').onclick = async () => {
    const file = el('restoreFileInput').files[0];
    if (!file) { el('restoreHint').textContent = 'Choose a backup file first.'; return; }
    if (!described) { el('restoreHint').textContent = "Couldn't read that backup file."; return; }
    if (!await customConfirm('Restore this backup?\n\n' + describeText(described) + '\n\nThis replaces the current data. A safety copy of the CURRENT data is saved first.')) return;
    try {
      const res = await postFile('backup/restore/', file, { confirm: 'yes' });
      el('restoreHint').textContent = `Restore complete. ${Object.keys(described.contains).length} sections restored. Safety copy of the previous data: ${res.safety_copy}.`;
      el('restoreFileInput').value = ''; described = null;
      await loadBootstrap(); paintSummary();
    } catch (e) { el('restoreHint').textContent = 'Restore failed: ' + apiErrorMessage(e) + ' Nothing was changed.'; }
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
