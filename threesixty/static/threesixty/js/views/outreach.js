// Outreach — the reference's weekly call list: a progress banner with a ring, four tiles, a search / week / staff bar,
// and one card per call (grouped per person for Admin / Branch Manager). "Call Log" records a not-reached attempt
// (optionally with a call-again date → the server adds a call task); "Call Completed" saves remarks and adds a Call
// interaction on the contact. Assigning lives on the Customer list (Actions → Assign Call), as in the reference.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtDateTime, customAlert, customConfirm, apiErrorMessage, openModal, closeModal } from '../ui.js';

let filters = { week: '', staff: '' };
let search = '';
let list = [];
let root = null;

const me = () => state.me.user_id;
const canSeeAll = () => isAdmin() || isBranchManager();
const canDirect = () => isAdmin() || isBranchManager();            // reference: canDirectEditDelete()
const initialsOf = (name) => { const p = (name || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
const fmtDay = (iso, opts) => new Date(iso).toLocaleDateString('en-IN', opts);
function waLink(phone) {
  let digits = (phone || '').replace(/\D/g, '');
  if (digits.length === 10) digits = '91' + digits;
  return digits ? `https://wa.me/${digits}?text=${encodeURIComponent('Hi, ')}` : null;
}
function mondayOf(d) {
  const date = new Date(d); date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
const isCalled = (a) => a.status === 'Called';

async function load() {
  list = await api.all('call-assignments/');
  const open = list.filter((a) => a.assigned_to && a.assigned_to.id === me() && !isCalled(a)).length;
  const b = el('callingListBadge'); if (b) { b.textContent = open > 99 ? '99+' : open; b.style.display = open ? 'inline-block' : 'none'; }
}

function renderStats() {
  const total = list.length;
  const pending = list.filter((a) => !isCalled(a)).length;
  const called = list.filter(isCalled).length;
  const attempted = list.filter((a) => !isCalled(a) && (a.attempts || []).length).length;
  const thisWeek = mondayOf(new Date());
  const dueThisWeek = list.filter((a) => a.week_of === thisWeek && !isCalled(a)).length;
  const pct = total ? Math.round(called / total * 100) : 0;
  el('callingListHero').innerHTML = `<div class="dash-hero has-ring">
    <div class="hi"><div class="g">Outreach</div><div class="n">${pending ? pending + ' call' + (pending === 1 ? '' : 's') + ' to make' : 'All caught up 🎉'}</div>
      <div class="d">${called} of ${total} completed (${pct}%)</div>
      <div class="ol-prog" style="max-width:min(100%,420px);"><i style="width:${pct}%"></i></div>
      <div class="chips"><span class="hchip">${dueThisWeek} due this week</span><span class="hchip">${attempted} attempted, not reached</span></div></div>
    <div class="ol-ring" style="--p:${pct}" title="${pct}% completed"><b>${pct}%</b><small>done</small></div>
  </div>`;
  el('callingListStatsRow').innerHTML = `
    <div class="dash-card pipe-1"><span class="ic">📋</span><div class="n">${total}</div><div class="l">Total assigned</div></div>
    <div class="dash-card pipe-4${pending ? '' : ' zero'}"><span class="ic">⏳</span><div class="n">${pending}</div><div class="l">Pending</div></div>
    <div class="dash-card pipe-2${dueThisWeek ? '' : ' zero'}"><span class="ic">📅</span><div class="n">${dueThisWeek}</div><div class="l">Pending this week</div></div>
    <div class="dash-card pipe-3${called ? '' : ' zero'}"><span class="ic">✅</span><div class="n">${called}</div><div class="l">Called</div></div>`;
}

function renderFilters() {
  const weeks = [...new Set(list.map((a) => a.week_of))].sort().reverse();
  const weekOptions = weeks.map((w) => `<option value="${w}">Week of ${fmtDay(w)}</option>`).join('');
  const staffOptions = canSeeAll() ? state.employees.map((e) => `<option value="${e.user_id}">${escapeHtml(e.full_name)}</option>`).join('') : '';
  const row = el('callingListFilterRow');
  row.className = 'ol-bar';
  row.innerHTML = `
    <div class="search"><input type="text" id="clSearch" placeholder="Search customer or contact" value="${escapeHtml(search)}"></div>
    <select id="clFilterWeek"><option value="">All weeks</option>${weekOptions}</select>
    ${canSeeAll() ? `<select id="clFilterStaff"><option value="">All staff</option>${staffOptions}</select>` : ''}`;
  el('clFilterWeek').value = filters.week;
  el('clFilterWeek').addEventListener('change', (e) => { filters.week = e.target.value; renderItems(); });
  el('clSearch').addEventListener('input', (e) => { search = e.target.value; renderItems(); });
  const sf = el('clFilterStaff');
  if (sf) { sf.value = filters.staff; sf.addEventListener('change', (e) => { filters.staff = e.target.value; renderItems(); }); }
}

function cardHtml(a) {
  const phone = a.contact_phone || '';
  const wa = phone ? waLink(phone) : null;
  const called = isCalled(a);
  const attempts = a.attempts || [];
  const last = attempts.length ? attempts[attempts.length - 1] : null;
  const cls = called ? 'done' : (attempts.length ? 'att' : '');
  const statusTxt = called ? 'Called' : (attempts.length ? `Attempted · ${escapeHtml(last.reason)} (${attempts.length})` : 'Pending');
  const canAct = (a.assigned_to && a.assigned_to.id === me()) || canDirect();
  const initial = ((a.customer_name || '?').trim()[0] || '?').toUpperCase();
  const tel = phone ? phone.replace(/[^\d+]/g, '') : '';
  const byName = escapeHtml((a.assigned_by && a.assigned_by.full_name) || '—');
  return `
    <div class="ol-card ${cls}">
      <div class="ol-top">
        <div class="ol-av">${escapeHtml(initial)}</div>
        <div style="min-width:0;flex:1;">
          <div class="ol-name" data-customer="${a.customer_id}">${escapeHtml(a.customer_name || '—')}</div>
          <div class="ol-sub">👤 ${escapeHtml(a.contact_name || 'No primary contact')}${phone ? ' · ' + escapeHtml(phone) : ''}</div>
        </div>
      </div>
      <div class="ol-chips">
        <span class="ol-chip k">${called ? '✓ ' : ''}${statusTxt}</span>
        <span class="ol-chip">📅 Week of ${fmtDay(a.week_of, { day: '2-digit', month: 'short' })}</span>
        <span class="ol-chip" title="Assigned by ${byName}">➜ ${escapeHtml((a.assigned_to && a.assigned_to.full_name) || '—')}</span>
      </div>
      ${last && !called ? `<div class="ol-note"><b>Last attempt:</b> ${escapeHtml(last.reason)}${last.note ? ' — ' + escapeHtml(last.note) : ''} · ${fmtDateTime(last.at)}${last.call_again_date ? ' · Call again on ' + fmtDay(last.call_again_date) : ''}</div>` : ''}
      ${called ? `<div class="ol-note"><b style="color:var(--wa);">Remarks:</b> ${escapeHtml(a.remarks || '—')} · ${fmtDateTime(a.called_at)} by ${escapeHtml((a.called_by && a.called_by.full_name) || '—')}</div>` : ''}
      <div class="ol-act">
        ${!called && tel ? `<a class="btn" style="text-decoration:none;" href="tel:${escapeHtml(tel)}">📞 Dial</a>` : ''}
        ${wa && !called ? `<a class="btn" style="text-decoration:none;" href="${wa}" target="_blank" rel="noopener">💬 WhatsApp</a>` : ''}
        ${!called && canAct ? `<button class="btn" data-notreached="${a.id}">Call Log</button><button class="btn btn-call-done" data-completed="${a.id}">✓ Call Completed</button>` : ''}
        ${called && canAct ? `<button class="btn btn-icon" data-completed="${a.id}">Edit remarks</button>` : ''}
        ${canDirect() ? `<button class="btn-danger-text" data-remove="${a.id}">Remove</button>` : ''}
      </div>
    </div>`;
}

function renderItems() {
  let items = list.slice();
  if (filters.week) items = items.filter((a) => a.week_of === filters.week);
  items = items.filter((a) => !isCalled(a));             // completed calls drop off the list (they stay in Reports → Interaction Log)
  if (filters.staff) items = items.filter((a) => a.assigned_to && String(a.assigned_to.id) === String(filters.staff));
  const q = search.trim().toLowerCase();
  if (q) items = items.filter((a) => [a.customer_name, a.contact_name, a.assigned_to && a.assigned_to.full_name].some((v) => (v || '').toLowerCase().includes(q)));
  items.sort((a, b) => new Date(b.week_of) - new Date(a.week_of));
  el('callingListSubline').textContent = items.length ? `${items.length} call${items.length === 1 ? '' : 's'} in your outreach list.`
    : (list.length ? (list.some((a) => !isCalled(a)) ? 'No calls match your filters.' : 'All calls done — nothing pending.')
      : 'No outreach list yet. Assign one from the Customer list (Actions → Assign Call).');
  const wrap = el('callingListWrap');
  if (canSeeAll() && !filters.staff && items.length) {
    const groups = []; const byId = new Map();
    items.forEach((a) => {
      const key = a.assigned_to ? a.assigned_to.id : '__unassigned';
      if (!byId.has(key)) { const g = { name: (a.assigned_to && a.assigned_to.full_name) || 'Unassigned', items: [] }; byId.set(key, g); groups.push(g); }
      byId.get(key).items.push(a);
    });
    groups.sort((x, y) => (x.name || '').localeCompare(y.name || ''));
    wrap.innerHTML = groups.map((g) => `
      <div class="tsec"><span class="avatar">${escapeHtml(initialsOf(g.name))}</span><span>${escapeHtml(g.name)}</span><span class="tag" style="background:var(--panel-2); color:var(--text-faint);">${g.items.length} call${g.items.length === 1 ? '' : 's'}</span></div>
      <div class="ol-grid">${g.items.map(cardHtml).join('')}</div>`).join('');
  } else {
    wrap.innerHTML = items.length ? `<div class="ol-grid">${items.map(cardHtml).join('')}</div>` : '<p class="sub">No calls yet.</p>';
  }
  wrap.querySelectorAll('[data-customer]').forEach((n) => n.onclick = () => navigate('customerview', n.dataset.customer));
  wrap.querySelectorAll('[data-notreached]').forEach((b) => b.onclick = () => openNotReached(find(b.dataset.notreached)));
  wrap.querySelectorAll('[data-completed]').forEach((b) => b.onclick = () => openCompleted(find(b.dataset.completed)));
  wrap.querySelectorAll('[data-remove]').forEach((b) => b.onclick = () => removeEntry(b.dataset.remove));
}

const find = (id) => list.find((a) => String(a.id) === String(id));
const refresh = async () => { await load(); renderStats(); renderFilters(); renderItems(); };

async function removeEntry(id) {
  if (!canDirect()) { await customAlert('Only an admin or branch manager can remove an outreach list entry.'); return; }
  if (!await customConfirm('Remove this entry from the outreach list?')) return;
  try { await api.delete(`call-assignments/${id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); }
  await refresh();
}

function sub(a) { return `${escapeHtml(a.customer_name)}${a.contact_name ? ' — ' + escapeHtml(a.contact_name) : ''}`; }
async function guard(a) {
  if (a && ((a.assigned_to && a.assigned_to.id === me()) || canDirect())) return true;
  await customAlert('Only the assigned staff member, an admin, or a branch manager can update this call.');
  return false;
}

async function openCompleted(a) {
  if (!a || !await guard(a)) return;
  openModal(`
    <h2>Call Completed</h2>
    <p class="modal-sub">${sub(a)} &middot; Week of ${fmtDay(a.week_of)}</p>
    <div class="field"><label for="callRemarksText">Remarks</label>
      <textarea id="callRemarksText" rows="4" placeholder="What did the customer say? Any follow-up needed?">${escapeHtml(a.remarks || '')}</textarea></div>
    <p class="sub" style="margin-top:-6px;">This is saved against the call list entry and added to the customer's contact profile as a Call interaction.</p>
    <div class="modal-actions"><button class="btn" id="callRemarksCancelBtn">Cancel</button><button class="btn btn-primary" id="callRemarksSaveBtn">Save call completed</button></div>`, {
    size: 'narrow',
    onMount: (m) => {
      m.querySelector('#callRemarksCancelBtn').onclick = closeModal;
      m.querySelector('#callRemarksSaveBtn').onclick = async () => {
        try { await api.patch(`call-assignments/${a.id}/`, { status: 'Called', remarks: m.querySelector('#callRemarksText').value.trim() }); }
        catch (e) { await customAlert(apiErrorMessage(e)); return; }
        closeModal(); await refresh();
      };
    },
  });
}

async function openNotReached(a) {
  if (!a || !await guard(a)) return;
  openModal(`
    <h2>Call Log</h2>
    <p class="modal-sub">${sub(a)}</p>
    <div class="field"><label for="cnrReason">Reason</label>
      <select id="cnrReason"><option>Not reachable</option><option>No answer</option><option>Switched off</option><option>Busy</option><option>Wrong number</option></select></div>
    <div class="field"><label for="cnrNote">Note (optional)</label><textarea id="cnrNote" rows="2" placeholder="Anything worth remembering for the next attempt"></textarea></div>
    <div class="field"><label for="cnrAgain">Call again on (optional)</label><input type="date" id="cnrAgain"></div>
    <p class="sub" style="margin-top:-6px;">The entry stays pending. This attempt is not counted as a completed call. If you pick a date, a call task is added for you.</p>
    <div class="modal-actions"><button class="btn" id="cnrCancelBtn">Cancel</button><button class="btn btn-primary" id="cnrSaveBtn">Save attempt</button></div>`, {
    size: 'narrow',
    onMount: (m) => {
      m.querySelector('#cnrCancelBtn').onclick = closeModal;
      m.querySelector('#cnrSaveBtn').onclick = async () => {
        try {
          await api.post(`call-assignments/${a.id}/attempts/`, { reason: m.querySelector('#cnrReason').value, note: m.querySelector('#cnrNote').value.trim(), call_again_date: m.querySelector('#cnrAgain').value || null });
        } catch (e) { await customAlert(apiErrorMessage(e)); return; }
        closeModal(); await refresh();
      };
    },
  });
}

export async function mountOutreach(rootEl) {
  root = rootEl;
  rootEl.innerHTML = `
    <div class="view active glassv" id="view-callinglist">
      <div class="view-head"><div>
        <p class="brand-eyebrow">Work</p><h1>Outreach</h1><p class="sub" id="callingListSubline">Loading&hellip;</p>
      </div></div>
      <div id="callingListHero"></div>
      <div class="dash-grid" id="callingListStatsRow" style="margin-bottom:16px;"></div>
      <div class="filter-row" id="callingListFilterRow"></div>
      <div id="callingListWrap"></div>
    </div>`;
  await load();
  renderStats(); renderFilters(); renderItems();
}
