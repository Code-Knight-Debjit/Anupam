// Reports — simplified port of the original's multi-tab Reports page
// (`renderReportsPage`/`renderReportBody`, ~L14625-14665). Covers Sales
// Performance, Customer Activity, Not-contacted (gap), and Payment
// Collection. The original's deeper drill-down matrices (SalesX/CustX),
// the Interaction Log tab, and the granular User Performance tab are not
// ported — a deliberate simplification given their size, flagged in the
// final report.
import { api } from '../api.js';
import { state, isSalesManager } from '../state.js';
import { el, escapeHtml, fmtDate, fmtMoney, daysSinceDate, renderTable } from '../ui.js';

const TABS = [
  { key: 'sales', label: 'Sales Performance', hideFor: ['sales-manager'] },
  { key: 'customers', label: 'Customer Activity', hideFor: ['sales-manager'] },
  { key: 'gap', label: 'Not Contacted' },
  { key: 'payments', label: 'Payment Collection' },
];

async function renderSalesPerformance(root) {
  const types = ['enquiry', 'quotation', 'proforma', 'po', 'dc'];
  const docsByType = {};
  await Promise.all(types.map(async (t) => { docsByType[t] = await api.all('sales-documents/', { type: t }); }));
  const perPerson = {};
  state.salesPersons.forEach((p) => { perPerson[p.id] = { name: p.name, enquiry: 0, quotation: 0, proforma: 0, po: 0, dc: 0, value: 0 }; });
  types.forEach((t) => (docsByType[t] || []).forEach((d) => {
    const pid = d.sales_person_id;
    if (!pid || !perPerson[pid]) return;
    perPerson[pid][t] += 1;
    if (t === 'quotation') perPerson[pid].value += Number(d.total_amount) || 0;
  }));
  const rows = Object.values(perPerson).filter((r) => r.enquiry + r.quotation + r.proforma + r.po + r.dc > 0);
  root.innerHTML = `<h3 style="margin-bottom:10px;">Sales performance by person</h3>
    ${renderTable(['Sales person', 'Enquiries', 'Quotations', 'Proformas', 'POs', 'DCs', 'Quotation value'], rows.map((r) => ({
      'Sales person': escapeHtml(r.name), Enquiries: r.enquiry, Quotations: r.quotation, Proformas: r.proforma, POs: r.po, DCs: r.dc,
      'Quotation value': `₹${fmtMoney(r.value)}`,
    })), { empty: 'No sales activity yet.' })}`;
}

async function renderCustomerActivity(root) {
  const [customers, employees] = await Promise.all([api.all('customers/'), api.all('employees/')]);
  const perPerson = {};
  employees.forEach((e) => { perPerson[e.user_id] = { name: e.full_name, customers: 0 }; });
  customers.forEach((c) => { if (c.created_by && perPerson[c.created_by.id]) perPerson[c.created_by.id].customers += 1; });
  const rows = Object.values(perPerson).filter((r) => r.customers > 0).sort((a, b) => b.customers - a.customers);
  root.innerHTML = `<h3 style="margin-bottom:10px;">Customers added per employee</h3>
    ${renderTable(['Employee', 'Customers added'], rows.map((r) => ({ Employee: escapeHtml(r.name), 'Customers added': r.customers })), { empty: 'No customers added yet.' })}`;
}

async function renderGapReport(root) {
  const days = Number(root.dataset.gapDays || 30);
  const customers = await api.all('customers/');
  const contactLists = await Promise.all(customers.map((c) => api.all(`customers/${c.id}/contacts/`)));
  const interactionLists = await Promise.all(contactLists.map((contacts) => Promise.all(contacts.map((ct) => api.all(`contacts/${ct.id}/interactions/`))).then((ls) => ls.flat())));
  const rows = customers.map((c, i) => {
    const interactions = interactionLists[i];
    const last = interactions.sort((a, b) => b.date.localeCompare(a.date))[0];
    return { c, lastDate: last ? last.date : null, daysSince: last ? daysSinceDate(last.date) : Infinity };
  }).filter((r) => r.daysSince >= days).sort((a, b) => b.daysSince - a.daysSince);

  root.innerHTML = `
    <div class="flex-between"><h3 style="margin:0;">Customers with no call or visit in the last <input type="number" id="gapDays" value="${days}" style="width:60px;display:inline;"> days</h3></div>
    ${renderTable(['Customer', 'City', 'Last contact', 'Days since'], rows.map((r) => ({
      Customer: escapeHtml(r.c.name), City: escapeHtml(r.c.city),
      'Last contact': r.lastDate ? fmtDate(r.lastDate) : 'Never',
      'Days since': r.daysSince === Infinity ? '—' : r.daysSince,
    })), { empty: 'Every customer has been contacted recently.' })}`;
  root.querySelector('#gapDays').addEventListener('change', (e) => { root.dataset.gapDays = e.target.value; renderGapReport(root); });
}

async function renderPaymentsReport(root) {
  const [payments, customers] = await Promise.all([api.all('payment-collections/'), api.all('customers/')]);
  const customerName = (id) => { const c = customers.find((x) => x.id === id); return c ? c.name : `#${id}`; };
  const due = payments.filter((p) => Number(p.balance) > 0).sort((a, b) => Number(b.balance) - Number(a.balance));
  const total = due.reduce((s, p) => s + Number(p.balance), 0);
  root.innerHTML = `<h3 style="margin-bottom:10px;">Outstanding collections — ₹${fmtMoney(total)}</h3>
    ${renderTable(['Customer', 'Amount', 'Collected', 'Balance'], due.map((p) => ({
      Customer: escapeHtml(customerName(p.customer_id)), Amount: `₹${fmtMoney(p.amount)}`,
      Collected: `₹${fmtMoney(Number(p.amount) - Number(p.balance))}`, Balance: `₹${fmtMoney(p.balance)}`,
    })), { empty: 'Nothing outstanding.' })}`;
}

export async function mountReports(root) {
  const visibleTabs = TABS.filter((t) => !(isSalesManager() && t.hideFor && t.hideFor.includes('sales-manager')));
  const renderers = { sales: renderSalesPerformance, customers: renderCustomerActivity, gap: renderGapReport, payments: renderPaymentsReport };
  root.innerHTML = `
    <div class="tabbar">${visibleTabs.map((t, i) => `<button data-t="${t.key}" class="${i === 0 ? 'active' : ''}">${escapeHtml(t.label)}</button>`).join('')}</div>
    <div id="reportBody"></div>`;
  const body = root.querySelector('#reportBody');
  const show = (key) => {
    root.querySelectorAll('[data-t]').forEach((b) => b.classList.toggle('active', b.dataset.t === key));
    renderers[key](body);
  };
  root.querySelectorAll('[data-t]').forEach((btn) => btn.addEventListener('click', () => show(btn.dataset.t)));
  show(visibleTabs[0].key);
}
