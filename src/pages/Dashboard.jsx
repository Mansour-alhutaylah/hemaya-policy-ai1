import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
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
  const ref = useRef(null);
  const selectedOption = options.find(o => o.id === selected) || options[0];

  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 bg-card border border-border rounded-lg px-3 py-2 text-sm font-medium text-foreground hover:border-foreground/20 hover:bg-muted/40 transition-all duration-150 shadow-sm min-w-[176px]"
      >
        {loading
          ? <Loader2 className="w-4 h-4 text-muted-foreground flex-shrink-0 animate-spin" />
          : <Icon className="w-4 h-4 text-muted-foreground flex-shrink-0" />}
        <span className="flex-1 text-left truncate">{selectedOption?.label ?? 'All Uploaded Files'}</span>
        <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform duration-150 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1.5 w-64 bg-popover text-popover-foreground rounded-xl border border-border shadow-xl z-50 py-1.5 overflow-hidden">
          {options.map(opt => (
            <button
              key={opt.id}
              onClick={() => { onSelect(opt.id); setOpen(false); }}
              className="w-full flex items-center gap-3 px-3 py-2 text-sm text-foreground hover:bg-muted/60 transition-colors"
            >
              <span className="flex-shrink-0 w-8 flex items-center justify-center">
                <FileExtBadge ext={opt.ext} />
              </span>
              <span className="flex-1 text-left truncate">{opt.label}</span>
              {selected === opt.id && <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />}
            </button>
          ))}
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
        className="bg-card rounded-2xl border border-border shadow-sm p-5 flex flex-col gap-4"
        style={{ borderLeftWidth: 3, borderLeftColor: accentColor }}
      >
        <div className="flex items-start justify-between">
          <Skeleton className="w-9 h-9 rounded-xl" />
          <Skeleton className="w-14 h-5 rounded-full" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-7 w-20 rounded-lg" />
          <Skeleton className="h-4 w-28 rounded" />
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
        <p className="text-2xl font-bold tracking-tight text-foreground leading-none">{value}</p>
        <p className="text-sm font-medium text-muted-foreground mt-1.5">{title}</p>
        {subtitle && <p className="text-xs text-muted-foreground/70 mt-0.5">{subtitle}</p>}
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

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-popover text-popover-foreground border border-border rounded-xl shadow-lg px-3.5 py-2.5 text-sm">
      {label && <p className="text-xs font-semibold text-muted-foreground mb-1.5">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: p.color || p.fill }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-semibold text-foreground">{p.value}{p.unit || ''}</span>
        </p>
      ))}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const [selectedFile, setSelectedFile] = useState('all');
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // ── Policy list (drives the dropdown + "Policies Analyzed" KPI) ───────────
  // staleTime: 0 so returning from the Policies upload page always shows fresh
  // data without a manual refresh.
  const { data: policies = [], isLoading: policiesLoading } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-created_at', 100),
    staleTime: 0,
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
  const frameworkCount = 3;
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
    complianceByFramework.map(item => ({
      name:    item.framework.split(' ')[0],
      Covered: item.covered,
      Partial: item.partial,
      Missing: item.missing,
    })),
  [complianceByFramework]);

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

  // ── Recent activity ───────────────────────────────────────────────────────
  const displayActivity = auditLogs.slice(0, 5).map(log => ({
    id:     log.id,
    action: log.action,
    actor:  log.actor,
    target: typeof log.details === 'object' ? JSON.stringify(log.details) : log.details,
    time:   log.timestamp,
  }));

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
      {/* ── KPI Cards ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">

        {/* Static — not affected by file filter */}
        <KpiCard
          title="Compliance Frameworks"
          value={frameworkCount}
          icon={Shield}
          subtitle="Active frameworks"
          accentColor="#10b981"
        />

        {/* Stats-dependent — show skeleton during load / file switch */}
        <KpiCard
          title="Security Score"
          value={`${avgScore}%`}
          icon={TrendingUp}
          trend={avgScore >= 70 ? 'up' : 'down'}
          trendValue={avgScore >= 70 ? '+5%' : '-3%'}
          accentColor="#3b82f6"
          isLoading={statsSkeletons}
        />
        <KpiCard
          title="Controls Mapped"
          value={totalControls}
          icon={FileCheck}
          trend="up"
          trendValue="+12"
          accentColor="#8b5cf6"
          isLoading={statsSkeletons}
        />
        <KpiCard
          title="Open Gaps"
          value={openGaps}
          icon={AlertTriangle}
          trend="down"
          trendValue="-2"
          accentColor={openGaps > 10 ? SEVERITY_COLORS.Critical : SEVERITY_COLORS.High}
          isLoading={statsSkeletons}
        />

        {/* Derived from policy list, not stats */}
        <KpiCard
          title="Policies Analyzed"
          value={policies.length}
          icon={FileText}
          subtitle="This month"
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
          <CardContent className="pt-5">
            {statsSkeletons ? (
              <Skeleton className="h-60 w-full rounded-xl" />
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
          <CardContent className="pt-5">
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
                    <span className="text-2xl font-bold text-foreground leading-none">{totalGaps}</span>
                    <span className="text-xs text-muted-foreground mt-1 font-medium">Total Gaps</span>
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
          <CardContent className="pt-5">
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
                    <span className="text-2xl font-bold text-foreground leading-none">{compliancePct}%</span>
                    <span className="text-xs text-muted-foreground mt-1 font-medium">Compliant</span>
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
          <CardContent className="pt-5">
            {statsSkeletons ? (
              <Skeleton className="h-60 w-full rounded-xl" />
            ) : topRiskyData.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mb-3">
                  <CheckCircle2 className="w-6 h-6 text-emerald-500/60" />
                </div>
                <p className="text-sm font-medium text-muted-foreground">No open gaps</p>
                <p className="text-xs text-muted-foreground/70 mt-1">All controls are compliant</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(220, topRiskyData.length * 28)}>
                <BarChart
                  data={topRiskyData}
                  layout="vertical"
                  margin={{ top: 4, right: 12, left: 0, bottom: 0 }}
                  barSize={16}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={170}
                    tick={{ fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(148,163,184,0.12)' }} />
                  <Bar dataKey="score" fill={SEVERITY_COLORS.High} radius={[0, 4, 4, 0]} name="Risk score" />
                </BarChart>
              </ResponsiveContainer>
            )}
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
          <CardContent className="pt-5">
            {statsSkeletons ? (
              <Skeleton className="h-60 w-full rounded-xl" />
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
                  <Bar dataKey="Covered" stackId="a" fill={SEVERITY_COLORS.Low}      radius={[0, 0, 0, 0]} />
                  <Bar dataKey="Partial"  stackId="a" fill={SEVERITY_COLORS.Medium} />
                  <Bar dataKey="Missing"  stackId="a" fill={SEVERITY_COLORS.Critical} radius={[4, 4, 0, 0]} />
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
          <CardContent className="pt-5">
            {logsLoading ? (
              <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full rounded-lg" />
                ))}
              </div>
            ) : displayActivity.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <div className="relative mb-4">
                  <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center">
                    <Activity className="w-6 h-6 text-muted-foreground/60" />
                  </div>
                  <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-lg bg-card border border-border shadow-sm flex items-center justify-center">
                    <Clock className="w-3 h-3 text-muted-foreground/60" />
                  </div>
                </div>
                <p className="text-sm font-medium text-muted-foreground">No recent activity to show</p>
                <p className="text-xs text-muted-foreground/70 mt-1 max-w-[160px]">Events will appear here as they occur</p>
              </div>
            ) : (
              <div className="space-y-3">
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
                    <span className="text-xs text-muted-foreground flex-shrink-0 tabular-nums">
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
