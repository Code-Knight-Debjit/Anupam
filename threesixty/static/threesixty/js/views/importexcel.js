// Import Excel — bulk customer+contact upload, ported from the original's
// `TEMPLATE_COLS`/import handler (contact_management.html ~L6434-6551).
// One row = one company + (optionally) one contact person; repeat the
// company name on further rows to add more contacts. Existing customers are
// matched by exact (trimmed, case-insensitive) name and updated in place —
// blank cells never overwrite existing data. `Industry`/`Source`/`Potential`/
// `Transport Preference`/`Courier Preference` are free text on the Customer
// model (not foreign keys), so no lookup resolution is needed for them.
// `Preferred Languages`/`Interested Brands`/`Interested Products` are matched
// against existing LookupItem names (unmatched names are reported, not
// auto-created — a deliberate, flagged simplification). `Assigned To` is
// matched against employee full names.
import { api } from '../api.js';
import { el, escapeHtml, toast, loadScript } from '../ui.js';

const TEMPLATE_COLS = [
  'Company', 'Plant', 'Address', 'Area', 'City', 'State', 'Pincode', 'Website', 'GST Number', 'Plant Location',
  'Head Office Name', 'Head Office Address', 'Head Office City', 'Head Office State', 'Head Office Pincode', 'Head Office Phone', 'Head Office Location',
  'Industry', 'Source', 'Potential', 'Transport Preference', 'Courier Preference', 'Preferred Languages', 'Assigned To',
  'Interested Brands', 'Interested Products', 'Contact Name', 'Job Title', 'Phone', 'Phone 2', 'Email',
];

async function getXlsx() {
  if (!window.XLSX) {
    if (!window.THREESIXTY_VENDOR || !window.THREESIXTY_VENDOR.xlsx) throw new Error('Excel library is not configured.');
    await loadScript(window.THREESIXTY_VENDOR.xlsx);
  }
  return window.XLSX;
}

function canon(s) { return String(s || '').toLowerCase().replace(/\s+/g, ' ').trim(); }

function titleCaseWords(s) {
  return String(s || '').replace(/\w\S*/g, (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
}

function geoParse(txt) {
  const m = String(txt || '').trim().match(/(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/);
  return m ? { lat: Number(m[1]), lng: Number(m[2]) } : null;
}

async function downloadTemplate() {
  const XLSX = await getXlsx();
  const sample = [{
    Company: 'Sundaram Fasteners Ltd', Plant: 'Unit 2', Address: 'Plot 12, Industrial Estate', Website: 'www.sundaramfasteners.com',
    'GST Number': '29ABCDE1234F1Z5', Area: 'Peenya', City: 'Bengaluru', State: 'Karnataka', Pincode: '560058', 'Plant Location': '13.0285, 77.5197',
    'Head Office Name': 'Corporate Office', 'Head Office Address': 'No. 98A, Anna Salai', 'Head Office City': 'Chennai', 'Head Office State': 'Tamil Nadu',
    'Head Office Pincode': '600002', 'Head Office Phone': '044 1234 5678', 'Head Office Location': 'https://www.google.com/maps?q=13.0827,80.2707',
    Industry: 'Gearbox Manufacturing', Source: 'Referral', Potential: 'High', 'Transport Preference': '', 'Courier Preference': '',
    'Preferred Languages': 'English, Kannada', 'Assigned To': '', 'Interested Brands': 'Timken, SKF', 'Interested Products': 'Spherical Roller Bearing',
    'Contact Name': 'Ramesh Iyer', 'Job Title': 'Purchase', Phone: '9876543210', 'Phone 2': '', Email: 'ramesh@example.com',
  }];
  const ws = XLSX.utils.json_to_sheet(sample, { header: TEMPLATE_COLS });
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Template');
  const notes = [
    ['Column', 'What to enter'],
    ['Company', 'Required. Rows with the same company name are merged; each row can add one contact person.'],
    ['Plant', 'Plant / unit name (optional).'],
    ['Plant Location', 'Map pin of the plant: "latitude, longitude" (e.g. 13.0285, 77.5197) or a full Google Maps link.'],
    ['Head Office …', 'Fill these only when the head office is different. Head Office Location works like Plant Location.'],
    ['Potential', 'High, Medium or Low.'],
    ['Preferred Languages / Interested Brands / Interested Products / Assigned To', 'Separate several values with commas. Must match existing names exactly (set these up in Manage lists / Users first).'],
    ['Contact Name, Job Title, Phone, Phone 2, Email', 'One contact person per row. Repeat the Company on the next row to add another contact.'],
    ['Tip', 'Leave a cell blank to keep what is already saved for an existing customer.'],
  ];
  const wn = XLSX.utils.aoa_to_sheet(notes);
  wn['!cols'] = [{ wch: 46 }, { wch: 100 }];
  XLSX.utils.book_append_sheet(wb, wn, 'Instructions');
  XLSX.writeFile(wb, 'anupam360-import-template.xlsx');
}

function buildCompanyRows(rawRows) {
  const byName = new Map();
  rawRows.forEach((r) => {
    const name = titleCaseWords(String(r.Company || '').trim());
    if (!name) return;
    const key = name.toLowerCase();
    let comp = byName.get(key);
    if (!comp) {
      comp = { name, fields: {}, contacts: [], badPins: [] };
      byName.set(key, comp);
    }
    const setIf = (col, field, transform) => { if (r[col]) comp.fields[field] = transform ? transform(String(r[col])) : String(r[col]).trim(); };
    setIf('Plant', 'plant');
    setIf('Address', 'address', titleCaseWords);
    setIf('Website', 'website');
    setIf('GST Number', 'gst_number', (v) => v.trim().toUpperCase());
    setIf('Area', 'area');
    setIf('City', 'city');
    setIf('State', 'state');
    setIf('Pincode', 'pincode');
    setIf('Head Office Name', 'ho_name');
    setIf('Head Office Address', 'ho_address', titleCaseWords);
    setIf('Head Office City', 'ho_city');
    setIf('Head Office State', 'ho_state');
    setIf('Head Office Pincode', 'ho_pincode');
    setIf('Head Office Phone', 'ho_phone');
    const putGeo = (col, latField, lngField) => {
      const txt = String(r[col] || '').trim();
      if (!txt) return;
      const g = geoParse(txt);
      if (g) { comp.fields[latField] = g.lat; comp.fields[lngField] = g.lng; } else comp.badPins.push(`${name} — ${col}`);
    };
    putGeo('Plant Location', 'plant_geo_lat', 'plant_geo_lng');
    putGeo('Head Office Location', 'ho_geo_lat', 'ho_geo_lng');
    if (r.Potential) { const pm = { high: 'High', medium: 'Medium', low: 'Low' }[String(r.Potential).trim().toLowerCase()]; if (pm) comp.fields.potential = pm; }
    setIf('Transport Preference', 'transport_preference');
    setIf('Courier Preference', 'courier_preference');
    setIf('Industry', 'industry');
    setIf('Source', 'source');
    if (r['Preferred Languages']) comp.preferredLanguages = String(r['Preferred Languages']).split(',').map((s) => s.trim()).filter(Boolean);
    if (r['Assigned To']) comp.assignedTo = String(r['Assigned To']).split(',').map((s) => s.trim()).filter(Boolean);
    if (r['Interested Brands']) comp.interestedBrands = String(r['Interested Brands']).split(',').map((s) => s.trim()).filter(Boolean);
    if (r['Interested Products']) comp.interestedProducts = String(r['Interested Products']).split(',').map((s) => s.trim()).filter(Boolean);

    const cName = titleCaseWords(String(r['Contact Name'] || '').trim());
    const cPhone = String(r.Phone || '').trim();
    const cPhone2 = String(r['Phone 2'] || '').trim();
    const cEmail = String(r.Email || '').trim();
    if (cName || cPhone || cPhone2 || cEmail) {
      const exists = comp.contacts.some((ct) => ct.name.toLowerCase() === cName.toLowerCase() && ct.phone === cPhone);
      if (!exists) comp.contacts.push({ name: cName, job_title: String(r['Job Title'] || '').trim(), phone: cPhone, phone2: cPhone2, email: cEmail });
    }
  });
  return [...byName.values()];
}

async function runImport(file, resultEl, hintEl) {
  hintEl.textContent = '';
  resultEl.style.display = 'none';
  resultEl.textContent = '';
  let XLSX;
  try { XLSX = await getXlsx(); } catch (e) { hintEl.textContent = e.message; return; }

  const buf = await file.arrayBuffer();
  let rawRows;
  try {
    const wb = XLSX.read(buf, { type: 'array' });
    const sheet = wb.Sheets[wb.SheetNames[0]];
    const canonMap = new Map(TEMPLATE_COLS.map((c) => [canon(c), c]));
    rawRows = XLSX.utils.sheet_to_json(sheet, { defval: '' }).map((r) => {
      const o = {};
      Object.keys(r).forEach((k) => { o[canonMap.get(canon(k)) || k] = r[k]; });
      return o;
    });
  } catch (e) {
    hintEl.textContent = "Couldn't read that file. Make sure it matches the template columns.";
    return;
  }
  if (rawRows.length === 0) { hintEl.textContent = 'That file has no rows.'; return; }
  if (!rawRows.some((r) => r.Company !== undefined)) { hintEl.textContent = 'No "Company" column found. Download the template and use its column names.'; return; }

  const companyRows = buildCompanyRows(rawRows);
  const [existingCustomers, employees, languages, brands, products] = await Promise.all([
    api.all('customers/'), api.all('employees/'), api.all('lookups/', { kind: 'language' }),
    api.all('lookups/', { kind: 'brand' }), api.all('lookups/', { kind: 'product' }),
  ]);
  const existingByName = new Map(existingCustomers.map((c) => [c.name.trim().toLowerCase(), c]));
  const employeeByName = new Map(employees.map((e) => [e.full_name.trim().toLowerCase(), e.user_id]));
  const lookupByName = (list) => new Map(list.map((l) => [l.name.trim().toLowerCase(), l.id]));
  const languageByName = lookupByName(languages), brandByName = lookupByName(brands), productByName = lookupByName(products);
  const resolveIds = (names, map, unresolved) => {
    const ids = [];
    (names || []).forEach((n) => { const id = map.get(n.toLowerCase()); if (id != null) ids.push(id); else unresolved.push(n); });
    return ids;
  };

  let newCompanies = 0, updatedCompanies = 0, newContacts = 0;
  const badPins = [], unresolvedNames = [];

  for (const comp of companyRows) {
    const existing = existingByName.get(comp.name.toLowerCase());
    const payload = { ...comp.fields };
    if (comp.preferredLanguages) payload.preferred_language_ids = resolveIds(comp.preferredLanguages, languageByName, unresolvedNames);
    if (comp.interestedBrands) payload.interested_brand_ids = resolveIds(comp.interestedBrands, brandByName, unresolvedNames);
    if (comp.interestedProducts) payload.interested_product_ids = resolveIds(comp.interestedProducts, productByName, unresolvedNames);
    if (comp.assignedTo) payload.assigned_to_ids = resolveIds(comp.assignedTo, employeeByName, unresolvedNames);
    badPins.push(...comp.badPins);

    let customerId;
    try {
      if (existing) {
        await api.patch(`customers/${existing.id}/`, { ...payload, version: existing.version });
        customerId = existing.id;
        updatedCompanies += 1;
      } else {
        const created = await api.post('customers/', { name: comp.name, ...payload });
        customerId = created.id;
        existingByName.set(comp.name.toLowerCase(), created);
        newCompanies += 1;
      }
    } catch (e) {
      unresolvedNames.push(`${comp.name} (save failed: ${e.message || e})`);
      continue;
    }

    if (comp.contacts.length) {
      let existingContacts = [];
      try { existingContacts = await api.all(`customers/${customerId}/contacts/`); } catch (e) { /* new customer, no contacts yet */ }
      for (const ct of comp.contacts) {
        const dup = existingContacts.some((ec) => ec.name.toLowerCase() === ct.name.toLowerCase() && (ec.phone || '') === ct.phone);
        if (dup) continue;
        try { await api.post(`customers/${customerId}/contacts/`, ct); newContacts += 1; } catch (e) { /* skip row on failure, continue importing the rest */ }
      }
    }
  }

  let msg = `Imported ${newCompanies} new customer(s), updated ${updatedCompanies}, added ${newContacts} new contact(s).`;
  if (badPins.length) msg += ` Map location not understood for: ${badPins.slice(0, 5).join('; ')}${badPins.length > 5 ? '…' : ''}.`;
  if (unresolvedNames.length) msg += ` Could not match: ${unresolvedNames.slice(0, 5).join('; ')}${unresolvedNames.length > 5 ? '…' : ''}.`;
  resultEl.textContent = msg;
  resultEl.style.display = 'block';
}

export async function mountImportExcel(root) {
  root.innerHTML = `
    <h2 style="margin-top:0;">Import Excel</h2>
    <div class="card" style="max-width:640px;margin-bottom:var(--sp-3);">
      <p class="sub">Download the template and fill it in — one row per contact person; repeat the company name to add more.</p>
      <button class="btn" id="downloadTemplateBtn">Download template</button>
    </div>
    <div class="card" style="max-width:640px;">
      <div class="field"><label>File to import (.xlsx, .xls, .csv)</label><input type="file" id="importFileInput" accept=".xlsx,.xls,.csv"></div>
      <button class="btn primary" id="importFileBtn">Import file</button>
      <p class="sub" id="importHint" style="color:var(--error);"></p>
      <div class="sub import-result" id="importResult" style="display:none;margin-top:10px;"></div>
    </div>`;

  const resultEl = el('importResult');

  el('downloadTemplateBtn').addEventListener('click', async () => {
    try { await downloadTemplate(); } catch (e) { toast(e.message || 'Could not build the template.', 'error'); }
  });
  el('importFileBtn').addEventListener('click', async () => {
    const file = el('importFileInput').files[0];
    const hintEl = el('importHint');
    if (!file) { hintEl.textContent = 'Choose a file first.'; return; }
    const btn = el('importFileBtn');
    btn.disabled = true; btn.textContent = 'Importing…';
    try { await runImport(file, resultEl, hintEl); } finally { btn.disabled = false; btn.textContent = 'Import file'; }
  });
}
