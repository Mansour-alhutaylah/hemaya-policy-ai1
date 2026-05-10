import jsPDF from "jspdf";

// Match apiClient.js: in prod VITE_API_URL points at the Render backend,
// in dev it falls back to "/api" (Vite proxy handles it).
const API_BASE = import.meta.env.VITE_API_URL || "/api";

const BRAND = {
  emerald: [16, 185, 129],
  emeraldLight: [52, 211, 153],
  teal: [13, 148, 136],
  slate950: [2, 6, 23],
  slate900: [15, 23, 42],
  slate700: [51, 65, 85],
  slate500: [100, 116, 139],
  slate300: [203, 213, 225],
  slate100: [241, 245, 249],
  slate50: [248, 250, 252],
  amber: [245, 158, 11],
  red: [239, 68, 68],
  blue: [59, 130, 246],
  white: [255, 255, 255],
};

const MARGIN = 16;
const PAGE_W = 210;
const PAGE_H = 297;

// Official Himaya mark: lucide ShieldCheck inside the same emerald→teal gradient
// rounded square used across the app (Sidebar.jsx, Home.jsx).
const LOGO_SVG = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="himayaGradient" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="rgb(52,211,153)"/>
      <stop offset="100%" stop-color="rgb(13,148,136)"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="256" height="256" rx="56" ry="56" fill="url(#himayaGradient)"/>
  <g transform="translate(64 64) scale(5.333)" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>
    <path d="m9 12 2 2 4-4"/>
  </g>
</svg>`;

let _logoDataUrlPromise = null;
function loadLogoDataUrl() {
  if (_logoDataUrlPromise) return _logoDataUrlPromise;
  _logoDataUrlPromise = new Promise((resolve, reject) => {
    const svgUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(LOGO_SVG)}`;
    const img = new Image();
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = 256;
        canvas.height = 256;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, 256, 256);
        resolve(canvas.toDataURL("image/png"));
      } catch (e) {
        reject(e);
      }
    };
    img.onerror = reject;
    img.src = svgUrl;
  });
  return _logoDataUrlPromise;
}

function safeDate(iso, fallback = "—") {
  if (!iso) return fallback;
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-GB", {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return fallback;
  }
}

function severityColor(sev) {
  switch (sev) {
    case "Critical": return BRAND.red;
    case "High": return BRAND.amber;
    case "Medium": return BRAND.blue;
    case "Low": return BRAND.emerald;
    default: return BRAND.slate500;
  }
}

function averageScore(results) {
  if (!results?.length) return 0;
  const sum = results.reduce((a, r) => a + (Number(r.compliance_score) || 0), 0);
  return Math.round((sum / results.length) * 10) / 10;
}

function newDoc() {
  const doc = new jsPDF({ unit: "mm", format: "a4", compress: true });
  doc.setFont("helvetica", "normal");
  return doc;
}

function drawHeader(doc, headerSubtitle, logoDataUrl, headerTitle = "Compliance Report") {
  doc.setFillColor(...BRAND.slate900);
  doc.rect(0, 0, PAGE_W, 28, "F");

  doc.setFillColor(...BRAND.emerald);
  doc.rect(0, 28, PAGE_W, 2, "F");

  if (logoDataUrl) {
    doc.addImage(logoDataUrl, "PNG", MARGIN, 8, 12, 12);
  }

  doc.setTextColor(...BRAND.white);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.text("Himaya", MARGIN + 16, 13.5);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...BRAND.slate300);
  doc.text("AI COMPLIANCE", MARGIN + 16, 18);

  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(...BRAND.white);
  doc.text(headerTitle, PAGE_W - MARGIN, 13.5, { align: "right" });
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...BRAND.slate300);
  const subtitle = headerSubtitle || "";
  const truncated = subtitle.length > 48 ? subtitle.slice(0, 45) + "…" : subtitle;
  doc.text(truncated, PAGE_W - MARGIN, 18, { align: "right" });
}

function drawFooter(doc, pageNum, totalPages, generatedAt) {
  doc.setDrawColor(...BRAND.slate300);
  doc.setLineWidth(0.2);
  doc.line(MARGIN, PAGE_H - 12, PAGE_W - MARGIN, PAGE_H - 12);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...BRAND.slate500);
  doc.text(`Generated ${safeDate(generatedAt)}`, MARGIN, PAGE_H - 6);
  doc.text(`Page ${pageNum} of ${totalPages}`, PAGE_W - MARGIN, PAGE_H - 6, { align: "right" });
  doc.text("Himaya · AI Compliance Platform", PAGE_W / 2, PAGE_H - 6, { align: "center" });
}

function ensureRoom(ctx, needed) {
  if (ctx.y + needed > PAGE_H - 18) {
    ctx.doc.addPage();
    drawHeader(ctx.doc, ctx.headerSubtitle ?? ctx.policyName, ctx.logoDataUrl, ctx.headerTitle);
    ctx.y = 38;
  }
}

function drawSectionTitle(ctx, title) {
  ensureRoom(ctx, 14);
  const { doc } = ctx;
  doc.setFillColor(...BRAND.emerald);
  doc.rect(MARGIN, ctx.y, 3, 6, "F");
  doc.setTextColor(...BRAND.slate900);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(13);
  doc.text(title, MARGIN + 6, ctx.y + 5);
  ctx.y += 10;
}

function drawKeyValueGrid(ctx, pairs) {
  const colW = (PAGE_W - 2 * MARGIN) / 2;
  ctx.y += 2;
  for (let i = 0; i < pairs.length; i += 2) {
    ensureRoom(ctx, 14);
    for (let j = 0; j < 2; j += 1) {
      const pair = pairs[i + j];
      if (!pair) continue;
      const x = MARGIN + j * colW;
      ctx.doc.setFont("helvetica", "normal");
      ctx.doc.setFontSize(8);
      ctx.doc.setTextColor(...BRAND.slate500);
      ctx.doc.text(pair.label.toUpperCase(), x, ctx.y);
      ctx.doc.setFont("helvetica", "bold");
      ctx.doc.setFontSize(10);
      ctx.doc.setTextColor(...BRAND.slate900);
      const valueLines = ctx.doc.splitTextToSize(String(pair.value ?? "—"), colW - 4);
      ctx.doc.text(valueLines.slice(0, 2), x, ctx.y + 5);
    }
    ctx.y += 12;
  }
}

function drawSummaryCards(ctx, avgScore, resultsCount, gapsCount, mappingsCount) {
  ensureRoom(ctx, 28);
  const cards = [
    { label: "Overall score", value: `${avgScore}%`, accent: BRAND.emerald },
    { label: "Frameworks", value: String(resultsCount), accent: BRAND.blue },
    { label: "Open gaps", value: String(gapsCount), accent: gapsCount > 0 ? BRAND.amber : BRAND.emerald },
    { label: "Mapped controls", value: String(mappingsCount), accent: BRAND.slate700 },
  ];
  const total = PAGE_W - 2 * MARGIN;
  const gap = 3;
  const cardW = (total - gap * (cards.length - 1)) / cards.length;
  cards.forEach((c, i) => {
    const x = MARGIN + i * (cardW + gap);
    ctx.doc.setFillColor(...BRAND.slate50);
    ctx.doc.setDrawColor(...BRAND.slate300);
    ctx.doc.setLineWidth(0.2);
    ctx.doc.roundedRect(x, ctx.y, cardW, 22, 2, 2, "FD");
    ctx.doc.setFillColor(...c.accent);
    ctx.doc.roundedRect(x, ctx.y, 2, 22, 1, 1, "F");
    ctx.doc.setFont("helvetica", "normal");
    ctx.doc.setFontSize(8);
    ctx.doc.setTextColor(...BRAND.slate500);
    ctx.doc.text(c.label.toUpperCase(), x + 5, ctx.y + 7);
    ctx.doc.setFont("helvetica", "bold");
    ctx.doc.setFontSize(15);
    ctx.doc.setTextColor(...BRAND.slate900);
    ctx.doc.text(c.value, x + 5, ctx.y + 16);
  });
  ctx.y += 28;
}

function drawFrameworkTable(ctx, rows) {
  if (!rows.length) {
    drawEmpty(ctx, "No compliance analyses recorded for this policy yet.");
    return;
  }
  const columns = [
    { key: "framework", label: "Framework", w: 45 },
    { key: "score", label: "Score", w: 20, align: "right" },
    { key: "covered", label: "Covered", w: 25, align: "right" },
    { key: "partial", label: "Partial", w: 25, align: "right" },
    { key: "missing", label: "Missing", w: 25, align: "right" },
    { key: "analyzed_at", label: "Analyzed", w: 38, align: "right" },
  ];
  drawTable(ctx, columns, rows.map(r => ({
    framework: r.framework,
    score: `${Math.round(r.compliance_score || 0)}%`,
    covered: r.controls_covered ?? 0,
    partial: r.controls_partial ?? 0,
    missing: r.controls_missing ?? 0,
    analyzed_at: safeDate(r.analyzed_at),
  })));
}

function drawGapsList(ctx, gaps) {
  if (!gaps.length) {
    drawEmpty(ctx, "No open gaps recorded for this policy.");
    return;
  }
  gaps.forEach((g) => {
    const descLines = ctx.doc.splitTextToSize(g.description || "No description provided.", PAGE_W - 2 * MARGIN - 6);
    const remLines = g.remediation
      ? ctx.doc.splitTextToSize(`Remediation: ${g.remediation}`, PAGE_W - 2 * MARGIN - 6)
      : [];
    const blockH = 14 + descLines.length * 4 + (remLines.length ? 2 + remLines.length * 4 : 0);
    ensureRoom(ctx, blockH + 4);

    ctx.doc.setFillColor(...BRAND.slate50);
    ctx.doc.setDrawColor(...BRAND.slate300);
    ctx.doc.setLineWidth(0.2);
    ctx.doc.roundedRect(MARGIN, ctx.y, PAGE_W - 2 * MARGIN, blockH, 2, 2, "FD");

    ctx.doc.setFillColor(...severityColor(g.severity));
    ctx.doc.roundedRect(MARGIN, ctx.y, 2, blockH, 1, 1, "F");

    ctx.doc.setFont("helvetica", "bold");
    ctx.doc.setFontSize(9);
    ctx.doc.setTextColor(...BRAND.slate900);
    const title = `${g.control_id || "—"} · ${g.control_name || "Unnamed control"}`;
    const titleTrimmed = ctx.doc.splitTextToSize(title, PAGE_W - 2 * MARGIN - 40)[0];
    ctx.doc.text(titleTrimmed, MARGIN + 5, ctx.y + 6);

    ctx.doc.setFont("helvetica", "bold");
    ctx.doc.setFontSize(7.5);
    const pillLabel = `${(g.severity || "Info").toUpperCase()} · ${g.framework || ""}`;
    const pillW = ctx.doc.getTextWidth(pillLabel) + 4;
    ctx.doc.setFillColor(...severityColor(g.severity));
    ctx.doc.roundedRect(PAGE_W - MARGIN - pillW - 2, ctx.y + 2, pillW, 5, 1, 1, "F");
    ctx.doc.setTextColor(...BRAND.white);
    ctx.doc.text(pillLabel, PAGE_W - MARGIN - pillW / 2 - 2, ctx.y + 5.5, { align: "center" });

    ctx.doc.setFont("helvetica", "normal");
    ctx.doc.setFontSize(9);
    ctx.doc.setTextColor(...BRAND.slate700);
    ctx.doc.text(descLines, MARGIN + 5, ctx.y + 11);
    let yCursor = ctx.y + 11 + descLines.length * 4;
    if (remLines.length) {
      yCursor += 2;
      ctx.doc.setTextColor(...BRAND.slate500);
      ctx.doc.setFont("helvetica", "italic");
      ctx.doc.text(remLines, MARGIN + 5, yCursor);
    }

    ctx.y += blockH + 3;
  });
}

function drawMappingsTable(ctx, mappings) {
  if (!mappings.length) {
    drawEmpty(ctx, "No mapped controls recorded for this policy.");
    return;
  }
  const top = mappings.slice(0, 25);
  const columns = [
    { key: "control_id", label: "Control", w: 25 },
    { key: "framework", label: "Framework", w: 30 },
    { key: "confidence", label: "Conf.", w: 18, align: "right" },
    { key: "decision", label: "Decision", w: 25 },
    { key: "evidence", label: "Evidence", w: 80 },
  ];
  drawTable(ctx, columns, top.map(m => ({
    control_id: m.control_id || "—",
    framework: m.framework,
    confidence: `${Math.round((m.confidence_score || 0) * 100)}%`,
    decision: m.decision || "Pending",
    evidence: (m.evidence_snippet || "—").replace(/\s+/g, " ").slice(0, 180),
  })));

  if (mappings.length > top.length) {
    ensureRoom(ctx, 6);
    ctx.doc.setFont("helvetica", "italic");
    ctx.doc.setFontSize(8);
    ctx.doc.setTextColor(...BRAND.slate500);
    ctx.doc.text(`+${mappings.length - top.length} more mappings not shown.`, MARGIN, ctx.y + 4);
    ctx.y += 6;
  }
}

function drawInsightsList(ctx, insights) {
  if (!insights.length) {
    drawEmpty(ctx, "No AI insights available for this policy.");
    return;
  }
  insights.slice(0, 12).forEach((i) => {
    const descLines = ctx.doc.splitTextToSize(i.description || "—", PAGE_W - 2 * MARGIN - 6);
    const blockH = 11 + descLines.length * 4;
    ensureRoom(ctx, blockH + 3);

    ctx.doc.setFillColor(...BRAND.slate50);
    ctx.doc.setDrawColor(...BRAND.slate300);
    ctx.doc.setLineWidth(0.2);
    ctx.doc.roundedRect(MARGIN, ctx.y, PAGE_W - 2 * MARGIN, blockH, 2, 2, "FD");

    ctx.doc.setFillColor(...BRAND.emerald);
    ctx.doc.roundedRect(MARGIN, ctx.y, 2, blockH, 1, 1, "F");

    ctx.doc.setFont("helvetica", "bold");
    ctx.doc.setFontSize(9);
    ctx.doc.setTextColor(...BRAND.slate900);
    ctx.doc.text(i.title || "Insight", MARGIN + 5, ctx.y + 6);
    ctx.doc.setFont("helvetica", "normal");
    ctx.doc.setFontSize(9);
    ctx.doc.setTextColor(...BRAND.slate700);
    ctx.doc.text(descLines, MARGIN + 5, ctx.y + 11);

    ctx.y += blockH + 2;
  });
}

function drawTable(ctx, columns, rows) {
  const totalW = columns.reduce((a, c) => a + c.w, 0);
  const scale = (PAGE_W - 2 * MARGIN) / totalW;
  const cols = columns.map(c => ({ ...c, w: c.w * scale }));

  ensureRoom(ctx, 14);
  ctx.doc.setFillColor(...BRAND.slate900);
  ctx.doc.rect(MARGIN, ctx.y, PAGE_W - 2 * MARGIN, 7, "F");
  ctx.doc.setTextColor(...BRAND.white);
  ctx.doc.setFont("helvetica", "bold");
  ctx.doc.setFontSize(8.5);
  let x = MARGIN + 2;
  cols.forEach(c => {
    const align = c.align || "left";
    const tx = align === "right" ? x + c.w - 4 : x + 1;
    ctx.doc.text(c.label, tx, ctx.y + 5, { align });
    x += c.w;
  });
  ctx.y += 7;

  rows.forEach((row, idx) => {
    const cellLines = cols.map(c => ctx.doc.splitTextToSize(String(row[c.key] ?? "—"), c.w - 4));
    const rowH = Math.max(6, ...cellLines.map(l => l.length * 3.6 + 2.2));
    ensureRoom(ctx, rowH);
    if (idx % 2 === 0) {
      ctx.doc.setFillColor(...BRAND.slate50);
      ctx.doc.rect(MARGIN, ctx.y, PAGE_W - 2 * MARGIN, rowH, "F");
    }
    ctx.doc.setDrawColor(...BRAND.slate300);
    ctx.doc.setLineWidth(0.1);
    ctx.doc.line(MARGIN, ctx.y + rowH, PAGE_W - MARGIN, ctx.y + rowH);

    ctx.doc.setFont("helvetica", "normal");
    ctx.doc.setFontSize(8.5);
    ctx.doc.setTextColor(...BRAND.slate700);
    let cx = MARGIN + 2;
    cols.forEach((c, i) => {
      const align = c.align || "left";
      const tx = align === "right" ? cx + c.w - 4 : cx + 1;
      ctx.doc.text(cellLines[i], tx, ctx.y + 4, { align });
      cx += c.w;
    });
    ctx.y += rowH;
  });

  ctx.y += 2;
}

function drawEmpty(ctx, msg) {
  ensureRoom(ctx, 14);
  ctx.doc.setFillColor(...BRAND.slate50);
  ctx.doc.setDrawColor(...BRAND.slate300);
  ctx.doc.setLineWidth(0.2);
  ctx.doc.roundedRect(MARGIN, ctx.y, PAGE_W - 2 * MARGIN, 10, 2, 2, "FD");
  ctx.doc.setFont("helvetica", "italic");
  ctx.doc.setFontSize(9);
  ctx.doc.setTextColor(...BRAND.slate500);
  ctx.doc.text(msg, MARGIN + 4, ctx.y + 6.5);
  ctx.y += 14;
}

function safeFilenameBase(name) {
  return (name || "policy").replace(/[^\w.-]+/g, "_").slice(0, 60);
}

async function buildPdfDoc(data) {
  const { policy, compliance_results = [], gaps = [], mappings = [], insights = [], generated_at } = data;
  const logoDataUrl = await loadLogoDataUrl().catch(() => null);
  const doc = newDoc();
  const ctx = { doc, y: 38, policyName: policy?.file_name || "Policy", logoDataUrl };
  drawHeader(doc, ctx.policyName, logoDataUrl);

  drawSectionTitle(ctx, "Policy overview");
  drawKeyValueGrid(ctx, [
    { label: "Policy", value: policy?.file_name || "—" },
    { label: "Version", value: policy?.version || "1.0" },
    { label: "Status", value: policy?.status || "—" },
    { label: "File type", value: policy?.file_type || "—" },
    { label: "Uploaded", value: safeDate(policy?.uploaded_at) },
    { label: "Last analyzed", value: safeDate(policy?.last_analyzed_at) },
    { label: "Description", value: policy?.description || "—" },
  ]);

  drawSectionTitle(ctx, "Executive summary");
  drawSummaryCards(ctx, averageScore(compliance_results), compliance_results.length, gaps.length, mappings.length);

  drawSectionTitle(ctx, "Compliance by framework");
  drawFrameworkTable(ctx, compliance_results);

  drawSectionTitle(ctx, `Findings & open gaps (${gaps.length})`);
  drawGapsList(ctx, gaps);

  drawSectionTitle(ctx, "Mapped evidence");
  drawMappingsTable(ctx, mappings);

  drawSectionTitle(ctx, "AI insights");
  drawInsightsList(ctx, insights);

  const total = doc.getNumberOfPages();
  for (let i = 1; i <= total; i += 1) {
    doc.setPage(i);
    drawFooter(doc, i, total, generated_at);
  }
  return doc;
}

function escapeCsvCell(v) {
  if (v === null || v === undefined) return "";
  const s = String(v);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function csvRow(fields) {
  return fields.map(escapeCsvCell).join(",");
}

function buildCsvBlob(data) {
  const { policy, compliance_results = [], gaps = [], mappings = [], insights = [], generated_at } = data;
  const lines = [];

  lines.push("Himaya Compliance Report");
  lines.push(`Generated,${escapeCsvCell(safeDate(generated_at))}`);
  lines.push("");

  lines.push("# Policy");
  lines.push(csvRow(["Field", "Value"]));
  lines.push(csvRow(["File name", policy?.file_name]));
  lines.push(csvRow(["Version", policy?.version]));
  lines.push(csvRow(["Status", policy?.status]));
  lines.push(csvRow(["File type", policy?.file_type]));
  lines.push(csvRow(["Uploaded", safeDate(policy?.uploaded_at)]));
  lines.push(csvRow(["Last analyzed", safeDate(policy?.last_analyzed_at)]));
  lines.push(csvRow(["Description", policy?.description]));
  lines.push("");

  lines.push("# Compliance by framework");
  lines.push(csvRow(["Framework", "Score", "Covered", "Partial", "Missing", "Status", "Analyzed at"]));
  compliance_results.forEach(r => {
    lines.push(csvRow([
      r.framework,
      `${Math.round(r.compliance_score || 0)}%`,
      r.controls_covered,
      r.controls_partial,
      r.controls_missing,
      r.status,
      safeDate(r.analyzed_at),
    ]));
  });
  lines.push("");

  lines.push("# Findings and gaps");
  lines.push(csvRow(["Control", "Framework", "Name", "Severity", "Status", "Description", "Remediation", "Created"]));
  gaps.forEach(g => {
    lines.push(csvRow([
      g.control_id,
      g.framework,
      g.control_name,
      g.severity,
      g.status,
      g.description,
      g.remediation,
      safeDate(g.created_at),
    ]));
  });
  lines.push("");

  lines.push("# Mapped controls");
  lines.push(csvRow(["Control", "Framework", "Confidence", "Decision", "Evidence", "Reviewed at"]));
  mappings.forEach(m => {
    lines.push(csvRow([
      m.control_id,
      m.framework,
      `${Math.round((m.confidence_score || 0) * 100)}%`,
      m.decision,
      m.evidence_snippet,
      safeDate(m.reviewed_at),
    ]));
  });
  lines.push("");

  lines.push("# AI insights");
  lines.push(csvRow(["Type", "Title", "Priority", "Confidence", "Status", "Description", "Created"]));
  insights.forEach(i => {
    lines.push(csvRow([
      i.insight_type,
      i.title,
      i.priority,
      `${Math.round((i.confidence || 0) * 100)}%`,
      i.status,
      i.description,
      safeDate(i.created_at),
    ]));
  });

  const csv = "﻿" + lines.join("\n");
  return new Blob([csv], { type: "text/csv;charset=utf-8;" });
}

// Re-export the shared branding primitives so other report builders
// (e.g. auditReport.js) can render documents in the same Himaya style
// without duplicating the logo/header/footer/table layout code.
export {
  BRAND,
  MARGIN,
  PAGE_W,
  PAGE_H,
  loadLogoDataUrl,
  safeDate,
  safeFilenameBase,
  newDoc,
  drawHeader,
  drawFooter,
  ensureRoom,
  drawSectionTitle,
  drawKeyValueGrid,
  drawTable,
  drawEmpty,
};

export async function buildPolicyReport(data, format) {
  const base = safeFilenameBase(data?.policy?.file_name);
  if (format === "csv") {
    return {
      blob: buildCsvBlob(data),
      filename: `himaya_report_${base}.csv`,
      mime: "text/csv",
    };
  }
  const doc = await buildPdfDoc(data);
  return {
    blob: doc.output("blob"),
    filename: `himaya_report_${base}.pdf`,
    mime: "application/pdf",
  };
}

export function triggerBrowserDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function downloadFromUrl(url, filename) {
  if (!url) return;
  const a = document.createElement("a");
  a.href = url;
  if (filename) a.download = filename;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export async function fetchPolicyReportData(policyId) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE}/functions/policy_report_data/${policyId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to load report data" }));
    throw new Error(err.detail || "Failed to load report data");
  }
  return res.json();
}

export async function persistReport({ blob, filename, mime, policyId, format }) {
  const token = localStorage.getItem("token");
  const form = new FormData();
  form.append("file", new File([blob], filename, { type: mime }));
  form.append("policy_id", policyId);
  form.append("format", format);
  const res = await fetch(`${API_BASE}/functions/save_report`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to save report" }));
    throw new Error(err.detail || "Failed to save report");
  }
  return res.json();
}

// Back-compat wrappers still used by earlier Policies.jsx changes.
export async function generatePolicyReportPdf(data) {
  const { blob, filename } = await buildPolicyReport(data, "pdf");
  triggerBrowserDownload(blob, filename);
}

export function generatePolicyReportCsv(data) {
  const blob = buildCsvBlob(data);
  const base = safeFilenameBase(data?.policy?.file_name);
  triggerBrowserDownload(blob, `himaya_report_${base}.csv`);
}
