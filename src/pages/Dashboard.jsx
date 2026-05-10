import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
import NextAction from '@/components/layout/NextAction';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Shield,
  FileCheck,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Upload,
  BarChart3,
  Clock,
  CheckCircle2,
  FileText,
  Filter,
  ChevronDown,
  ChevronRight,
  Activity,
  Check,
  Loader2,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { createPageUrl } from '@/utils';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { format } from 'date-fns';
import { SEVERITY_COLORS, STATUS_COLORS } from '@/components/charts/severityColors';

const Policy   = api.entities.Policy;
const AuditLog = api.entities.AuditLog;

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Derive a short extension key from a policy's file_type or file_name
function deriveExt(policy) {
  const src = (policy.file_type || policy.file_name || '').toLowerCase();
  if (src.includes('pdf'))  return 'pdf';
  if (src.includes('doc'))  return 'doc';
  if (src.includes('xls'))  return 'xls';
  return null;
}

// Phase G.1: routed through apiClient so 401 handling, FastAPI error
// parsing, and the Authorization header all live in one place.
async function fetchDashboardStats(policyId) {
  const path =
    policyId && policyId !== 'all'
      ? `/dashboard/stats?policy_id=${encodeURIComponent(policyId)}`
      : '/dashboard/stats';
  try {
    return await api.get(path);
  } catch {
    return null;
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function FileExtBadge({ ext }) {
  const styles = {
    pdf: 'bg-red-50 text-red-600 border border-red-200',
    doc: 'bg-blue-50 text-blue-600 border border-blue-200',
    xls: 'bg-emerald-50 text-emerald-600 border border-emerald-200',
  };
  const label = { pdf: 'PDF', doc: 'DOC', xls: 'XLS' };
  if (!ext) return <Filter className="w-4 h-4 text-muted-foreground" />;
  return (
    <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded ${styles[ext]}`}>
      {label[ext]}
    </span>
  );
}

function FilterDropdown({ options, selected, onSelect, icon: Icon, loading }) {
  const [open, setOpen] = useState(false);
  // Phase UI-8: highlighted index drives keyboard navigation. Defaults to
  // the currently-selected option each time the menu opens.
  const [activeIdx, setActiveIdx] = useState(-1);
  const ref = useRef(null);
  const triggerRef = useRef(null);
  const selectedOption = options.find(o => o.id === selected) || options[0];

  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  // Phase UI-8: Esc anywhere closes the menu and returns focus to the
  // trigger; a separate keydown on the trigger handles arrow / enter / tab.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  // Reset highlight to current selection each time the menu opens.
  useEffect(() => {
    if (open) {
      const i = options.findIndex(o => o.id === selected);
      setActiveIdx(i >= 0 ? i : 0);
    }
  }, [open, options, selected]);

  const handleKey = (e) => {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx(i => Math.min(options.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx(i => Math.max(0, i - 1));
    } else if (e.key === 'Home') {
      e.preventDefault();
      setActiveIdx(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      setActiveIdx(options.length - 1);
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      const opt = options[activeIdx];
      if (opt) {
        onSelect(opt.id);
        setOpen(false);
        triggerRef.current?.focus();
      }
    } else if (e.key === 'Tab') {
      // Closing on Tab matches the WAI-ARIA combobox pattern — focus
      // continues to the next interactive element.
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Filter dashboard by policy"
        aria-activedescendant={open && activeIdx >= 0 ? `filter-opt-${options[activeIdx]?.id}` : undefined}
        onClick={() => setOpen(v => !v)}
        onKeyDown={handleKey}
        className="flex items-center gap-2 bg-card border border-border rounded-lg px-3 py-2 text-sm font-medium text-foreground hover:border-foreground/20 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40 transition-all duration-150 shadow-sm min-w-[176px]"
      >
        {loading
          ? <Loader2 className="w-4 h-4 text-muted-foreground flex-shrink-0 animate-spin" />
          : <Icon className="w-4 h-4 text-muted-foreground flex-shrink-0" />}
        <span className="flex-1 text-left truncate">{selectedOption?.label ?? 'All Uploaded Files'}</span>
        <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform duration-150 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Policy filter options"
          className="absolute top-full left-0 mt-1.5 w-64 bg-popover text-popover-foreground rounded-xl border border-border shadow-xl z-50 py-1.5 overflow-hidden"
        >
          {options.map((opt, idx) => {
            const isActive = idx === activeIdx;
            const isSelected = selected === opt.id;
            return (
              <button
                key={opt.id}
                id={`filter-opt-${opt.id}`}
                type="button"
                role="option"
                aria-selected={isSelected}
                onClick={() => { onSelect(opt.id); setOpen(false); triggerRef.current?.focus(); }}
                onMouseEnter={() => setActiveIdx(idx)}
                className={`w-full flex items-center gap-3 px-3 py-2 text-sm text-foreground transition-colors ${
                  isActive ? 'bg-muted/60' : 'hover:bg-muted/60'
                }`}
              >
                <span className="flex-shrink-0 w-8 flex items-center justify-center">
                  <FileExtBadge ext={opt.ext} />
                </span>
                <span className="flex-1 text-left truncate">{opt.label}</span>
                {isSelected && <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// KPI card that renders a polished skeleton while its data is loading
function KpiCard({ title, value, subtitle, icon: Icon, trend, trendValue, accentColor, isLoading }) {
  if (isLoading) {
    return (
      <div
        className="bg-card rounded-2xl border border-border shadow-sm p-4 sm:p-6 flex flex-col gap-4"
        style={{ borderLeftWidth: 3, borderLeftColor: accentColor }}
      >
        <div className="flex items-start justify-between">
          <Skeleton className="w-9 h-9 rounded-xl" />
          <Skeleton className="w-14 h-5 rounded-full" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-8 w-20 rounded-lg" />
          <Skeleton className="h-3 w-24 rounded" />
          <Skeleton className="h-3 w-32 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div
      className="bg-card rounded-2xl border border-border shadow-sm hover:shadow-md transition-shadow duration-200 p-5 flex flex-col gap-4"
      style={{ borderLeftWidth: 3, borderLeftColor: accentColor }}
    >
      <div className="flex items-start justify-between">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: `${accentColor}26` }}
        >
          <Icon className="w-4 h-4" style={{ color: accentColor }} />
        </div>
        {trend && (
          <span className={`flex items-center text-xs font-semibold px-2 py-0.5 rounded-full ${
            trend === 'up'
              ? 'text-emerald-700 bg-emerald-50 dark:bg-emerald-500/15 dark:text-emerald-300'
              : 'text-red-600 bg-red-50 dark:bg-red-500/15 dark:text-red-300'
          }`}>
            {trend === 'up'
              ? <TrendingUp className="w-3 h-3 mr-0.5" />
              : <TrendingDown className="w-3 h-3 mr-0.5" />}
            {trendValue}
          </span>
        )}
      </div>
      <div>
        <p className="text-3xl font-semibold tracking-tight tabular-nums text-foreground leading-none">{value}</p>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mt-2">{title}</p>
        {subtitle && <p className="text-xs text-muted-foreground/70 mt-1 leading-snug">{subtitle}</p>}
      </div>
    </div>
  );
}

function CardIcon({ children, bg }) {
  return (
    <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${bg}`}>
      {children}
    </div>
  );
}

// Designed empty state for charts. Reused across the framework chart,
// controls-distribution chart, and risky-controls list. Single CTA, no
// fabricated copy — the message explains what the user has to do for
// the chart to populate, e.g. "Run an analysis...".
function ChartEmptyState({ icon: Icon, title, body, ctaLabel, ctaTo }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mb-3">
        <Icon className="w-6 h-6 text-muted-foreground/60" />
      </div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {body && <p className="text-xs text-muted-foreground/70 mt-1 max-w-[260px]">{body}</p>}
      {ctaLabel && ctaTo && (
        <Link to={ctaTo} className="mt-3">
          <Button size="sm" variant="outline" className="text-xs">
            {ctaLabel}
          </Button>
        </Link>
      )}
    </div>
  );
}

// Score-tinted summary tile for a single framework. Used when there are
// only 1-2 frameworks (a sparse bar chart looks broken in that case).
// All values come straight from a /dashboard/stats framework_scores row.
function FrameworkSummaryCard({ framework, score, covered, partial, missing }) {
  const total = covered + partial + missing;
  // Score-to-color is a *presentational* mapping — not severity. We reuse
  // the same green/yellow/red Status tokens the rest of the page uses so
  // the eye is consistent.
  const tone =
    score >= 80 ? { text: 'text-emerald-600 dark:text-emerald-400', bar: '#22C55E', tint: 'bg-emerald-50 dark:bg-emerald-500/10', border: 'border-emerald-200 dark:border-emerald-500/30' }
    : score >= 50 ? { text: 'text-amber-600 dark:text-amber-400',     bar: '#EAB308', tint: 'bg-amber-50 dark:bg-amber-500/10',     border: 'border-amber-200 dark:border-amber-500/30' }
    :              { text: 'text-red-600 dark:text-red-400',        bar: '#EF4444', tint: 'bg-red-50 dark:bg-red-500/10',         border: 'border-red-200 dark:border-red-500/30' };
  return (
    <div className={`rounded-xl border ${tone.border} ${tone.tint} p-4 flex flex-col gap-3`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{framework}</p>
          <p className="text-xs text-muted-foreground/80 mt-0.5 tabular-nums">{total} control{total === 1 ? '' : 's'}</p>
        </div>
        <p className={`text-3xl font-semibold tracking-tight tabular-nums ${tone.text} leading-none`}>{score}%</p>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${Math.max(0, Math.min(100, score))}%`, backgroundColor: tone.bar }} />
      </div>
      <div className="flex items-center justify-between text-[11px] tabular-nums">
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: STATUS_COLORS.Covered }} /><span className="text-muted-foreground">Compliant</span><span className="text-foreground font-semibold ml-1">{covered}</span></span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: STATUS_COLORS.Partial }} /><span className="text-muted-foreground">Partial</span><span className="text-foreground font-semibold ml-1">{partial}</span></span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: STATUS_COLORS.Missing }} /><span className="text-muted-foreground">Missing</span><span className="text-foreground font-semibold ml-1">{missing}</span></span>
      </div>
    </div>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  // Phase UI-3: prefer payload[0].payload.fullName when the chart deliberately
  // truncated its category labels (Top Risky Controls), so the tooltip always
  // shows the full text even when the axis tick is shortened with an ellipsis.
  const row = payload[0]?.payload;
  const heading = row?.fullName || label;
  return (
    <div className="bg-popover text-popover-foreground border border-border rounded-xl shadow-lg px-3.5 py-2.5 text-sm max-w-xs">
      {heading && <p className="text-xs font-semibold text-muted-foreground mb-1.5 break-words">{heading}</p>}
      {payload.map((p, i) => (
        <p key={i} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: p.color || p.fill }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-semibold text-foreground">{p.value}{p.unit || ''}</span>
        </p>
      ))}
      {row?.gap_count != null && (
        <p className="text-xs text-muted-foreground mt-1">
          {row.gap_count} open gap{row.gap_count === 1 ? '' : 's'}
        </p>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const [selectedFile, setSelectedFile] = useState('all');
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // ── Policy list (drives the dropdown + "Policies Analyzed" KPI) ───────────
  // Phase UI-3: removed `staleTime: 0`. The previous override forced a
  // refetch on every Dashboard visit even when the cache was already fresh,
  // which made tab-switches feel laggy. The Policies page already calls
  // `queryClient.invalidateQueries(['policies'])` after upload / pause /
  // resume / delete, so the cache is always up to date when it matters.
  // Falls back to the global staleTime (60 s) from query-client.js.
  const { data: policies = [], isLoading: policiesLoading } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-created_at', 100),
  });

  // ── File dropdown options derived from live policy list ───────────────────
  const fileOptions = useMemo(() => [
    { id: 'all', label: 'All Uploaded Files', ext: null },
    ...policies.map(p => ({
      id:    p.id,
      label: p.file_name,
      ext:   deriveExt(p),
    })),
  ], [policies]);

  // Guard: if the previously selected file was deleted, reset to 'all'
  useEffect(() => {
    if (selectedFile !== 'all' && !policies.find(p => p.id === selectedFile)) {
      setSelectedFile('all');
    }
  }, [policies, selectedFile]);

  // ── Dashboard stats — re-fetched whenever selectedFile changes ────────────
  const {
    data: stats,
    isLoading: statsLoading,
    isFetching: statsFetching,
  } = useQuery({
    queryKey: ['dashboardStats', selectedFile],
    queryFn: () => fetchDashboardStats(selectedFile),
    // Keep previous data visible while the new fetch is in flight so the UI
    // doesn't flash empty before the response arrives.
    placeholderData: (prev) => prev,
  });

  // ── Audit log ─────────────────────────────────────────────────────────────
  const { data: auditLogs = [], isLoading: logsLoading } = useQuery({
    queryKey: ['auditLogs'],
    queryFn: () => AuditLog.list('-timestamp', 10),
  });

  // ── Derived metrics ───────────────────────────────────────────────────────
  // Phase D-3: derive from real backend data (was hardcoded to 3).
  const frameworkCount = stats?.framework_scores?.length ?? 0;
  const avgScore      = stats?.security_score || 0;
  const openGaps      = stats?.open_gaps      || 0;
  // Prefer the new `controls_total` field (covered + partial + missing).
  // Fall back to `controls_mapped` so older backends keep working.
  const totalControls = stats?.controls_total ?? stats?.controls_mapped ?? 0;

  const complianceByFramework = useMemo(() =>
    (stats?.framework_scores || []).map(r => ({
      framework: r.framework,
      score:     Math.round(r.score || 0),
      covered:   r.covered  || 0,
      partial:   r.partial  || 0,
      missing:   r.missing  || 0,
    })),
  [stats]);

  const sevDist = stats?.severity_distribution || {};
  const riskData = useMemo(() => [
    { name: 'Critical', value: sevDist['Critical'] || 0, color: SEVERITY_COLORS.Critical },
    { name: 'High',     value: sevDist['High']     || 0, color: SEVERITY_COLORS.High },
    { name: 'Medium',   value: sevDist['Medium']   || 0, color: SEVERITY_COLORS.Medium },
    { name: 'Low',      value: sevDist['Low']      || 0, color: SEVERITY_COLORS.Low },
  ], [stats]);
  const totalGaps = riskData.reduce((sum, r) => sum + r.value, 0);

  const controlsData = useMemo(() =>
    // Use the full framework name on the X-axis. The previous .split(' ')[0]
    // turned "NCA ECC" -> "NCA" and "ISO 27001" -> "ISO" silently, dropping
    // identifying detail. Full name fits because the tooltip shows the same.
    complianceByFramework.map(item => ({
      name:    item.framework,
      Covered: item.covered,
      Partial: item.partial,
      Missing: item.missing,
    })),
  [complianceByFramework]);

  // KPI context lines — all derived from data already loaded above. Strict
  // rule: never invent a metric. If we can't compute it from the existing
  // payload, the line stays empty.
  const kpiCovered = complianceByFramework.reduce((s, f) => s + f.covered, 0);
  const kpiPartial = complianceByFramework.reduce((s, f) => s + f.partial, 0);
  const kpiMissing = complianceByFramework.reduce((s, f) => s + f.missing, 0);
  const selectedPolicy = selectedFile === 'all'
    ? null
    : policies.find(p => p.id === selectedFile);

  // Phase D: status donut data (covered / partial / missing across frameworks)
  const statusOverview = stats?.status_overview || {};
  const statusData = useMemo(() => [
    { name: 'Covered', value: statusOverview.compliant     || 0, color: STATUS_COLORS.Covered },
    { name: 'Partial', value: statusOverview.partial       || 0, color: STATUS_COLORS.Partial },
    { name: 'Missing', value: statusOverview.non_compliant || 0, color: STATUS_COLORS.Missing },
  ], [stats]);
  const totalAssessed = statusData.reduce((s, r) => s + r.value, 0);
  const compliancePct = totalAssessed
    ? Math.round((statusData[0].value / totalAssessed) * 100)
    : 0;

  // Phase D: top-10 risky controls (severity-weighted)
  const topRiskyData = useMemo(() => {
    const rows = stats?.top_risky_controls || [];
    return rows.map(r => ({
      // truncate long control names so the y-axis stays readable
      name: (r.control_name || '').length > 38
        ? (r.control_name || '').slice(0, 36) + '…'
        : (r.control_name || ''),
      fullName:  r.control_name || '',
      gap_count: r.gap_count || 0,
      score:     r.risk_score || 0,
    }));
  }, [stats]);

  // Whether KPI/chart areas should show skeletons (first load or no data yet)
  const statsSkeletons = statsLoading;
  // Whether a subtle "refreshing" indicator is needed (file switch in-flight)
  const statsRefreshing = statsFetching && !statsLoading;

  // ── Phase UI-1: recommended next action ───────────────────────────────────
  // Computed from already-loaded data — pages-as-state pattern. We hide the
  // banner while the policies query is still in flight so the user never
  // sees "upload your first policy" flash for a beat before the real CTA.
  const nextAction = useMemo(() => {
    if (policiesLoading) return null;
    if (policies.length === 0) {
      return {
        primary: {
          label: 'Upload your first policy',
          helper: 'Pick a PDF, DOCX, or TXT under 50 MB to start your first compliance analysis.',
          to: createPageUrl('Policies'),
          icon: Upload,
        },
      };
    }
    if (statsSkeletons) return null;
    const totalAssessedLocal =
      (statusOverview.compliant || 0) +
      (statusOverview.partial || 0) +
      (statusOverview.non_compliant || 0);
    if (totalAssessedLocal === 0) {
      return {
        primary: {
          label: 'Run your first analysis',
          helper: 'Open Policies and click Start Compliance Analysis on a policy to see it scored.',
          to: createPageUrl('Policies'),
          icon: BarChart3,
        },
      };
    }
    if ((openGaps || 0) > 0) {
      const top = Math.min(openGaps, 5);
      return {
        primary: {
          label: `Review top ${top} gap${top === 1 ? '' : 's'}`,
          helper: 'Sorted by priority — severity weighted by how long the gap has been open.',
          to: createPageUrl('GapsRisks'),
          icon: AlertTriangle,
        },
        secondary: [
          { label: 'Open Mapping Review', to: createPageUrl('MappingReview') },
        ],
        tone: 'warning',
      };
    }
    return {
      primary: {
        label: 'Generate compliance report',
        helper: 'No open gaps — package your latest analysis as a PDF or DOCX.',
        to: createPageUrl('Reports'),
        icon: FileText,
      },
      tone: 'success',
    };
  }, [policiesLoading, policies.length, statsSkeletons, statusOverview, openGaps]);

  // ── Recent activity ───────────────────────────────────────────────────────
  // Phase UI-3: memoised so the slice + map (and the JSON.stringify on the
  // details payload) only run when auditLogs actually changes — not on every
  // unrelated re-render of this page (filter changes, hover, etc).
  const displayActivity = useMemo(() => auditLogs.slice(0, 5).map(log => ({
    id:     log.id,
    action: log.action,
    actor:  log.actor,
    target: typeof log.details === 'object' ? JSON.stringify(log.details) : log.details,
    time:   log.timestamp,
  })), [auditLogs]);

  const getActionIcon = (action) => {
    switch (action) {
      case 'policy_upload':
        return <Upload className="w-4 h-4 text-blue-500" />;
      case 'analysis_complete':
      case 'analysis_start':
        return <BarChart3 className="w-4 h-4 text-emerald-500" />;
      case 'gap_update':
        return <AlertTriangle className="w-4 h-4 text-amber-500" />;
      case 'report_generate':
        return <FileText className="w-4 h-4 text-purple-500" />;
      default:
        return <CheckCircle2 className="w-4 h-4 text-muted-foreground" />;
    }
  };

  return (
    <PageContainer
      title="Executive Dashboard"
      subtitle="Real-time compliance monitoring and insights"
      actions={
        <div className="flex items-center gap-2.5 flex-wrap">
          <FilterDropdown
            options={fileOptions}
            selected={selectedFile}
            onSelect={setSelectedFile}
            icon={Filter}
            loading={policiesLoading}
          />
          <Link to={createPageUrl('Policies')}>
            <Button className="bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-sm text-sm">
              <Upload className="w-4 h-4 mr-2" />
              Upload Policy
            </Button>
          </Link>
        </div>
      }
    >
      {/* Phase UI-1: recommended next step (computed above) */}
      {nextAction && (
        <NextAction
          primary={nextAction.primary}
          secondary={nextAction.secondary}
          tone={nextAction.tone}
        />
      )}

      {/* ── KPI Cards ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">

        {/* Phase D-3: trend chips removed — the API returns no period-
            over-period delta, so the previous '+5%' / '-3%' / '+12' / '-2'
            values were fabricated. Subtitles are computed from already-loaded
            data only — no invented metrics. */}
        <KpiCard
          title="Compliance Frameworks"
          value={frameworkCount}
          icon={Shield}
          subtitle={
            frameworkCount === 0
              ? 'Run an analysis to populate'
              : `Across ${policies.length} policy${policies.length === 1 ? '' : 'ies'}`
          }
          accentColor="#10b981"
          isLoading={statsSkeletons || policiesLoading}
        />

        <KpiCard
          title="Security Score"
          value={`${avgScore}%`}
          icon={TrendingUp}
          subtitle={
            selectedPolicy
              ? `For ${selectedPolicy.file_name}`
              : frameworkCount > 0
                ? `Average across ${frameworkCount} framework${frameworkCount === 1 ? '' : 's'}`
                : 'No analyses yet'
          }
          accentColor="#3b82f6"
          isLoading={statsSkeletons}
        />
        <KpiCard
          title="Controls Mapped"
          value={totalControls}
          icon={FileCheck}
          subtitle={
            totalControls === 0
              ? 'No controls mapped yet'
              : `${kpiCovered} compliant · ${kpiPartial} partial · ${kpiMissing} missing`
          }
          accentColor="#8b5cf6"
          isLoading={statsSkeletons}
        />
        <KpiCard
          title="Open Gaps"
          value={openGaps}
          icon={AlertTriangle}
          subtitle={
            openGaps === 0
              ? frameworkCount === 0 ? 'No analyses yet' : 'All controls compliant'
              : `Across ${frameworkCount} framework${frameworkCount === 1 ? '' : 's'}`
          }
          accentColor={openGaps > 10 ? SEVERITY_COLORS.Critical : SEVERITY_COLORS.High}
          isLoading={statsSkeletons}
        />

        <KpiCard
          title="Policies Analyzed"
          value={policies.length}
          icon={FileText}
          subtitle={policies.length === 0 ? 'Upload your first policy' : 'All time'}
          accentColor="#06b6d4"
          isLoading={policiesLoading}
        />
      </div>

      {/* ── Charts Row ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">

        {/* Compliance by Framework */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base font-semibold flex items-center gap-2.5 text-foreground">
              <CardIcon bg="bg-emerald-50 dark:bg-emerald-500/15">
                <Shield className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              </CardIcon>
              Compliance Level by Framework
              {statsRefreshing && (
                <Loader2 className="w-3.5 h-3.5 text-muted-foreground animate-spin ml-auto" />
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 sm:p-6">
            {statsSkeletons ? (
              <Skeleton className="h-60 w-full rounded-xl" />
            ) : complianceByFramework.length === 0 ? (
              <ChartEmptyState
                icon={Shield}
                title="No framework scores yet"
                body="Run a compliance analysis on a policy to populate framework scores."
                ctaLabel="Open Policies"
                ctaTo={createPageUrl('Policies')}
              />
            ) : complianceByFramework.length <= 2 ? (
              // Sparse-data treatment: a single 80%-tall bar against an empty
              // grid reads as broken. Per-framework summary cards convey the
              // same information richly without looking unfinished.
              <div className={`grid gap-3 ${complianceByFramework.length === 1 ? 'grid-cols-1' : 'grid-cols-1 sm:grid-cols-2'}`}>
                {complianceByFramework.map(f => (
                  <FrameworkSummaryCard
                    key={f.framework}
                    framework={f.framework}
                    score={f.score}
                    covered={f.covered}
                    partial={f.partial}
                    missing={f.missing}
                  />
                ))}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={256}>
                <BarChart
                  data={complianceByFramework}
                  barSize={30}
                  margin={{ top: 4, right: 4, left: -18, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="framework"
                    tick={{ fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    interval={0}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={v => `${v}%`}
                  />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(148,163,184,0.12)', radius: 4 }} />
                  <Bar dataKey="score" fill="#10b981" radius={[4, 4, 0, 0]} name="Compliance" unit="%" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Gap Severity Distribution */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base font-semibold flex items-center gap-2.5 text-foreground">
              <CardIcon bg="bg-amber-50 dark:bg-amber-500/15">
                <AlertTriangle className="w-4 h-4 text-amber-500 dark:text-amber-400" />
              </CardIcon>
              Gap Severity Distribution
              {statsRefreshing && (
                <Loader2 className="w-3.5 h-3.5 text-muted-foreground animate-spin ml-auto" />
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 sm:p-6">
            {statsSkeletons ? (
              <Skeleton className="h-60 w-full rounded-xl" />
            ) : (
              <div className="flex items-center gap-6">
                <div className="relative flex-shrink-0" style={{ width: 200, height: 200 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={riskData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={88}
                        paddingAngle={2}
                        dataKey="value"
                        startAngle={90}
                        endAngle={-270}
                        strokeWidth={0}
                        cursor="pointer"
                        onClick={(data) => {
                          if (data?.name) navigate(`/GapsRisks?severity=${data.name}`);
                        }}
                      >
                        {riskData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">Risk</span>
                    <span className="text-3xl font-semibold tracking-tight tabular-nums text-foreground leading-none mt-1">{totalGaps}</span>
                    <span className="text-[11px] text-muted-foreground/70 mt-1">Total gaps</span>
                  </div>
                </div>

                <div className="flex-1 space-y-3">
                  {riskData.map((item, index) => (
                    <button
                      key={index}
                      onClick={() => navigate(`/GapsRisks?severity=${item.name}`)}
                      className="flex items-center gap-3 w-full text-left hover:bg-muted/50 rounded-lg px-2 py-1 -mx-2 transition-colors cursor-pointer"
                    >
                      <div
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: item.color }}
                      />
                      <span className="text-sm text-muted-foreground flex-1">{item.name}</span>
                      <span
                        className="text-xs font-semibold text-white px-2 py-0.5 rounded-full tabular-nums"
                        style={{ backgroundColor: item.color }}
                      >
                        {item.value}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Phase D: Compliance Status Donut + Top-10 Risky Controls ─────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">

        {/* Compliance Status Donut — covered / partial / missing across frameworks */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base font-semibold flex items-center gap-2.5 text-foreground">
              <CardIcon bg="bg-emerald-50 dark:bg-emerald-500/15">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              </CardIcon>
              Compliance Status
              {statsRefreshing && (
                <Loader2 className="w-3.5 h-3.5 text-muted-foreground animate-spin ml-auto" />
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 sm:p-6">
            {statsSkeletons ? (
              <Skeleton className="h-60 w-full rounded-xl" />
            ) : totalAssessed === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mb-3">
                  <BarChart3 className="w-6 h-6 text-muted-foreground/60" />
                </div>
                <p className="text-sm font-medium text-muted-foreground">No analyses yet</p>
                <p className="text-xs text-muted-foreground/70 mt-1">Run an analysis to see compliance status</p>
              </div>
            ) : (
              <div className="flex items-center gap-6">
                <div className="relative flex-shrink-0" style={{ width: 200, height: 200 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={statusData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={88}
                        paddingAngle={2}
                        dataKey="value"
                        startAngle={90}
                        endAngle={-270}
                        strokeWidth={0}
                      >
                        {statusData.map((entry, index) => (
                          <Cell key={`cell-status-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">Compliance</span>
                    <span className="text-3xl font-semibold tracking-tight tabular-nums text-foreground leading-none mt-1">{compliancePct}%</span>
                    <span className="text-[11px] text-muted-foreground/70 mt-1">Compliant</span>
                  </div>
                </div>
                <div className="flex-1 space-y-3">
                  {statusData.map((item, index) => (
                    <div
                      key={index}
                      className="flex items-center gap-3 w-full text-left rounded-lg px-2 py-1 -mx-2"
                    >
                      <div
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: item.color }}
                      />
                      <span className="text-sm text-muted-foreground flex-1">{item.name}</span>
                      <span
                        className="text-xs font-semibold text-white px-2 py-0.5 rounded-full tabular-nums"
                        style={{ backgroundColor: item.color }}
                      >
                        {item.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top-10 Risky Controls — severity-weighted */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base font-semibold flex items-center gap-2.5 text-foreground">
              <CardIcon bg="bg-red-50 dark:bg-red-500/15">
                <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400" />
              </CardIcon>
              Top Risky Controls
              {statsRefreshing && (
                <Loader2 className="w-3.5 h-3.5 text-muted-foreground animate-spin ml-auto" />
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 sm:p-6">
            {statsSkeletons ? (
              <div className="space-y-2.5">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full rounded-lg" />
                ))}
              </div>
            ) : topRiskyData.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <div className="w-14 h-14 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center mb-3">
                  <CheckCircle2 className="w-6 h-6 text-emerald-500/70" />
                </div>
                <p className="text-sm font-medium text-foreground">No open gaps</p>
                <p className="text-xs text-muted-foreground/70 mt-1">All controls are compliant</p>
              </div>
            ) : (() => {
              // List layout. The previous horizontal bar chart truncated each
              // control name to 36 chars + ellipsis, hiding the most useful
              // identifying text. We render the full name (line-clamped to 2
              // for visual rhythm), the open-gap count, and an intensity bar
              // sized relative to the highest risk_score in the list.
              // top_risky_controls[] gives only {control_name, gap_count,
              // risk_score} — no severity, no control_id — so we don't
              // fabricate either. Rows link to /GapsRisks (existing route).
              const maxScore = Math.max(...topRiskyData.map(r => r.score), 1);
              return (
                <ul className="space-y-2">
                  {topRiskyData.map((row, idx) => {
                    const widthPct = Math.round((row.score / maxScore) * 100);
                    return (
                      <li key={idx}>
                        <Link
                          to={createPageUrl('GapsRisks')}
                          className="group flex items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 hover:bg-muted/50 hover:border-border transition-colors"
                        >
                          <span className="w-5 text-[11px] font-semibold tabular-nums text-muted-foreground/70 flex-shrink-0">
                            {idx + 1}
                          </span>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-foreground line-clamp-2 leading-snug" title={row.fullName}>
                              {row.fullName}
                            </p>
                            <div className="mt-1.5 flex items-center gap-3">
                              <span className="text-xs text-muted-foreground tabular-nums flex-shrink-0">
                                {row.gap_count} open gap{row.gap_count === 1 ? '' : 's'}
                              </span>
                              <div className="h-1 flex-1 bg-muted rounded-full overflow-hidden">
                                <div
                                  className="h-full rounded-full"
                                  style={{ width: `${widthPct}%`, backgroundColor: SEVERITY_COLORS.High }}
                                />
                              </div>
                            </div>
                          </div>
                          <ChevronRight className="w-4 h-4 text-muted-foreground/40 group-hover:text-foreground transition-colors flex-shrink-0" />
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              );
            })()}
          </CardContent>
        </Card>
      </div>

      {/* ── Bottom Row ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Controls Distribution */}
        <Card className="lg:col-span-2 shadow-sm">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base font-semibold flex items-center gap-2.5 text-foreground">
              <CardIcon bg="bg-blue-50 dark:bg-blue-500/15">
                <BarChart3 className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              </CardIcon>
              Controls Distribution
              {statsRefreshing && (
                <Loader2 className="w-3.5 h-3.5 text-muted-foreground animate-spin ml-auto" />
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 sm:p-6">
            {statsSkeletons ? (
              <Skeleton className="h-60 w-full rounded-xl" />
            ) : controlsData.length === 0 ? (
              <ChartEmptyState
                icon={BarChart3}
                title="No control data yet"
                body="Run a compliance analysis to see how each framework's controls are covered."
                ctaLabel="Open Policies"
                ctaTo={createPageUrl('Policies')}
              />
            ) : controlsData.length <= 2 ? (
              // Sparse-data treatment: a stacked bar with one column reads as
              // a thermometer, not a distribution. Show per-framework rows
              // with three counters instead, sharing the page's status palette.
              <div className="space-y-3">
                {controlsData.map(row => {
                  const total = row.Covered + row.Partial + row.Missing;
                  const widths = total
                    ? {
                        c: (row.Covered / total) * 100,
                        p: (row.Partial / total) * 100,
                        m: (row.Missing / total) * 100,
                      }
                    : { c: 0, p: 0, m: 0 };
                  return (
                    <div key={row.name} className="rounded-xl border border-border bg-card p-4">
                      <div className="flex items-center justify-between gap-3 mb-3">
                        <p className="text-sm font-semibold text-foreground truncate" title={row.name}>{row.name}</p>
                        <p className="text-xs text-muted-foreground tabular-nums flex-shrink-0">{total} control{total === 1 ? '' : 's'}</p>
                      </div>
                      <div className="flex h-2 rounded-full overflow-hidden bg-muted">
                        <div style={{ width: `${widths.c}%`, backgroundColor: STATUS_COLORS.Covered }} />
                        <div style={{ width: `${widths.p}%`, backgroundColor: STATUS_COLORS.Partial }} />
                        <div style={{ width: `${widths.m}%`, backgroundColor: STATUS_COLORS.Missing }} />
                      </div>
                      <div className="mt-3 flex items-center gap-4 text-xs tabular-nums flex-wrap">
                        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: STATUS_COLORS.Covered }} /><span className="text-muted-foreground">Compliant</span><span className="text-foreground font-semibold ml-0.5">{row.Covered}</span></span>
                        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: STATUS_COLORS.Partial }} /><span className="text-muted-foreground">Partial</span><span className="text-foreground font-semibold ml-0.5">{row.Partial}</span></span>
                        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: STATUS_COLORS.Missing }} /><span className="text-muted-foreground">Missing</span><span className="text-foreground font-semibold ml-0.5">{row.Missing}</span></span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={256}>
                <BarChart
                  data={controlsData}
                  barSize={22}
                  margin={{ top: 4, right: 4, left: -18, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    interval={0}
                  />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(148,163,184,0.12)', radius: 4 }} />
                  <Legend
                    iconType="circle"
                    iconSize={8}
                    formatter={v => <span className="text-muted-foreground" style={{ fontSize: 12 }}>{v}</span>}
                  />
                  {/* Phase HOTFIX: use STATUS_COLORS (not SEVERITY_COLORS) on
                      compliance categories. Same green/yellow/red hexes today,
                      but semantically a Compliant control isn't "Low severity". */}
                  <Bar dataKey="Covered" stackId="a" fill={STATUS_COLORS.Covered} />
                  <Bar dataKey="Partial" stackId="a" fill={STATUS_COLORS.Partial} />
                  <Bar dataKey="Missing" stackId="a" fill={STATUS_COLORS.Missing} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base font-semibold flex items-center gap-2.5 text-foreground">
              <CardIcon bg="bg-muted">
                <Clock className="w-4 h-4 text-muted-foreground" />
              </CardIcon>
              Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 sm:p-6">
            {logsLoading ? (
              <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full rounded-lg" />
                ))}
              </div>
            ) : displayActivity.length === 0 ? (
              // Compact empty state — the previous version stacked a 14x14
              // icon bowl, a duplicate clock badge, and two paragraphs of
              // helper text, taking over half the card. This is one row.
              <div className="flex items-center gap-3 py-2">
                <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
                  <Activity className="w-4 h-4 text-muted-foreground/60" />
                </div>
                <p className="text-xs text-muted-foreground leading-snug">
                  No activity yet — events appear as you upload, analyse, and review.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {displayActivity.map((activity) => (
                  <div key={activity.id} className="flex items-start gap-3 group">
                    <div className="w-8 h-8 rounded-lg bg-muted/60 border border-border/60 flex items-center justify-center flex-shrink-0 group-hover:border-border transition-colors">
                      {getActionIcon(activity.action)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">
                        {activity.action?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">
                        {activity.target || activity.actor}
                      </p>
                    </div>
                    <span className="text-[11px] text-muted-foreground flex-shrink-0 tabular-nums mt-1">
                      {activity.time ? format(new Date(activity.time), 'HH:mm') : 'Now'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
