import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  GitCompare, Search, FileText, AlertTriangle, CheckCircle2,
  XCircle, Brain, Loader2, ListChecks, Wrench, Quote, Filter,
  Layers, ChevronRight, BookOpen,
} from 'lucide-react';

import PageContainer from '@/components/layout/PageContainer';
import NextAction from '@/components/layout/NextAction';
import { createPageUrl } from '@/utils';
import EmptyState from '@/components/ui/EmptyState';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Tooltip as UiTooltip,
  TooltipTrigger as UiTooltipTrigger,
  TooltipContent as UiTooltipContent,
  TooltipProvider,
} from '@/components/ui/tooltip';
import { useToast } from '@/components/ui/use-toast';

import { api } from '@/api/apiClient';

// ─── helpers ──────────────────────────────────────────────────────────────────
// Phase G.1: previously had a hand-rolled authGet helper here. Replaced by
// api.get from apiClient — same auth header, same 401 handling, plus the
// FastAPI-shaped error parsing the rest of the app already depends on.

const STATUS_META = {
  compliant: {
    label: 'Compliant',
    icon: CheckCircle2,
    chipClass:
      'text-emerald-700 bg-emerald-50 border-emerald-200 ' +
      'dark:text-emerald-300 dark:bg-emerald-500/15 dark:border-emerald-500/30',
    barClass: 'bg-emerald-500/80 dark:bg-emerald-400/70',
    headerClass:
      'border-emerald-500/30 bg-emerald-500/5 dark:bg-emerald-500/8',
  },
  partial: {
    label: 'Partial',
    icon: AlertTriangle,
    chipClass:
      'text-amber-700 bg-amber-50 border-amber-200 ' +
      'dark:text-amber-300 dark:bg-amber-500/15 dark:border-amber-500/30',
    barClass: 'bg-amber-500/80 dark:bg-amber-400/70',
    headerClass: 'border-amber-500/30 bg-amber-500/5 dark:bg-amber-500/8',
  },
  non_compliant: {
    label: 'Non-Compliant',
    icon: XCircle,
    chipClass:
      'text-red-700 bg-red-50 border-red-200 ' +
      'dark:text-red-300 dark:bg-red-500/15 dark:border-red-500/30',
    barClass: 'bg-red-500/80 dark:bg-red-400/70',
    headerClass: 'border-red-500/30 bg-red-500/5 dark:bg-red-500/8',
  },
};

function confidenceLabel(score) {
  if (score >= 0.8) return 'High';
  if (score >= 0.5) return 'Medium';
  return 'Low';
}

function confidenceClass(score) {
  if (score >= 0.8) {
    return 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/15';
  }
  if (score >= 0.5) {
    return 'text-amber-700 dark:text-amber-300 bg-amber-500/15';
  }
  return 'text-red-700 dark:text-red-300 bg-red-500/15';
}

// ─── Summary stats card ───────────────────────────────────────────────────────

function StatChip({ tone, value, label, icon: Icon }) {
  const meta = STATUS_META[tone] || STATUS_META.partial;
  return (
    <Card className="relative overflow-hidden shadow-sm">
      <span className={`absolute left-0 top-0 h-full w-1 ${meta.barClass}`} />
      <CardContent className="p-4 pl-5 flex items-center gap-4">
        <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-muted">
          <Icon className="w-6 h-6 text-muted-foreground" />
        </div>
        <div>
          <p className="text-2xl font-bold leading-none">{value}</p>
          <p className="text-sm mt-1 font-medium text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Explainability card ──────────────────────────────────────────────────────

function ExplainabilityCard({ item, onGenerateDraft, isGenerating }) {
  const meta = STATUS_META[item.status] || STATUS_META.non_compliant;
  const Icon = meta.icon;

  const hasEvidence =
    item.policy_evidence &&
    item.policy_evidence.trim() &&
    item.policy_evidence.trim().toLowerCase() !== 'no direct evidence found';

  // Phase UI-5: per-card "Generate draft" action. Only meaningful when the
  // control isn't already compliant AND the backend returned a
  // mapping_review_id we can post to /api/remediation/generate.
  const canGenerate = item.status !== 'compliant' && !!item.mapping_review_id;
  const showGenerate = item.status !== 'compliant';

  return (
    <Card className={`relative overflow-hidden border ${meta.headerClass}`}>
      {/* Phase UI-5: status accent — 4 px left bar, status-coloured */}
      <span className={`absolute left-0 top-0 h-full w-1 ${meta.barClass}`} />
      <CardContent className="p-0">
        {/* Header */}
        <div className="flex items-start gap-3 px-5 py-4 border-b border-border/40">
          <div className={`mt-0.5 w-9 h-9 rounded-lg flex items-center justify-center ${meta.chipClass}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className="font-mono text-xs">
                {item.control_code}
              </Badge>
              <Badge className="bg-muted text-foreground border border-border/60 hover:bg-muted">
                {item.framework_name}
              </Badge>
              <span className={`text-xs font-medium px-2 py-0.5 rounded border ${meta.chipClass}`}>
                {meta.label}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${confidenceClass(item.confidence)}`}>
                {confidenceLabel(item.confidence)} · {Math.round(item.confidence * 100)}%
              </span>
            </div>
            {item.source?.section_title && (
              <p className="text-xs text-muted-foreground mt-1 truncate">
                Section: <span className="font-medium">{item.source.section_title}</span>
                {item.subdomain_code ? ` (${item.subdomain_code})` : ''}
              </p>
            )}
            <p className="text-sm text-foreground/80 mt-2">{item.reason}</p>
          </div>
        </div>

        {/* Side-by-side: framework requirement | policy evidence */}
        <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border/40">
          {/* Left: framework requirement */}
          <div className="p-5">
            <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5 uppercase tracking-wider">
              <BookOpen className="w-3.5 h-3.5" />
              Framework Requirement
            </p>
            <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
              {item.framework_requirement || '—'}
            </p>
          </div>

          {/* Right: policy evidence (or empty) */}
          <div className="p-5">
            <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5 uppercase tracking-wider">
              <Quote className="w-3.5 h-3.5" />
              Policy Evidence
              {/* Phase E.1: source attribution chip — Phase 11 data, finally on the UI */}
              {hasEvidence && item.source?.page_number != null && (
                <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20">
                  <FileText className="w-3 h-3" />
                  Page {item.source.page_number}
                  {item.source.paragraph_index != null && ` · ¶${item.source.paragraph_index}`}
                </span>
              )}
            </p>
            {hasEvidence ? (
              <p className="text-sm italic text-foreground/85 leading-relaxed whitespace-pre-wrap">
                "{item.policy_evidence}"
              </p>
            ) : (
              <p className="text-sm text-muted-foreground italic">
                No relevant policy evidence found.
              </p>
            )}
          </div>
        </div>

        {/* Missing requirements / recommended fix */}
        {(item.status !== 'compliant') && (
          <div className="px-5 py-4 border-t border-border/40 grid grid-cols-1 md:grid-cols-2 gap-5">
            {item.missing_requirements?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-2 flex items-center gap-1.5 uppercase tracking-wider">
                  <ListChecks className="w-3.5 h-3.5" />
                  Missing Requirements
                </p>
                <ul className="space-y-1.5">
                  {item.missing_requirements.map((req, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-foreground/85">
                      <span className="mt-0.5 shrink-0 w-4 h-4 rounded-full bg-amber-500/20 text-amber-700 dark:text-amber-300 flex items-center justify-center text-[10px] font-bold">
                        {i + 1}
                      </span>
                      <span>{req}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {item.recommended_fix && (
              <div>
                <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 mb-2 flex items-center gap-1.5 uppercase tracking-wider">
                  <Wrench className="w-3.5 h-3.5" />
                  Recommended Fix
                </p>
                <p className="text-xs text-foreground/85 whitespace-pre-wrap leading-relaxed">
                  {item.recommended_fix}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Phase UI-5: action footer — Generate draft (where wired) + space
            reserved for Accept / Reject in a follow-up phase. */}
        {showGenerate && (
          <div className="px-5 py-3 border-t border-border/40 flex items-center justify-end gap-2">
            {canGenerate ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onGenerateDraft?.(item)}
                disabled={isGenerating}
                className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/10"
              >
                {isGenerating
                  ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  : <Wrench className="w-3.5 h-3.5 mr-1.5" />}
                Generate remediation draft
              </Button>
            ) : (
              <UiTooltip>
                <UiTooltipTrigger asChild>
                  <span>
                    <Button size="sm" variant="outline" disabled>
                      <Wrench className="w-3.5 h-3.5 mr-1.5" />
                      Generate remediation draft
                    </Button>
                  </span>
                </UiTooltipTrigger>
                <UiTooltipContent className="bg-popover text-popover-foreground border border-border text-xs max-w-xs">
                  This framework's analyzer doesn't write a mapping_reviews
                  row, so drafts can't be generated from this card yet. Use
                  the Gaps page or wait for the next workflow update.
                </UiTooltipContent>
              </UiTooltip>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function MappingReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const initialPolicyId = searchParams.get('policy_id') || '';

  const [policyId, setPolicyId] = useState(initialPolicyId);
  const [frameworkId, setFrameworkId] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [confidenceTier, setConfidenceTier] = useState('all');
  const [search, setSearch] = useState('');

  // Sync the policy id back to the URL so deep links work
  useEffect(() => {
    if (policyId && policyId !== searchParams.get('policy_id')) {
      const next = new URLSearchParams(searchParams);
      next.set('policy_id', policyId);
      setSearchParams(next, { replace: true });
    }
  }, [policyId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Deep-link target control (e.g. from Explainability "Review Mapping" link).
  // We scroll the matching card into view and pulse a ring around it once
  // the data lands. Cleared after the first scroll so re-filters don't yank
  // the user around mid-session.
  const focusControl = searchParams.get('control');
  const [pendingFocusControl, setPendingFocusControl] = useState(focusControl);
  useEffect(() => {
    if (!focusControl) return;
    setPendingFocusControl(focusControl);
  }, [focusControl]);

  // Policies
  const { data: policies = [], isLoading: policiesLoading } = useQuery({
    queryKey: ['policies'],
    queryFn: () => api.entities.Policy.list(),
  });

  // Frameworks for the selected policy (only those with analysis rows)
  const { data: frameworksWithResults = [] } = useQuery({
    queryKey: ['mappingFrameworks', policyId],
    queryFn: () => api.get(`/mapping-reviews/frameworks?policy_id=${policyId}`),
    enabled: !!policyId,
  });

  // Mapping reviews (explainability rows)
  const params = useMemo(() => {
    const p = new URLSearchParams({ policy_id: policyId });
    if (frameworkId && frameworkId !== 'all') p.set('framework_id', frameworkId);
    if (statusFilter !== 'all') p.set('status', statusFilter);
    if (confidenceTier === 'high') p.set('min_confidence', '0.8');
    else if (confidenceTier === 'medium') p.set('min_confidence', '0.5');
    return p.toString();
  }, [policyId, frameworkId, statusFilter, confidenceTier]);

  const {
    data: items = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['mappingReviews', params],
    queryFn: () => api.get(`/mapping-reviews?${params}`),
    enabled: !!policyId,
    retry: false,
  });

  // Search-filter + low-confidence-tier filter on the client
  const filtered = useMemo(() => {
    let out = items;
    if (search.trim()) {
      const s = search.toLowerCase();
      out = out.filter(it =>
        it.control_code?.toLowerCase().includes(s) ||
        it.framework_requirement?.toLowerCase().includes(s) ||
        it.policy_evidence?.toLowerCase().includes(s) ||
        it.subdomain_name?.toLowerCase().includes(s)
      );
    }
    if (confidenceTier === 'low') {
      out = out.filter(it => (it.confidence || 0) < 0.5);
    }
    return out;
  }, [items, search, confidenceTier]);

  // Scroll to the requested control once it appears in the filtered list,
  // then clear the pending target so subsequent filter changes don't snap
  // back to it.
  useEffect(() => {
    if (!pendingFocusControl || filtered.length === 0) return;
    const match = filtered.find(it => it.control_code === pendingFocusControl);
    if (!match) return;
    const node = document.querySelector(
      `[data-mapping-control="${CSS.escape(pendingFocusControl)}"]`,
    );
    if (node) {
      node.scrollIntoView({ behavior: 'smooth', block: 'center' });
      node.classList.add('ring-2', 'ring-emerald-500', 'ring-offset-2', 'rounded-lg');
      window.setTimeout(() => {
        node.classList.remove('ring-2', 'ring-emerald-500', 'ring-offset-2', 'rounded-lg');
      }, 2500);
    }
    setPendingFocusControl(null);
  }, [pendingFocusControl, filtered]);

  // Counts (over the unfiltered backend response so the totals don't change
  // when the user types a search query).
  const counts = useMemo(() => {
    const c = { compliant: 0, partial: 0, non_compliant: 0 };
    items.forEach(it => { if (c[it.status] !== undefined) c[it.status] += 1; });
    return c;
  }, [items]);

  const total = items.length;
  const score =
    total === 0
      ? null
      : Math.round(((counts.compliant + counts.partial * 0.5) / total) * 100);

  const policyName =
    policies.find(p => p.id === policyId)?.file_name || '';

  // Phase UI-1: recommended next action — drives the banner above the picker.
  const nextAction = useMemo(() => {
    if (policiesLoading) return null;
    if (policies.length === 0) {
      return {
        primary: {
          label: 'Upload your first policy',
          helper: 'Mapping Review surfaces the AI verdict per control once a policy has been analysed.',
          to: createPageUrl('Policies'),
          icon: FileText,
        },
      };
    }
    if (!policyId) {
      return {
        primary: {
          label: 'Select a policy to review',
          helper: 'Pick one from the dropdown below to see how each control was mapped to its evidence.',
          icon: GitCompare,
          onClick: () => {
            // Soft scroll: the picker is right below.
            const el = document.querySelector('[role="combobox"]');
            if (el) el.focus();
          },
        },
      };
    }
    if (isLoading) return null;
    if (items.length === 0) return null;
    const lowConf = items.filter(it => (it.confidence || 0) < 0.5).length;
    if (lowConf > 0) {
      return {
        primary: {
          label: `Review ${lowConf} low-confidence mapping${lowConf === 1 ? '' : 's'}`,
          helper: 'These are the rows the AI is least sure about — most reviewer value lives here.',
          icon: AlertTriangle,
          onClick: () => setConfidenceTier('low'),
        },
        tone: 'warning',
      };
    }
    if (counts.non_compliant > 0) {
      return {
        primary: {
          label: `Open ${counts.non_compliant} non-compliant control${counts.non_compliant === 1 ? '' : 's'} in Gaps`,
          helper: 'Each non-compliant control has been recorded as a gap with a priority score.',
          to: createPageUrl('GapsRisks') + `?policy_id=${policyId}`,
          icon: AlertTriangle,
        },
        tone: 'info',
      };
    }
    return null;
  }, [policiesLoading, policies.length, policyId, isLoading, items, counts.non_compliant]);

  // Phase UI-5: per-card "Generate draft" mutation. Backend now resolves
  // mapping_review_id for cards that have one, so the existing
  // /api/remediation/generate endpoint accepts the call. Toast + cache
  // invalidations mirror the GapsRisks inline action so flows agree.
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const generateDraftMutation = useMutation({
    mutationFn: ({ mapping_review_id, policy_id }) =>
      api.post('/remediation/generate', { mapping_review_id, policy_id }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['mappingReviews'] });
      queryClient.invalidateQueries({ queryKey: ['gaps'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
      toast({
        title: 'Draft generated',
        description:
          `Saved as draft for ${data?.control_code || 'this control'}. ` +
          `Improvement: ${data?.improvement_pct ?? 0}%.`,
      });
    },
    onError: (err) => toast({
      title: 'Could not generate draft',
      description: err.message || 'Try again in a moment.',
      variant: 'destructive',
    }),
  });

  const handleGenerateDraft = (item) => {
    if (!item?.mapping_review_id || !item?.policy_id) return;
    generateDraftMutation.mutate({
      mapping_review_id: item.mapping_review_id,
      policy_id: item.policy_id,
    });
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <TooltipProvider delayDuration={150}>
    <PageContainer
      title="Mapping Review"
      subtitle="Per-control explainability — what the framework requires, what the policy says, and how to close the gap."
    >
      {/* Phase UI-1: recommended next step (computed above) */}
      {nextAction && (
        <NextAction
          primary={nextAction.primary}
          secondary={nextAction.secondary}
          tone={nextAction.tone}
        />
      )}

      {/* Top bar: policy + framework selectors */}
      <div className="flex flex-col md:flex-row gap-3 mb-6">
        <div className="flex-1 min-w-0">
          <label className="text-xs text-muted-foreground mb-1 block">Policy</label>
          <Select value={policyId} onValueChange={setPolicyId}>
            <SelectTrigger className="w-full">
              <FileText className="w-4 h-4 mr-2 shrink-0" />
              <SelectValue placeholder={policiesLoading ? 'Loading…' : 'Select a policy…'} />
            </SelectTrigger>
            <SelectContent>
              {policies.map(p => (
                <SelectItem key={p.id} value={p.id}>{p.file_name || p.id}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="md:w-56">
          <label className="text-xs text-muted-foreground mb-1 block">Framework</label>
          <Select value={frameworkId} onValueChange={setFrameworkId} disabled={!policyId}>
            <SelectTrigger className="w-full">
              <Layers className="w-4 h-4 mr-2 shrink-0" />
              <SelectValue placeholder="All frameworks" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All frameworks</SelectItem>
              {frameworksWithResults.map(fw => (
                <SelectItem key={fw.framework_id} value={fw.framework_id}>
                  {fw.framework_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="md:w-44">
          <label className="text-xs text-muted-foreground mb-1 block">Status</label>
          <Select value={statusFilter} onValueChange={setStatusFilter} disabled={!policyId}>
            <SelectTrigger className="w-full">
              <Filter className="w-4 h-4 mr-2 shrink-0" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="compliant">Compliant</SelectItem>
              <SelectItem value="partial">Partial</SelectItem>
              <SelectItem value="non_compliant">Non-Compliant</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="md:w-44">
          <label className="text-xs text-muted-foreground mb-1 block">Confidence</label>
          <Select value={confidenceTier} onValueChange={setConfidenceTier} disabled={!policyId}>
            <SelectTrigger className="w-full">
              <Brain className="w-4 h-4 mr-2 shrink-0" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All confidence</SelectItem>
              <SelectItem value="high">High (80%+)</SelectItem>
              <SelectItem value="medium">Medium (50%+)</SelectItem>
              <SelectItem value="low">Low (&lt;50%)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {!policyId ? (
        <EmptyState
          icon={GitCompare}
          title="Select a policy to begin"
          description="Pick a policy above to see per-control explainability for the latest analysis."
        />
      ) : isError ? (
        <Card className="border-red-500/30 bg-red-500/5">
          <CardContent className="p-6 text-sm">
            <p className="font-medium text-red-700 dark:text-red-300 mb-1">
              Could not load mapping reviews
            </p>
            <p className="text-muted-foreground">
              {error?.message || 'Unknown error'}
            </p>
            <p className="text-xs text-muted-foreground mt-3">
              Run an analysis on this policy first, then return here.
            </p>
          </CardContent>
        </Card>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={GitCompare}
          title="No analysis rows yet"
          description={
            policyName
              ? `No mapping data exists for "${policyName}". Run analysis first.`
              : 'Run analysis first.'
          }
          action={() => navigate(`/Analyses?policy_id=${policyId}`)}
          actionLabel="Run analysis"
        />
      ) : (
        <>
          {/* Score + counts header */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <Card className="relative overflow-hidden shadow-sm">
              <span className="absolute left-0 top-0 h-full w-1 bg-emerald-500/80 dark:bg-emerald-400/70" />
              <CardContent className="p-4 pl-5 flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-emerald-500/10">
                  <CheckCircle2 className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
                </div>
                <div>
                  <p className="text-2xl font-bold leading-none tabular-nums">
                    {score === null ? '—' : `${score}%`}
                  </p>
                  <p className="text-sm mt-1 font-medium text-muted-foreground">
                    Compliance score
                  </p>
                </div>
              </CardContent>
            </Card>
            <StatChip
              tone="compliant"
              icon={CheckCircle2}
              value={counts.compliant}
              label="Compliant controls"
            />
            <StatChip
              tone="partial"
              icon={AlertTriangle}
              value={counts.partial}
              label="Partial controls"
            />
            <StatChip
              tone="non_compliant"
              icon={XCircle}
              value={counts.non_compliant}
              label="Non-compliant controls"
            />
          </div>

          {/* Search + jump-to-versions CTA */}
          <div className="flex flex-col sm:flex-row gap-3 mb-6">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search control code, requirement, evidence…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
            <Button
              variant="outline"
              onClick={() =>
                navigate(`/PolicyVersions?policy_id=${policyId}${frameworkId !== 'all' ? `&framework_id=${frameworkId}` : ''}`)
              }
              className="gap-1.5 sm:ml-auto"
            >
              Improve this policy
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>

          {/* Cards */}
          {filtered.length === 0 ? (
            <EmptyState
              icon={Search}
              title="No matches"
              description="Adjust the filters or search term to see more results."
            />
          ) : (
            <div className="space-y-4">
              {filtered.map(item => (
                <div
                  key={`${item.framework_id}|${item.control_code}`}
                  data-mapping-control={item.control_code}
                  className="transition-shadow"
                >
                  <ExplainabilityCard
                    item={item}
                    onGenerateDraft={handleGenerateDraft}
                    isGenerating={
                      generateDraftMutation.isPending &&
                      generateDraftMutation.variables?.mapping_review_id ===
                        item.mapping_review_id
                    }
                  />
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </PageContainer>
    </TooltipProvider>
  );
}
