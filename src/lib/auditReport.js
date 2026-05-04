// Branded Audit Trail PDF — reuses the same Himaya branding primitives
// as the Generate Report output (header bar, footer, table styling, logo).
import {
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
  triggerBrowserDownload,
} from "@/lib/policyReport";

const ACTION_LABELS = {
  policy_upload: "Policy Upload",
  policy_delete: "Policy Delete",
  analysis_start: "Analysis Started",
  analysis_complete: "Analysis Complete",
  mapping_review: "Mapping Review",
  report_generate: "Report Generated",
  report_delete: "Report Deleted",
  gap_update: "Gap Update",
  settings_change: "Settings Change",
  user_login: "User Login",
  user_logout: "User Logout",
};

function readableAction(action) {
  if (!action) return "—";
  return (
    ACTION_LABELS[action] ||
    action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

function detailsToText(details) {
  if (details == null) return "—";
  if (typeof details === "string") {
    // Try to parse JSON-stringified details for nicer formatting.
    const trimmed = details.trim();
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed && typeof parsed === "object") {
          return Object.entries(parsed)
            .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
            .join(" · ");
        }
      } catch {
        // fall through and return the raw string
      }
    }
    return details;
  }
  if (typeof details === "object") {
    try {
      return Object.entries(details)
        .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
        .join(" · ");
    } catch {
      return JSON.stringify(details);
    }
  }
  return String(details);
}

function formatTimestamp(ts) {
  return safeDate(ts);
}

// Severity-style accent badge per action group, drawn into a cell pill.
function actionAccent(action) {
  if (!action) return BRAND.slate500;
  if (action.includes("delete")) return BRAND.red;
  if (action.includes("complete")) return BRAND.emerald;
  if (action.includes("start") || action.includes("update")) return BRAND.amber;
  if (action.includes("upload") || action.includes("login")) return BRAND.blue;
  if (action.includes("logout")) return BRAND.slate500;
  if (action.includes("report")) return BRAND.amber;
  return BRAND.slate500;
}

function drawAuditOverview(ctx, summary) {
  ensureRoom(ctx, 28);
  const cards = [
    { label: "Records", value: String(summary.total) },
    { label: "Distinct actions", value: String(summary.distinctActions) },
    { label: "Distinct actors", value: String(summary.distinctActors) },
    { label: "Date range", value: summary.range },
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
    ctx.doc.setFillColor(...BRAND.emerald);
    ctx.doc.roundedRect(x, ctx.y, 2, 22, 1, 1, "F");
    ctx.doc.setFont("helvetica", "normal");
    ctx.doc.setFontSize(8);
    ctx.doc.setTextColor(...BRAND.slate500);
    ctx.doc.text(c.label.toUpperCase(), x + 5, ctx.y + 7);
    ctx.doc.setFont("helvetica", "bold");
    ctx.doc.setFontSize(c.value.length > 20 ? 9 : 12);
    ctx.doc.setTextColor(...BRAND.slate900);
    const valueLines = ctx.doc.splitTextToSize(c.value, cardW - 8);
    ctx.doc.text(valueLines.slice(0, 2), x + 5, ctx.y + 16);
  });
  ctx.y += 28;
}

function drawAuditTable(ctx, logs) {
  if (!logs.length) {
    drawEmpty(ctx, "No audit log entries match the current filters.");
    return;
  }

  const columns = [
    { key: "timestamp", label: "Timestamp", w: 38 },
    { key: "action",    label: "Action",    w: 30 },
    { key: "actor",     label: "Actor",     w: 42 },
    { key: "target",    label: "Target",    w: 40 },
    { key: "details",   label: "Details",   w: 60 },
  ];

  const rows = logs.map((log) => ({
    timestamp: formatTimestamp(log.timestamp),
    action: readableAction(log.action),
    actor: log.actor || "system",
    target: log.target_type
      ? `${log.target_type}${log.target_id ? `: ${log.target_id}` : ""}`
      : log.target_id || "—",
    details: detailsToText(log.details),
    _accent: actionAccent(log.action),
  }));

  drawTable(ctx, columns, rows);
}

function drawAuditCards(ctx, logs) {
  if (!logs.length) {
    drawEmpty(ctx, "No audit log entries match the current filters.");
    return;
  }

  logs.forEach((log) => {
    const detailsText = detailsToText(log.details);
    const detailsLines = ctx.doc.splitTextToSize(detailsText, PAGE_W - 2 * MARGIN - 14);
    const targetText = log.target_type
      ? `${log.target_type}${log.target_id ? `: ${log.target_id}` : ""}`
      : log.target_id || "";
    const targetLines = targetText
      ? ctx.doc.splitTextToSize(`Target: ${targetText}`, PAGE_W - 2 * MARGIN - 14)
      : [];
    const blockH = 14 + detailsLines.length * 4 + (targetLines.length ? 4 + targetLines.length * 4 : 0);
    ensureRoom(ctx, blockH + 3);

    ctx.doc.setFillColor(...BRAND.slate50);
    ctx.doc.setDrawColor(...BRAND.slate300);
    ctx.doc.setLineWidth(0.2);
    ctx.doc.roundedRect(MARGIN, ctx.y, PAGE_W - 2 * MARGIN, blockH, 2, 2, "FD");

    ctx.doc.setFillColor(...actionAccent(log.action));
    ctx.doc.roundedRect(MARGIN, ctx.y, 2, blockH, 1, 1, "F");

    // Top line: action title + timestamp on the right
    ctx.doc.setFont("helvetica", "bold");
    ctx.doc.setFontSize(9);
    ctx.doc.setTextColor(...BRAND.slate900);
    ctx.doc.text(readableAction(log.action), MARGIN + 5, ctx.y + 6);

    ctx.doc.setFont("helvetica", "normal");
    ctx.doc.setFontSize(8);
    ctx.doc.setTextColor(...BRAND.slate500);
    ctx.doc.text(formatTimestamp(log.timestamp), PAGE_W - MARGIN - 2, ctx.y + 6, { align: "right" });

    // Actor
    ctx.doc.setFont("helvetica", "italic");
    ctx.doc.setFontSize(8.5);
    ctx.doc.setTextColor(...BRAND.slate700);
    ctx.doc.text(`by ${log.actor || "system"}`, MARGIN + 5, ctx.y + 11);

    // Details
    ctx.doc.setFont("helvetica", "normal");
    ctx.doc.setFontSize(9);
    ctx.doc.setTextColor(...BRAND.slate700);
    ctx.doc.text(detailsLines, MARGIN + 5, ctx.y + 16);

    if (targetLines.length) {
      ctx.doc.setFont("helvetica", "italic");
      ctx.doc.setFontSize(8);
      ctx.doc.setTextColor(...BRAND.slate500);
      ctx.doc.text(targetLines, MARGIN + 5, ctx.y + 16 + detailsLines.length * 4 + 2);
    }

    ctx.y += blockH + 2;
  });
}

function summarize(logs) {
  if (!logs.length) {
    return { total: 0, distinctActions: 0, distinctActors: 0, range: "—" };
  }
  const actions = new Set();
  const actors = new Set();
  let earliest = null;
  let latest = null;
  logs.forEach((l) => {
    if (l.action) actions.add(l.action);
    if (l.actor) actors.add(l.actor);
    if (l.timestamp) {
      const t = new Date(l.timestamp);
      if (!earliest || t < earliest) earliest = t;
      if (!latest   || t > latest)   latest = t;
    }
  });
  let range = "—";
  if (earliest && latest) {
    range = earliest.getTime() === latest.getTime()
      ? safeDate(earliest.toISOString())
      : `${safeDate(earliest.toISOString())} → ${safeDate(latest.toISOString())}`;
  }
  return {
    total: logs.length,
    distinctActions: actions.size,
    distinctActors: actors.size,
    range,
  };
}

function describeFilters(filters = {}) {
  const parts = [];
  if (filters.search)         parts.push({ label: "Search", value: filters.search });
  if (filters.action && filters.action !== "all") {
    parts.push({ label: "Action", value: readableAction(filters.action) });
  }
  if (filters.dateFrom || filters.dateTo) {
    const f = filters.dateFrom ? safeDate(filters.dateFrom.toISOString()) : "—";
    const t = filters.dateTo   ? safeDate(filters.dateTo.toISOString())   : "—";
    parts.push({ label: "Date range", value: `${f} → ${t}` });
  }
  return parts;
}

export async function buildAuditTrailPdf(logs, filters = {}) {
  const generatedAt = new Date().toISOString();
  const summary = summarize(logs);
  const headerSubtitle = `${logs.length} record${logs.length === 1 ? "" : "s"} · ${summary.range}`;

  const logoDataUrl = await loadLogoDataUrl().catch(() => null);
  const doc = newDoc();
  const ctx = {
    doc,
    y: 38,
    headerSubtitle,
    headerTitle: "Audit Trail",
    logoDataUrl,
  };
  drawHeader(doc, headerSubtitle, logoDataUrl, "Audit Trail");

  drawSectionTitle(ctx, "Overview");
  drawAuditOverview(ctx, summary);

  const filterChips = describeFilters(filters);
  if (filterChips.length) {
    drawSectionTitle(ctx, "Active filters");
    drawKeyValueGrid(ctx, filterChips);
  }

  // For small result sets, the card layout reads better; for larger ones,
  // the table is denser and more scannable.
  drawSectionTitle(ctx, `Audit log entries (${logs.length})`);
  if (logs.length > 24) {
    drawAuditTable(ctx, logs);
  } else {
    drawAuditCards(ctx, logs);
  }

  const total = doc.getNumberOfPages();
  for (let i = 1; i <= total; i += 1) {
    doc.setPage(i);
    drawFooter(doc, i, total, generatedAt);
  }

  return {
    blob: doc.output("blob"),
    filename: `himaya_audit_${safeFilenameBase(new Date().toISOString().slice(0, 10))}.pdf`,
    mime: "application/pdf",
  };
}

export async function downloadAuditTrailPdf(logs, filters) {
  const { blob, filename } = await buildAuditTrailPdf(logs, filters);
  triggerBrowserDownload(blob, filename);
}
