// Pasting a table (from an email, Excel or Word) or tab-separated text into a Remarks box lines it up in neat columns
// (reference: pasteAlignRows / pasteHtmlToAlignedText / pasteAlignText). Ordinary text is pasted as usual.
export function pasteAlignRows(rows, headerRow) {
  const clean = rows.map((r) => r.map((c) => String(c || '').replace(/\s+/g, ' ').trim()));
  const n = Math.max(...clean.map((r) => r.length));
  const w = Array.from({ length: n }, (_, i) => Math.max(...clean.map((r) => (r[i] || '').length)));
  const line = (r) => w.map((x, i) => (r[i] || '').padEnd(x)).join('  ').replace(/\s+$/, '');
  const out = clean.map(line);
  if (headerRow) out.splice(1, 0, w.map((x) => '-'.repeat(x)).join('  '));
  return out.join('\n');
}
export function pasteHtmlToAlignedText(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  if (!doc.querySelector('table')) return null;
  doc.querySelectorAll('table').forEach((tb) => {
    const trs = [...tb.querySelectorAll('tr')].filter((tr) => tr.closest('table') === tb);
    const rows = trs.map((tr) => [...tr.children].filter((c) => /^(td|th)$/i.test(c.tagName)).map((c) => c.textContent));
    const hasTh = trs.length && [...trs[0].children].some((c) => /^th$/i.test(c.tagName));
    const pre = doc.createElement('pre'); pre.textContent = '\n' + pasteAlignRows(rows.filter((r) => r.length), hasTh) + '\n';
    tb.replaceWith(pre);
  });
  let out = '';
  const walk = (n) => {
    if (n.nodeType === 3) { out += n.parentNode && n.parentNode.tagName === 'PRE' ? n.textContent : n.textContent.replace(/\s+/g, ' '); return; }
    if (n.nodeType !== 1) return;
    const t = n.tagName.toLowerCase();
    if (['style', 'script', 'head'].includes(t)) return;
    if (t === 'br') { out += '\n'; return; }
    n.childNodes.forEach(walk);
    if (['p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'pre', 'ul', 'ol'].includes(t)) out += '\n';
  };
  walk(doc.body);
  return out.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}
export function pasteAlignText(text) {
  const lines = text.replace(/\r/g, '').split('\n');
  if (lines.filter((l) => l.includes('\t')).length < 2) return null;
  return pasteAlignRows(lines.filter((l) => l.trim() !== '').map((l) => l.split('\t')), false);
}
const looksTabular = (txt) => { const ls = (txt || '').split('\n'); return ls.length > 2 && ls.filter((l) => /\S {2,}\S/.test(l)).length >= 2; };

/** Gives a textarea the paste behaviour, and the monospaced look while its text is a table. */
export function enablePasteTable(ta) {
  const sync = () => { const tab = looksTabular(ta.value); ta.classList.toggle('rem-table', tab); if (tab && ta.rows < 8) ta.rows = 8; };
  ta.addEventListener('paste', (e) => {
    const cd = e.clipboardData; if (!cd) return;
    let aligned = null;
    const html = cd.getData('text/html');
    if (html && /<table/i.test(html)) aligned = pasteHtmlToAlignedText(html);
    if (aligned == null) aligned = pasteAlignText(cd.getData('text/plain') || '');
    if (aligned == null) return;
    e.preventDefault();
    ta.setRangeText(aligned, ta.selectionStart, ta.selectionEnd, 'end');
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    sync();
  });
  ta.addEventListener('input', sync);
  sync();
}
