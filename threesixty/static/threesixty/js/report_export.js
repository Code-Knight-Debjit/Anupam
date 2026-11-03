// The shared look of every PDF / Print export in the reference: company letterhead, title block, summary cards, tables
// (or sections with a heading, a line of figures and an attendance calendar), running header and footer, and the
// branch watermark. `exportRowsToPdf(rows, title, prefix, opts)` and `printRowsTable(rows, title, opts)` take the same
// `opts` ({ subtitle, cards, sections, legend, branch }); a plain array in place of `opts` is the old "columns" form.
import { state } from './state.js';
import { escapeHtml, customAlert, getJsPdf, getXlsx } from './ui.js';

const ACCENT = '#d97b2f';
const hexRgb = (h) => { h = String(h || ACCENT).replace('#', ''); if (h.length === 3) h = h.split('').map((c) => c + c).join(''); const n = parseInt(h, 16); return Number.isNaN(n) ? [217, 123, 47] : [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const pdfText = (v) => String(v == null ? '' : v).replace(/\(₹\)/g, '(Rs.)').replace(/₹\s?/g, 'Rs. ').replace(/[−]/g, '-').replace(/[✓✔]/g, 'Yes').replace(/[^\x00-\xFF–—‘’“”•]/g, '');
const title = (t) => String(t || 'Report').replace(/^Anupam 360\s*[—-]\s*/, '');
const STATUS_COLORS = [
  [/^present \(late\)|^late|^overdue|^no follow-up|^pending|^open/i, '#c98a0b'], [/^present|^won|^win|^completed|^complete|^done|^yes|^scheduled ok/i, '#2f9e52'],
  [/^half/i, '#e07a2c'], [/^absent|^lose|^lost|^regretted|^rejected/i, '#d9534f'], [/^leave|^scheduled|^follow-up logged/i, '#3a7bd5'],
  [/^off|^weekly off|^holiday|^hold|^part pending/i, '#7b8794'], [/^visit|^appointment/i, '#1f8a78'], [/^call|^cold call|^follow-up call|^outreach/i, '#3a7bd5'],
];
export function statusColor(txt) { const t = String(txt || '').trim(); for (const [re, c] of STATUS_COLORS) if (re.test(t)) return c; return null; }
export const isStatusCol = (c) => /^(status|type)$/i.test(c);
const generated = () => 'Generated ' + new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) + ' ' + new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) + (state.me && (state.me.full_name || state.me.username) ? ' by ' + (state.me.full_name || state.me.username) : '');

// ---- letterhead & watermark ------------------------------------------------------------------------------------------------------
/** The branch the export is for (named, else the signed-in user's own, else the first). */
function branchOf(name) {
  if (name) { const b = state.branches.find((x) => x.name === name); if (b) return b; }
  return state.branches.find((x) => (state.me.branch_ids || []).includes(x.id)) || state.branches[0] || null;
}
export function branchLetterhead(name) {
  const b = branchOf(name) || {};
  return {
    logo: b.logo_url || window.THREESIXTY_LOGO || '', companyName: b.letterhead_name || b.name || 'Anupam Bearings', address: b.letterhead_address || '',
    phone: b.letterhead_phone || '', mobile: b.letterhead_mobile || '', email: b.letterhead_email || '', website: b.letterhead_website || '',
    gstNumber: b.letterhead_gstin || '', udyamNumber: b.udyam_number || '', accentColor: b.accent_color || ACCENT, branch: b,
  };
}
const contactLine = (lh) => [lh.phone, lh.mobile, lh.email, lh.website].filter(Boolean).join('   |   ');
const regLine = (lh) => [lh.gstNumber ? 'GSTIN: ' + lh.gstNumber : '', lh.udyamNumber ? 'Udyam: ' + lh.udyamNumber : ''].filter(Boolean).join('   |   ');
const SIZE = { small: 30, medium: 50, large: 75 };
const sizeKey = (n) => (n <= 40 ? 'small' : n >= 65 ? 'large' : 'medium');
function watermark(name) {
  const b = branchOf(name);
  if (!b || !b.watermark_enabled) return null;
  const text = String(b.watermark_text || '').trim();
  if (b.watermark_type === 'text' && !text) return null;
  return { type: b.watermark_type === 'text' ? 'text' : 'logo', text: text.toUpperCase(), size: sizeKey(b.watermark_size || 50), lh: branchLetterhead(b.name) };
}
async function dataUrl(src) {
  if (!src || /^data:/.test(src)) return src || '';
  try {
    const blob = await (await fetch(src, { credentials: 'same-origin' })).blob();
    return await new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => res(''); r.readAsDataURL(blob); });
  } catch (e) { return ''; }
}
const imageSize = (src) => new Promise((res) => { const i = new Image(); i.onload = () => res(i.naturalWidth / (i.naturalHeight || 1) || 1); i.onerror = () => res(1); i.src = src; });
const fitBox = (aspect, maxW, maxH) => { let w = maxW, h = w / aspect; if (h > maxH) { h = maxH; w = h * aspect; } return { w, h }; };

function pdfWatermark(doc, wm, logo) {
  if (!wm) return;
  try {
    const pw = doc.internal.pageSize.getWidth(), ph = doc.internal.pageSize.getHeight(), n = doc.internal.getNumberOfPages();
    if (wm.type === 'logo') {
      if (!logo) return;
      const frac = { small: 0.3, medium: 0.5, large: 0.75 }[wm.size];
      let w = pw * frac, h = w / logo.aspect;
      if (h > ph * 0.8) { h = ph * 0.8; w = h * logo.aspect; }
      for (let p = 1; p <= n; p++) {
        doc.setPage(p); doc.saveGraphicsState(); doc.setGState(new doc.GState({ opacity: 0.1 }));
        doc.addImage(logo.data, /^data:image\/jpe?g/i.test(logo.data) ? 'JPEG' : 'PNG', (pw - w) / 2, (ph - h) / 2, w, h); doc.restoreGraphicsState();
      }
      return;
    }
    const frac = { small: 0.4, medium: 0.6, large: 0.82 }[wm.size];
    const diag = Math.sqrt(pw * pw + ph * ph), ang = Math.atan2(ph, pw) * 180 / Math.PI, rad = ang * Math.PI / 180;
    doc.setFont('helvetica', 'bold'); doc.setFontSize(100);
    let size = Math.min(100 * (diag * frac) / (doc.getTextWidth(wm.text) || 1), frac >= 0.8 ? 130 : 110);
    doc.setFontSize(size);
    const w = doc.getTextWidth(wm.text), cx = pw / 2, cy = ph / 2;
    const x = cx - (w / 2) * Math.cos(rad) + (size * 0.35 / 2.835) * Math.sin(rad), y = cy + (w / 2) * Math.sin(rad) + (size * 0.35 / 2.835) * Math.cos(rad);
    for (let p = 1; p <= n; p++) {
      doc.setPage(p); doc.saveGraphicsState(); doc.setGState(new doc.GState({ opacity: 0.13 })); doc.setTextColor(120, 120, 120);
      doc.text(wm.text, x, y, { angle: ang }); doc.restoreGraphicsState();
    }
  } catch (e) { console.error('watermark failed', e); }
}
function wmHtml(wm) {
  if (!wm) return '';
  const base = '.wm-mark{position:fixed; left:0; top:0; width:100%; height:100%; display:flex; align-items:center; justify-content:center; pointer-events:none; z-index:0; overflow:hidden;}';
  if (wm.type === 'logo') {
    if (!wm.lh.logo) return '';
    return `<style>${base} .wm-mark img{width:${SIZE[wm.size]}%; max-height:80%; object-fit:contain; opacity:.1; -webkit-print-color-adjust:exact; print-color-adjust:exact;}</style><div class="wm-mark"><img src="${wm.lh.logo}" alt=""></div>`;
  }
  const fs = Math.round({ small: 0.4, medium: 0.6, large: 0.82 }[wm.size] * 100 * 0.5);
  return `<style>${base} .wm-mark span{transform:rotate(-45deg); font:800 ${fs}vmin/1 Arial,sans-serif; color:rgba(120,120,120,.14); white-space:nowrap; letter-spacing:.04em; -webkit-print-color-adjust:exact; print-color-adjust:exact;}</style><div class="wm-mark"><span>${escapeHtml(wm.text)}</span></div>`;
}

// ---- PDF -------------------------------------------------------------------------------------------------------------------------------
const asOpts = (o) => (Array.isArray(o) ? { columns: o } : (o || {}));
export async function exportRowsToPdf(rows, ttl, filenamePrefix, options) {
  try {
    const opts = asOpts(options);
    const sections = opts.sections && opts.sections.length ? opts.sections : null;
    if (!sections && (!rows || !rows.length)) { await customAlert('Nothing to export.'); return; }
    const JsPDF = await getJsPdf();
    const doc = new JsPDF({ orientation: opts.orientation || 'landscape', unit: 'mm', format: 'a4' });
    const pw = doc.internal.pageSize.getWidth(), ph = doc.internal.pageSize.getHeight(), M = 10;
    const lh = branchLetterhead(opts.branch || ''), acc = hexRgb(lh.accentColor), T = pdfText;
    // letterhead
    let y = 8, textX = M, logoH = 0;
    const logoData = await dataUrl(lh.logo);
    const logo = logoData ? { data: logoData, aspect: await imageSize(logoData) } : null;
    if (logo) {
      try { const { w, h } = fitBox(logo.aspect, 40, 17); doc.addImage(logoData, /^data:image\/jpe?g/i.test(logoData) ? 'JPEG' : 'PNG', M, y, w, h); textX = M + w + 6; logoH = h; } catch (e) { textX = M; }
    }
    let ty = y + 4.5;
    doc.setFont('helvetica', 'bold'); doc.setFontSize(14); doc.setTextColor(30, 30, 30); doc.text(T(lh.companyName), textX, ty); ty += 4.8;
    doc.setFont('helvetica', 'normal'); doc.setFontSize(8); doc.setTextColor(95, 95, 95);
    if (lh.address) doc.splitTextToSize(T(lh.address), pw - textX - M).slice(0, 2).forEach((l) => { doc.text(l, textX, ty); ty += 3.6; });
    if (contactLine(lh)) { doc.text(T(contactLine(lh)), textX, ty); ty += 3.6; }
    if (regLine(lh)) { doc.text(T(regLine(lh)), textX, ty); ty += 3.6; }
    y = Math.max(y + logoH, ty) + 1.5;
    doc.setDrawColor(acc[0], acc[1], acc[2]); doc.setLineWidth(0.7); doc.line(M, y, pw - M, y); y += 6;
    // title block
    doc.setFont('helvetica', 'bold'); doc.setFontSize(13); doc.setTextColor(acc[0], acc[1], acc[2]); doc.text(T(title(ttl)), M, y);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(8); doc.setTextColor(120, 120, 120); doc.text(T(generated()), pw - M, y, { align: 'right' });
    y += 4.5;
    if (opts.subtitle) { doc.setFontSize(8.5); doc.setTextColor(70, 70, 70); doc.splitTextToSize(T(opts.subtitle), pw - 2 * M).forEach((l) => { doc.text(l, M, y); y += 4; }); }
    y += 1.5;
    // summary cards
    const cards = (opts.cards || []).filter((c) => c && c[0] !== undefined).slice(0, 12);
    if (cards.length) {
      const perRow = Math.min(6, cards.length), gap = 3, cw = (pw - 2 * M - (perRow - 1) * gap) / perRow, ch = 13;
      cards.forEach((c, i) => {
        const r = Math.floor(i / perRow), k = i % perRow, x = M + k * (cw + gap), yy = y + r * (ch + gap);
        doc.setFillColor(253, 246, 238); doc.setDrawColor(acc[0], acc[1], acc[2]); doc.setLineWidth(0.25); doc.roundedRect(x, yy, cw, ch, 1.8, 1.8, 'FD');
        let fs = 11; doc.setFont('helvetica', 'bold'); doc.setTextColor(30, 30, 30); doc.setFontSize(fs);
        while (doc.getTextWidth(T(c[0])) > cw - 5 && fs > 6) { fs -= 0.5; doc.setFontSize(fs); }
        doc.text(T(c[0]), x + 2.5, yy + 6);
        doc.setFont('helvetica', 'normal'); doc.setFontSize(6.5); doc.setTextColor(110, 110, 110);
        doc.text(doc.splitTextToSize(T(String(c[1]).toUpperCase()), cw - 5).slice(0, 1), x + 2.5, yy + 10.6);
      });
      y += Math.ceil(cards.length / perRow) * (ch + gap) + 1;
    }
    // legend
    if (opts.legend && opts.legend.length) {
      doc.setFontSize(7.5); let lx = M;
      opts.legend.forEach(([lab, col]) => {
        const rgb = hexRgb(col); doc.setFillColor(rgb[0], rgb[1], rgb[2]); doc.roundedRect(lx, y - 2.6, 3.2, 3.2, 0.6, 0.6, 'F');
        doc.setTextColor(70, 70, 70); doc.text(T(lab), lx + 4.6, y); lx += 4.6 + doc.getTextWidth(T(lab)) + 6;
      });
      y += 9;
    }
    // tables
    const drawTable = (cols, tRows, startY) => {
      const statusIdx = cols.map((c, i) => (isStatusCol(c) ? i : -1)).filter((i) => i >= 0);
      doc.autoTable({
        startY, margin: { top: 15, left: M, right: M, bottom: 14 },
        head: [cols.map(T)], body: tRows.map((r) => cols.map((c) => T(r[c] !== undefined && r[c] !== null ? r[c] : ''))),
        theme: 'grid', styles: { fontSize: 7.6, cellPadding: 1.9, lineColor: [225, 225, 225], lineWidth: 0.15, textColor: [40, 40, 40], overflow: 'linebreak' },
        headStyles: { fillColor: acc, textColor: 255, fontStyle: 'bold', halign: 'left' }, alternateRowStyles: { fillColor: [250, 247, 243] },
        didParseCell: (d) => { if (d.section === 'body' && statusIdx.includes(d.column.index)) { const c = statusColor(d.cell.raw); if (c) { d.cell.styles.textColor = hexRgb(c); d.cell.styles.fontStyle = 'bold'; } } },
      });
      return (doc.lastAutoTable && doc.lastAutoTable.finalY) || startY;
    };
    if (sections) {
      sections.forEach((sec) => {
        if (y > ph - 45) { doc.addPage(); y = 18; }
        doc.setFillColor(acc[0], acc[1], acc[2]); doc.rect(M, y - 3.4, 1.4, 4.6, 'F');
        doc.setFont('helvetica', 'bold'); doc.setFontSize(10.5); doc.setTextColor(30, 30, 30); doc.text(T(sec.heading), M + 3.4, y);
        y += 4.2;
        if (sec.sub) { doc.setFont('helvetica', 'normal'); doc.setFontSize(8); doc.setTextColor(90, 90, 90); doc.splitTextToSize(T(sec.sub), pw - 2 * M).forEach((l) => { doc.text(l, M, y); y += 3.8; }); }
        if (sec.calendar) {
          const lw = 24, bw = Math.min(8.6, (pw - 2 * M - lw) / 31), bh = 9;
          sec.calendar.forEach((mo) => {
            if (y + bh + 2 > ph - 16) { doc.addPage(); y = 18; }
            doc.setFont('helvetica', 'bold'); doc.setFontSize(8); doc.setTextColor(60, 60, 60); doc.text(T(mo.label), M, y + bh / 2 + 1);
            mo.cells.forEach((c, i) => {
              const x = M + lw + i * bw;
              if (c.code) { const rgb = hexRgb(c.color); doc.setFillColor(rgb[0], rgb[1], rgb[2]); } else doc.setFillColor(235, 235, 235);
              doc.roundedRect(x + 0.2, y, bw - 0.4, bh, 0.8, 0.8, 'F');
              doc.setFont('helvetica', 'bold'); doc.setFontSize(6.5); doc.setTextColor(c.code ? 255 : 150);
              doc.text(String(c.n), x + bw / 2, y + 3.6, { align: 'center' });
              doc.setFontSize(6); doc.text(T(c.code || '-'), x + bw / 2, y + 7.2, { align: 'center' });
            });
            y += bh + 2.2;
          });
          y += 2;
          if (sec.rows.length) {
            if (y > ph - 40) { doc.addPage(); y = 18; }
            doc.setFont('helvetica', 'bold'); doc.setFontSize(8.5); doc.setTextColor(60, 60, 60); doc.text(T(sec.excTitle || 'Days to note'), M, y); y += 2;
            y = drawTable(sec.cols, sec.rows, y) + 8;
          } else { doc.setFont('helvetica', 'italic'); doc.setFontSize(8.5); doc.setTextColor(47, 158, 82); doc.text(T(sec.emptyNote || ''), M, y + 2); y += 9; }
          return;
        }
        y = drawTable(sec.cols, sec.rows.length ? sec.rows : [Object.fromEntries(sec.cols.map((c) => [c, '—']))], y + 1) + 8;
      });
    } else {
      drawTable(opts.columns || Object.keys(rows[0]), rows, y);
    }
    // running header (pages 2+) and footer
    const n = doc.internal.getNumberOfPages();
    for (let p = 1; p <= n; p++) {
      doc.setPage(p);
      if (p > 1) {
        doc.setFont('helvetica', 'bold'); doc.setFontSize(8.5); doc.setTextColor(60, 60, 60); doc.text(T(lh.companyName), M, 9);
        doc.setFont('helvetica', 'normal'); doc.setTextColor(120, 120, 120); doc.text(T(title(ttl)), pw - M, 9, { align: 'right' });
        doc.setDrawColor(acc[0], acc[1], acc[2]); doc.setLineWidth(0.4); doc.line(M, 11, pw - M, 11);
      }
      doc.setDrawColor(210, 210, 210); doc.setLineWidth(0.2); doc.line(M, ph - 10, pw - M, ph - 10);
      doc.setFont('helvetica', 'normal'); doc.setFontSize(7.5); doc.setTextColor(130, 130, 130);
      doc.text('Anupam 360  |  ' + T(lh.companyName), M, ph - 6);
      doc.text('Page ' + p + ' of ' + n, pw - M, ph - 6, { align: 'right' });
    }
    pdfWatermark(doc, watermark(opts.branch || ''), logo);
    doc.save(`${filenamePrefix}-${Date.now()}.pdf`);
  } catch (e) { console.error(e); await customAlert('PDF export failed: ' + e.message); }
}

// ---- Print -----------------------------------------------------------------------------------------------------------------------------
export function printRowsTable(rows, ttl, options) {
  try {
    const opts = asOpts(options);
    const sections = opts.sections && opts.sections.length ? opts.sections : null;
    if (!sections && (!rows || !rows.length)) { customAlert('Nothing to print.'); return; }
    const w = window.open('', '_blank');
    if (!w) { customAlert("Couldn't open the print window — your browser may have blocked the pop-up. Please allow pop-ups for this page and try again."); return; }
    const lh = branchLetterhead(opts.branch || ''), acc = lh.accentColor;
    const tableHtml = (cols, tRows) => `<table><thead><tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead><tbody>
      ${tRows.map((r) => `<tr>${cols.map((c) => {
        const v = r[c] !== undefined && r[c] !== null ? String(r[c]) : '';
        const col = isStatusCol(c) ? statusColor(v) : null;
        return `<td>${col ? `<span class="pill" style="background:${col};">${escapeHtml(v)}</span>` : escapeHtml(v)}</td>`;
      }).join('')}</tr>`).join('') || `<tr><td colspan="${cols.length}" style="text-align:center;color:#888;">Nothing to show.</td></tr>`}</tbody></table>`;
    const body = sections
      ? sections.map((sec) => {
        const cal = sec.calendar ? sec.calendar.map((mo) => `<div class="calrow"><div class="calm">${escapeHtml(mo.label)}</div>${mo.cells.map((c) => `<div class="cal" style="background:${c.code ? c.color : '#ececec'};color:${c.code ? '#fff' : '#999'};"><b>${c.n}</b><span>${c.code || '-'}</span></div>`).join('')}</div>`).join('') : '';
        const tbl = sec.calendar
          ? (sec.rows.length ? `<div class="exct">${escapeHtml(sec.excTitle || 'Days to note')}</div>${tableHtml(sec.cols, sec.rows)}` : `<div class="okline">${escapeHtml(sec.emptyNote || '')}</div>`)
          : tableHtml(sec.cols, sec.rows);
        return `<div class="sec"><h2>${escapeHtml(sec.heading)}</h2>${sec.sub ? `<div class="secsub">${escapeHtml(sec.sub)}</div>` : ''}${cal ? `<div class="calwrap">${cal}</div>` : ''}${tbl}</div>`;
      }).join('')
      : tableHtml(opts.columns || Object.keys(rows[0]), rows);
    const cards = (opts.cards || []).filter((c) => c && c[0] !== undefined);
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(title(ttl))}</title>
      <style>
        @page{ size:A4 landscape; margin:8mm 8mm 12mm; }
        *{ -webkit-print-color-adjust:exact; print-color-adjust:exact; box-sizing:border-box; }
        body{font-family:Arial,Helvetica,sans-serif; margin:0; color:#1f2a37; font-size:12px;}
        .lh{display:flex; align-items:center; gap:14px; padding-bottom:8px; border-bottom:3px solid ${acc};}
        .lh img{max-height:58px; max-width:150px; object-fit:contain;}
        .lh .cn{font-size:20px; font-weight:800; color:#1b1b1b;} .lh .cl{font-size:11px; color:#555; line-height:1.45; margin-top:2px;}
        .tb{display:flex; justify-content:space-between; align-items:flex-end; margin:14px 0 4px;}
        .tb h1{font-size:20px; margin:0; color:${acc};} .tb .gen{font-size:10.5px; color:#777; text-align:right;}
        .sub{font-size:11.5px; color:#444; margin:0 0 10px;}
        .cards{display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 12px;}
        .card{flex:1 1 140px; max-width:220px; border:1px solid ${acc}; background:#fdf6ee; border-radius:8px; padding:7px 10px;}
        .card .n{font-size:17px; font-weight:800; color:#1b1b1b;} .card .l{font-size:9.5px; letter-spacing:.05em; text-transform:uppercase; color:#777; margin-top:2px;}
        .legend{display:flex; flex-wrap:wrap; gap:14px; font-size:11px; color:#444; margin:2px 0 12px;} .legend i{display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:5px; vertical-align:-1px;}
        .sec{margin-top:16px; break-inside:auto;} .sec h2,.secsub,.exct{break-after:avoid;} .sec h2{font-size:14px; margin:0 0 3px; padding-left:8px; border-left:4px solid ${acc};} .secsub{font-size:11px; color:#555; margin:0 0 6px 12px;}
        table{width:100%; border-collapse:collapse; margin-top:4px;}
        thead{display:table-header-group;} tr{break-inside:avoid;}
        th{background:${acc}; color:#fff; text-align:left; padding:6px 8px; font-size:11px; border:1px solid ${acc};}
        td{border:1px solid #e1e1e1; padding:5px 8px; font-size:11px; vertical-align:top;}
        tbody tr:nth-child(even) td{background:#faf7f3;}
        .calwrap{margin:4px 0 10px 12px;} .calrow{display:flex; align-items:center; gap:2px; margin-bottom:3px; break-inside:avoid;} .calm{width:96px; font-size:10.5px; font-weight:700; color:#444; flex-shrink:0;}
        .cal{width:26px; height:30px; border-radius:4px; text-align:center; display:flex; flex-direction:column; justify-content:center; line-height:1.15;} .cal b{font-size:10px;} .cal span{font-size:9px; font-weight:700;}
        .exct{font-size:11px; font-weight:700; color:#444; margin:6px 0 2px 12px;} .okline{font-size:11px; color:#2f9e52; font-style:italic; margin:4px 0 4px 12px;}
        .pill{display:inline-block; color:#fff; font-weight:700; font-size:10.5px; padding:1px 8px; border-radius:10px; white-space:nowrap;}
        .foot{position:fixed; left:0; right:0; bottom:0; font-size:9.5px; color:#888; display:flex; justify-content:space-between; border-top:1px solid #ddd; padding-top:3px; background:#fff;}
      </style></head><body>
      <div class="lh">${lh.logo ? `<img src="${lh.logo}" alt="">` : ''}<div><div class="cn">${escapeHtml(lh.companyName)}</div>
        <div class="cl">${lh.address ? escapeHtml(lh.address) + '<br>' : ''}${escapeHtml(contactLine(lh))}${regLine(lh) ? '<br>' + escapeHtml(regLine(lh)) : ''}</div></div></div>
      <div class="tb"><h1>${escapeHtml(title(ttl))}</h1><div class="gen">${escapeHtml(generated())}</div></div>
      ${opts.subtitle ? `<p class="sub">${escapeHtml(opts.subtitle)}</p>` : ''}
      ${cards.length ? `<div class="cards">${cards.map((c) => `<div class="card"><div class="n">${escapeHtml(String(c[0]))}</div><div class="l">${escapeHtml(String(c[1]))}</div></div>`).join('')}</div>` : ''}
      ${opts.legend && opts.legend.length ? `<div class="legend">${opts.legend.map(([l, c]) => `<span><i style="background:${c};"></i>${escapeHtml(l)}</span>`).join('')}</div>` : ''}
      ${body}
      <div class="foot"><span>Anupam 360 &nbsp;|&nbsp; ${escapeHtml(lh.companyName)}</span><span>${escapeHtml(generated())}</span></div>
      ${wmHtml(watermark(opts.branch || ''))}
      </body></html>`;
    w.document.open(); w.document.write(html); w.document.close();
    w.onload = () => { w.focus(); w.print(); };
    setTimeout(() => { try { w.focus(); w.print(); } catch (e) { /* closed */ } }, 600);
  } catch (e) { console.error(e); customAlert('Print failed: ' + e.message); }
}

// ---- Excel with several sheets (User Performance) -------------------------------------------------------------------
export async function exportSheetsToExcel(sheets, prefix) {
  const list = sheets.filter((sh) => sh.rows && sh.rows.length);
  if (!list.length) { await customAlert('Nothing to export.'); return; }
  const XLSX = await getXlsx();
  const wb = XLSX.utils.book_new();
  list.forEach((sh) => {
    const ws = XLSX.utils.json_to_sheet(sh.rows);
    const keys = Object.keys(sh.rows[0]);
    ws['!cols'] = keys.map((k) => ({ wch: Math.min(48, Math.max(k.length + 2, ...sh.rows.slice(0, 200).map((r) => String(r[k] == null ? '' : r[k]).length + 2))) }));
    XLSX.utils.book_append_sheet(wb, ws, sh.name.slice(0, 31));
  });
  XLSX.writeFile(wb, `${prefix}-${Date.now()}.xlsx`);
}
