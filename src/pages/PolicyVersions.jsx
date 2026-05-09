// @ts-nocheck
import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import {
  GitFork, CheckCircle2, XCircle, AlertTriangle, FileText, Loader2,
  Sparkles, Wand2, Download, ListChecks, RefreshCw, ArrowLeft,
  Shield, ScrollText, FileDown, TrendingUp, TrendingDown, ArrowRight,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import PageContainer from '@/components/layout/PageContainer';
import EmptyState from '@/components/ui/EmptyState';
import { api } from '@/api/apiClient';

// ── API helpers ───────────────────────────────────────────────────────────────

const token = () => localStorage.getItem('token');

async function authFetch(url) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token()}` } });
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(e.detail || 'Request failed');
  }
  return res.json();
}

async function authPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(e.detail || 'Request failed');
  }
  return res.json();
}

/**
 * Download a binary stream from the API and trigger a browser save dialog.
 * Resolves on success, throws on a non-2xx so the caller can show an error toast.
 * The default filename is read from the Content-Disposition header.
 */
async function authDownloadPdf(url, fallbackName) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token()}` } });
  if (!res.ok) {
    let detail = 'PDF generation failed. Please try again.';
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === 'string' ? j.detail : detail;
    } catch { /* not JSON */ }
    throw new Error(detail);
  }
  const blob = await res.blob();
  // Parse Content-Disposition: attachment; filename="..."
  const cd = res.headers.get('Content-Disposition') || '';
  const m = cd.match(/filename="?([^";]+)"?/i);
  const filename = (m && m[1]) || fallbackName || 'policy.pdf';

  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(objectUrl);
}

// ── Status visual config ──────────────────────────────────────────────────────

const VERSION_TYPE_META = {
  original: {
    label: 'Original',
    icon: ScrollText,
    chip: 'text-muted-foreground bg-muted/60 border-border',
  },
  ai_remediated: {
    label: 'AI-Remediated',
    icon: Sparkles,
    chip: 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/15 border-emerald-500/30',
  },
  ai_draft: {
    label: 'AI Draft',
    icon: Wand2,
    chip: 'text-blue-700 dark:text-blue-300 bg-blue-500/15 border-blue-500/30',
  },
  final: {
    label: 'Final',
    icon: CheckCircle2,
    chip: 'text-purple-700 dark:text-purple-300 bg-purple-500/15 border-purple-500/30',
  },
};

function VersionTypeBadge({ type }) {
  const meta = VERSION_TYPE_META[type] || VERSION_TYPE_META.original;
  const Icon = meta.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${meta.chip}`}>
      <Icon className="w-3 h-3" />
      {meta.label}
    </span>
  );
}

// ── Generation modal ──────────────────────────────────────────────────────────

const LOADING_STEPS = [
  'Loading partial and non-compliant controls…',
  'Building consolidated remediation request…',
  'Generating improved policy sections via AI…',
  'Saving AI-remediated version…',
  'Re-analyzing improved version…',
  'Calculating new compliance score…',
];

function GenerateImprovedDialog({
  open, onClose, policyId, frameworkId, onSuccess,
}) {
  const [step, setStep] = useState('confirm');     // confirm | running | done
  const [stepIdx, setStepIdx] = useState(0);
  const [result, setResult] = useState(null);
  const [pdfDownloading, setPdfDownloading] = useState(false);
  const { toast } = useToast();

  const mutation = useMutation({
    mutationFn: (body) => authPost('/api/policy-versions/generate', body),
    onSuccess: (data) => {
      setResult(data);
      setStep('done');
      toast({ title: 'Improved version saved.' });
      onSuccess?.(data);
    },
    onError: (e) => {
      setStep('confirm');
      toast({ title: 'Generation failed', description: e.message, variant: 'destructive' });
    },
  });

  useEffect(() => {
    if (step !== 'running') return;
    const id = setInterval(() => setStepIdx(i => (i + 1) % LOADING_STEPS.length), 1800);
    return () => clearInterval(id);
  }, [step]);

  const handleGenerate = () => {
    setStep('running');
    setStepIdx(0);
    mutation.mutate({
      policy_id: policyId,
      framework_id: frameworkId && frameworkId !== 'all' ? frameworkId : null,
    });
  };

  const handleClose = () => {
    setStep('confirm');
    setStepIdx(0);
    setResult(null);
    setPdfDownloading(false);
    onClose();
  };

  const handleDownloadPdf = async () => {
    if (!result?.version_id) return;
    setPdfDownloading(true);
    try {
      await authDownloadPdf(
        `/api/policies/${policyId}/versions/${result.version_id}/download/pdf`,
        `ai_remediated_policy_v${result.version_number}.pdf`,
      );
      toast({ title: 'PDF downloaded.' });
    } catch (e) {
      toast({
        title: 'PDF generation failed. Please try again.',
        description: e.message,
        variant: 'destructive',
      });
    } finally {
      setPdfDownloading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        {step === 'confirm' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Wand2 className="w-5 h-5 text-emerald-500" />
                Generate Improved Policy Version
              </DialogTitle>
              <DialogDescription>
                Create a new <span className="font-medium">ai_remediated</span> version of this
                policy that addresses every partial and non-compliant control found in the
                latest analysis. The original policy file is never modified.
              </DialogDescription>
            </DialogHeader>
            <ul className="text-sm text-foreground/85 space-y-2 py-2">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                Pulls all partial / non-compliant findings from the most recent analysis.
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                Generates targeted policy sections for the missing requirements only.
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                Saves a new version in <span className="font-mono">policy_versions</span>.
              </li>
            </ul>
            <div className="flex justify-end gap-2 pt-2 border-t border-border/60">
              <Button variant="outline" onClick={handleClose}>Cancel</Button>
              <Button onClick={handleGenerate} className="bg-emerald-600 hover:bg-emerald-700 gap-1.5">
                <Wand2 className="w-4 h-4" />
                Generate
              </Button>
            </div>
          </>
        )}

        {step === 'running' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Loader2 className="w-5 h-5 animate-spin text-emerald-500" />
                Generating improved version
              </DialogTitle>
              <DialogDescription>{LOADING_STEPS[stepIdx]}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-col items-center justify-center py-8 gap-3">
              <div className="flex gap-1.5">
                {LOADING_STEPS.map((_, i) => (
                  <div
                    key={i}
                    className={`h-1 rounded-full transition-all duration-500 ${
                      i <= stepIdx ? 'w-6 bg-emerald-500' : 'w-3 bg-muted'
                    }`}
                  />
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                This usually takes 30–90 seconds.
              </p>
            </div>
          </>
        )}

        {step === 'done' && result && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-emerald-500" />
                Improved version created
              </DialogTitle>
              <DialogDescription>
                New <span className="font-mono">ai_remediated</span> version saved and
                re-analyzed. Results are based on actual compliance analysis.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3 py-2">

              {/* Score comparison */}
              <div className="rounded-xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/8 to-teal-500/5 p-4">
                <p className="text-xs uppercase font-semibold text-emerald-700 dark:text-emerald-300 mb-3 flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5" />
                  Overall Compliance Score
                </p>
                <div className="flex items-center justify-center gap-5">
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">Before</p>
                    <p className="text-3xl font-black text-muted-foreground tabular-nums">
                      {result.original_score}<span className="text-xl">%</span>
                    </p>
                  </div>
                  <ArrowRight className="w-5 h-5 text-emerald-500 shrink-0" />
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground mb-1">After</p>
                    <p className="text-4xl font-black text-emerald-600 dark:text-emerald-400 tabular-nums">
                      {result.new_score}<span className="text-2xl">%</span>
                    </p>
                  </div>
                  <span className={`text-sm font-bold px-2.5 py-1 rounded-full flex items-center gap-1 ${
                    result.improvement_delta > 0
                      ? 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/15'
                      : result.improvement_delta === 0
                      ? 'text-muted-foreground bg-muted/50'
                      : 'text-red-700 dark:text-red-300 bg-red-500/15'
                  }`}>
                    {result.improvement_delta > 0 && <TrendingUp className="w-3.5 h-3.5" />}
                    {result.improvement_delta < 0 && <TrendingDown className="w-3.5 h-3.5" />}
                    {result.improvement_delta > 0 ? '+' : ''}{result.improvement_delta}%
                  </span>
                </div>
              </div>

              {/* Remediation stats */}
              <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-4">
                <p className="text-xs uppercase font-semibold text-blue-700 dark:text-blue-300 mb-3 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Remediation Results
                </p>
                <div className="grid grid-cols-3 gap-2 text-center mb-3">
                  <div className="rounded-lg bg-muted/30 py-2">
                    <p className="text-2xl font-black tabular-nums">{result.total_targeted}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Targeted</p>
                  </div>
                  <div className="rounded-lg bg-emerald-500/10 py-2">
                    <p className="text-2xl font-black text-emerald-600 dark:text-emerald-400 tabular-nums">{result.fixed_controls}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Fixed</p>
                  </div>
                  <div className="rounded-lg bg-amber-500/10 py-2">
                    <p className="text-2xl font-black text-amber-600 dark:text-amber-400 tabular-nums">
                      {result.still_partial + result.still_non_compliant}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">Remaining</p>
                  </div>
                </div>
                <div className="flex items-center justify-between text-xs px-0.5 mb-1.5">
                  <span className="text-muted-foreground">Remediation success rate</span>
                  <span className="font-bold text-blue-700 dark:text-blue-300">{result.remediation_score}%</span>
                </div>
                <div className="w-full bg-muted/40 rounded-full h-1.5">
                  <div className="bg-blue-500 h-1.5 rounded-full" style={{ width: `${result.remediation_score}%` }} />
                </div>
              </div>

              {/* Addressed controls */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-1.5">
                  Controls targeted ({result.addressed_controls.length})
                </p>
                <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                  {result.addressed_controls.map((c, i) => (
                    <Badge key={i} variant="outline" className="font-mono text-xs">
                      {c}
                    </Badge>
                  ))}
                </div>
              </div>

            </div>

            <div className="flex flex-wrap justify-end gap-2 pt-2 border-t border-border/60">
              <Button variant="outline" onClick={handleClose}>Close</Button>
              <Button
                onClick={handleDownloadPdf}
                disabled={pdfDownloading}
                className="bg-emerald-600 hover:bg-emerald-700 gap-1.5"
              >
                {pdfDownloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
                {pdfDownloading ? 'Preparing PDF…' : 'Download PDF'}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PolicyVersions() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const initialPolicyId = searchParams.get('policy_id') || '';
  const initialFrameworkId = searchParams.get('framework_id') || 'all';

  const [policyId, setPolicyId] = useState(initialPolicyId);
  const [frameworkId, setFrameworkId] = useState(initialFrameworkId);
  const [showGenerate, setShowGenerate] = useState(false);
  const [openVersionId, setOpenVersionId] = useState(null);

  // Sync to URL
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (policyId) next.set('policy_id', policyId); else next.delete('policy_id');
    if (frameworkId && frameworkId !== 'all') next.set('framework_id', frameworkId);
    else next.delete('framework_id');
    setSearchParams(next, { replace: true });
  }, [policyId, frameworkId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Policies
  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => api.entities.Policy.list(),
  });

  // Frameworks with results for this policy
  const { data: frameworksWithResults = [] } = useQuery({
    queryKey: ['mappingFrameworks', policyId],
    queryFn: () => authFetch(`/api/mapping-reviews/frameworks?policy_id=${policyId}`),
    enabled: !!policyId,
  });

  // Mapping items for the partial / non-compliant summary (uses the same
  // explainability endpoint to stay consistent with Mapping Review).
  const explainParams = useMemo(() => {
    if (!policyId) return null;
    const p = new URLSearchParams({ policy_id: policyId });
    if (frameworkId && frameworkId !== 'all') p.set('framework_id', frameworkId);
    return p.toString();
  }, [policyId, frameworkId]);

  const { data: mappingItems = [], isLoading: loadingItems } = useQuery({
    queryKey: ['mappingReviews', explainParams],
    queryFn: () => authFetch(`/api/mapping-reviews?${explainParams}`),
    enabled: !!explainParams,
    retry: false,
  });

  // Versions
  const {
    data: versions = [],
    isLoading: loadingVersions,
  } = useQuery({
    queryKey: ['policyVersions', policyId],
    queryFn: () => authFetch(`/api/policy-versions?policy_id=${policyId}`),
    enabled: !!policyId,
    retry: false,
  });

  const counts = useMemo(() => {
    const c = { compliant: 0, partial: 0, non_compliant: 0 };
    mappingItems.forEach(it => { if (c[it.status] !== undefined) c[it.status] += 1; });
    return c;
  }, [mappingItems]);

  const total = mappingItems.length;
  const score =
    total === 0 ? null : Math.round(((counts.compliant + counts.partial * 0.5) / total) * 100);

  const partialNonCompliant = useMemo(
    () => mappingItems.filter(it => it.status !== 'compliant'),
    [mappingItems],
  );

  const policyName = policies.find(p => p.id === policyId)?.file_name || '';

  const handleGenerationSuccess = () => {
    queryClient.invalidateQueries({ queryKey: ['policyVersions', policyId] });
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <PageContainer
      title="Policy Versions"
      subtitle="Generate AI-remediated versions of a policy and track its full version history."
    >
      {/* Top bar */}
      <div className="flex flex-col md:flex-row gap-3 mb-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate(`/MappingReview${policyId ? `?policy_id=${policyId}` : ''}`)}
          className="gap-1.5 self-start"
        >
          <ArrowLeft className="w-4 h-4" />
          Mapping Review
        </Button>

        <div className="flex-1 min-w-0">
          <Select value={policyId} onValueChange={setPolicyId}>
            <SelectTrigger className="w-full">
              <FileText className="w-4 h-4 mr-2 shrink-0" />
              <SelectValue placeholder="Select a policy…" />
            </SelectTrigger>
            <SelectContent>
              {policies.map(p => (
                <SelectItem key={p.id} value={p.id}>{p.file_name || p.id}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="md:w-56">
          <Select
            value={frameworkId}
            onValueChange={setFrameworkId}
            disabled={!policyId}
          >
            <SelectTrigger className="w-full">
              <Shield className="w-4 h-4 mr-2 shrink-0" />
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
      </div>

      {!policyId ? (
        <EmptyState
          icon={GitFork}
          title="Select a policy"
          description="Choose a policy above to view its compliance status, generate an improved version, and browse version history."
        />
      ) : (
        <div className="space-y-6">
          {/* Compliance overview */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card>
              <CardContent className="p-5">
                <p className="text-xs uppercase font-semibold text-muted-foreground mb-1.5">
                  Latest score
                </p>
                <p className="text-3xl font-black tabular-nums">
                  {score === null ? '—' : `${score}%`}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {total > 0 ? `${total} controls assessed` : 'No analysis yet'}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-5">
                <p className="text-xs uppercase font-semibold text-emerald-700 dark:text-emerald-400 mb-1.5">
                  Compliant
                </p>
                <p className="text-3xl font-black text-emerald-600 dark:text-emerald-400 tabular-nums">
                  {counts.compliant}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-5">
                <p className="text-xs uppercase font-semibold text-amber-700 dark:text-amber-400 mb-1.5">
                  Partial
                </p>
                <p className="text-3xl font-black text-amber-600 dark:text-amber-400 tabular-nums">
                  {counts.partial}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-5">
                <p className="text-xs uppercase font-semibold text-red-700 dark:text-red-400 mb-1.5">
                  Non-compliant
                </p>
                <p className="text-3xl font-black text-red-600 dark:text-red-400 tabular-nums">
                  {counts.non_compliant}
                </p>
              </CardContent>
            </Card>
          </div>

          {total === 0 && !loadingItems ? (
            <Card className="border-amber-500/30 bg-amber-500/5">
              <CardContent className="p-5 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-amber-800 dark:text-amber-200">
                    Run analysis first
                  </p>
                  <p className="text-sm text-amber-700/90 dark:text-amber-200/80 mb-3">
                    No analysis results found for this policy. Run an analysis so the
                    AI remediation has something to work with.
                  </p>
                  <Button
                    size="sm"
                    onClick={() => navigate(`/Analyses?policy_id=${policyId}`)}
                  >
                    Go to Analyses
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Generate CTA */}
              <Card className="border-emerald-500/30 bg-gradient-to-br from-emerald-500/5 to-teal-500/5">
                <CardContent className="p-5 flex flex-col md:flex-row md:items-center gap-4 justify-between">
                  <div>
                    <p className="font-semibold text-foreground flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-emerald-500" />
                      Generate an improved version of "{policyName}"
                    </p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Builds a new version that targets all {partialNonCompliant.length}{' '}
                      partial / non-compliant control(s). Original policy stays untouched.
                    </p>
                  </div>
                  <Button
                    onClick={() => setShowGenerate(true)}
                    disabled={partialNonCompliant.length === 0}
                    className="bg-emerald-600 hover:bg-emerald-700 gap-1.5"
                  >
                    <Wand2 className="w-4 h-4" />
                    Generate Improved Policy Version
                  </Button>
                </CardContent>
              </Card>

              {/* Findings to remediate */}
              {partialNonCompliant.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <ListChecks className="w-4 h-4 text-amber-500" />
                      What will be remediated ({partialNonCompliant.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <div className="max-h-64 overflow-y-auto pr-1 space-y-1.5">
                      {partialNonCompliant.map(item => (
                        <div
                          key={`${item.framework_id}|${item.control_code}`}
                          className="flex items-start gap-2.5 text-xs p-2.5 rounded-lg border border-border/60 bg-muted/20"
                        >
                          {item.status === 'partial' ? (
                            <AlertTriangle className="w-3.5 h-3.5 text-amber-500 mt-0.5 shrink-0" />
                          ) : (
                            <XCircle className="w-3.5 h-3.5 text-red-500 mt-0.5 shrink-0" />
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-0.5">
                              <span className="font-mono text-[10px] font-semibold">
                                {item.framework_name} · {item.control_code}
                              </span>
                              <span className="text-[10px] uppercase text-muted-foreground">
                                {item.status === 'partial' ? 'Partial' : 'Non-Compliant'}
                              </span>
                            </div>
                            <p className="text-foreground/80 line-clamp-2">
                              {item.framework_requirement}
                            </p>
                            {item.missing_requirements?.length > 0 && (
                              <p className="text-muted-foreground mt-0.5 text-[10px]">
                                {item.missing_requirements.length} missing requirement(s)
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}

          {/* Version history */}
          <Card>
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <CardTitle className="text-sm flex items-center gap-2">
                <GitFork className="w-4 h-4 text-emerald-500" />
                Version history
              </CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => queryClient.invalidateQueries({ queryKey: ['policyVersions', policyId] })}
              >
                <RefreshCw className="w-3.5 h-3.5 mr-1" />
                Refresh
              </Button>
            </CardHeader>
            <CardContent className="pt-0">
              {loadingVersions ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-emerald-500" />
                </div>
              ) : versions.length === 0 ? (
                <div className="text-sm text-muted-foreground py-6 text-center">
                  No versions yet. Generate an improved version above to start the history.
                </div>
              ) : (
                <div className="space-y-1.5">
                  {versions.map(v => (
                    <button
                      key={v.id}
                      onClick={() => setOpenVersionId(v.id)}
                      className="w-full text-left p-3.5 rounded-lg border border-border bg-card hover:border-emerald-500/40 hover:bg-muted/30 transition-all"
                    >
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="font-mono text-xs font-semibold">v{v.version_number}</span>
                        <VersionTypeBadge type={v.version_type} />
                        {v.compliance_score !== null && v.compliance_score !== undefined && (
                          <span className="text-xs text-muted-foreground">
                            est. {Math.round(v.compliance_score)}%
                          </span>
                        )}
                        <span className="text-xs text-muted-foreground ml-auto">
                          {v.created_at
                            ? format(new Date(v.created_at), 'MMM d, yyyy • HH:mm')
                            : '—'}
                        </span>
                      </div>
                      {v.change_summary && (
                        <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2">
                          {v.change_summary}
                        </p>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <GenerateImprovedDialog
        open={showGenerate}
        onClose={() => setShowGenerate(false)}
        policyId={policyId}
        frameworkId={frameworkId}
        onSuccess={handleGenerationSuccess}
      />

      {openVersionId && (
        <VersionDetailDialog
          versionId={openVersionId}
          policyId={policyId}
          onClose={() => setOpenVersionId(null)}
          onReanalysisDone={() => {
            queryClient.invalidateQueries({ queryKey: ['policyVersions', policyId] });
            queryClient.invalidateQueries({ queryKey: ['mappingReviews'] });
            queryClient.invalidateQueries({ queryKey: ['mappingFrameworks', policyId] });
            queryClient.invalidateQueries({ queryKey: ['policies'] });
          }}
        />
      )}
    </PageContainer>
  );
}

// ── Version detail (view + Download PDF + Re-run analysis) ────────────────────

function VersionDetailDialog({ versionId, policyId, onClose, onReanalysisDone }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [pdfDownloading, setPdfDownloading] = useState(false);
  const [reanalysisResult, setReanalysisResult] = useState(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['policyVersion', versionId],
    queryFn: () => authFetch(`/api/policy-versions/${versionId}`),
    enabled: !!versionId,
  });

  const reanalyzeMutation = useMutation({
    mutationFn: () =>
      authPost(
        `/api/policies/${policyId}/versions/${versionId}/reanalyze`,
        {},
      ),
    onSuccess: (res) => {
      setReanalysisResult(res);
      // Refresh the version row so its compliance_score updates inline.
      queryClient.invalidateQueries({ queryKey: ['policyVersion', versionId] });
      onReanalysisDone?.();
      toast({ title: `Re-analysis complete · ${res.new_overall_score}% overall (was ${res.original_overall_score}%)` });
    },
    onError: (e) =>
      toast({
        title: 'Re-analysis failed. Please try again.',
        description: e.message,
        variant: 'destructive',
      }),
  });

  const handleDownloadText = () => {
    if (!data?.content) return;
    const blob = new Blob([data.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `policy-v${data.version_number}-${data.version_type}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadPdf = async () => {
    if (!data) return;
    setPdfDownloading(true);
    try {
      const fallback =
        data.version_type === 'ai_remediated'
          ? `ai_remediated_policy_v${data.version_number}.pdf`
          : `policy_v${data.version_number}_${data.version_type}.pdf`;
      await authDownloadPdf(
        `/api/policies/${policyId}/versions/${versionId}/download/pdf`,
        fallback,
      );
      toast({ title: 'PDF downloaded.' });
    } catch (e) {
      toast({
        title: 'PDF generation failed. Please try again.',
        description: e.message,
        variant: 'destructive',
      });
    } finally {
      setPdfDownloading(false);
    }
  };

  const handleClose = () => {
    if (reanalyzeMutation.isPending) return;     // guard close while running
    setReanalysisResult(null);
    onClose();
  };

  const reanalyzing = reanalyzeMutation.isPending;

  return (
    <>
      <Dialog open onOpenChange={handleClose}>
        <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ScrollText className="w-5 h-5 text-emerald-500" />
              {data ? `Version ${data.version_number}` : 'Loading…'}
              {data && <VersionTypeBadge type={data.version_type} />}
            </DialogTitle>
            <DialogDescription>
              {data?.change_summary || 'Version details'}
            </DialogDescription>
          </DialogHeader>

          {isLoading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
            </div>
          ) : error ? (
            <div className="text-sm text-red-500 py-4">
              Failed to load version: {error.message}
            </div>
          ) : data ? (
            <div className="space-y-3">
              <div className="border border-border rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-3 py-2 bg-muted/40 border-b border-border text-xs gap-2 flex-wrap">
                  <span className="font-medium">
                    Content ({data.content?.length || 0} chars)
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={handleDownloadText}
                      disabled={reanalyzing}
                    >
                      <Download className="w-3.5 h-3.5 mr-1" />
                      Download .txt
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={handleDownloadPdf}
                      disabled={pdfDownloading || reanalyzing}
                      className="text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/10"
                    >
                      {pdfDownloading ? (
                        <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                      ) : (
                        <FileDown className="w-3.5 h-3.5 mr-1" />
                      )}
                      {pdfDownloading ? 'Preparing PDF…' : 'Download PDF'}
                    </Button>
                  </div>
                </div>
                <pre className="text-xs font-mono text-foreground/85 whitespace-pre-wrap break-words leading-relaxed p-4 max-h-[55vh] overflow-y-auto">
                  {data.content}
                </pre>
              </div>

              {/* Inline re-analysis loading banner */}
              {reanalyzing && (
                <div className="flex items-center gap-3 p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/8">
                  <Loader2 className="w-4 h-4 animate-spin text-emerald-500 shrink-0" />
                  <div className="text-xs">
                    <p className="font-medium text-emerald-800 dark:text-emerald-200">
                      Re-running analysis on this remediated version…
                    </p>
                    <p className="text-emerald-700/80 dark:text-emerald-200/80">
                      The original policy file is not modified. This typically takes
                      a few minutes.
                    </p>
                  </div>
                </div>
              )}

              <div className="flex flex-wrap justify-end gap-2 pt-2 border-t border-border/60">
                <Button
                  variant="outline"
                  onClick={handleClose}
                  disabled={reanalyzing}
                >
                  Close
                </Button>
                <Button
                  variant="outline"
                  onClick={handleDownloadPdf}
                  disabled={pdfDownloading || reanalyzing}
                  className="gap-1.5"
                >
                  {pdfDownloading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <FileDown className="w-4 h-4" />
                  )}
                  {pdfDownloading ? 'Preparing PDF…' : 'Download PDF'}
                </Button>
                <Button
                  onClick={() => reanalyzeMutation.mutate()}
                  disabled={reanalyzing}
                  className="bg-emerald-600 hover:bg-emerald-700 gap-1.5"
                >
                  {reanalyzing ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <RefreshCw className="w-4 h-4" />
                  )}
                  {reanalyzing ? 'Re-running analysis…' : 'Re-run analysis'}
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Re-analysis result modal */}
      {reanalysisResult && (
        <ReanalysisResultDialog
          result={reanalysisResult}
          policyId={policyId}
          versionId={versionId}
          versionNumber={data?.version_number}
          versionType={data?.version_type}
          onClose={() => setReanalysisResult(null)}
        />
      )}
    </>
  );
}

// ── Re-analysis result modal ──────────────────────────────────────────────────

function ReanalysisResultDialog({
  result, policyId, versionId, versionNumber, versionType, onClose,
}) {
  const { toast } = useToast();
  const [pdfDownloading, setPdfDownloading] = useState(false);

  const deltaPositive = result.overall_delta > 0;
  const deltaZero     = result.overall_delta === 0;

  const handleDownloadPdf = async () => {
    setPdfDownloading(true);
    try {
      const fallback =
        versionType === 'ai_remediated'
          ? `ai_remediated_policy_v${versionNumber}.pdf`
          : `policy_v${versionNumber}_${versionType}.pdf`;
      await authDownloadPdf(
        `/api/policies/${policyId}/versions/${versionId}/download/pdf`,
        fallback,
      );
      toast({ title: 'PDF downloaded.' });
    } catch (e) {
      toast({
        title: 'PDF generation failed. Please try again.',
        description: e.message,
        variant: 'destructive',
      });
    } finally {
      setPdfDownloading(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-emerald-500" />
            Re-analysis complete
          </DialogTitle>
          <DialogDescription>
            Targeted {result.targeted_controls} previously flagged controls.
            Compliant controls were preserved.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">

          {/* ── Section 1: Overall Compliance Score ── */}
          <div className="rounded-xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/8 to-teal-500/5 p-4">
            <p className="text-xs uppercase font-semibold text-emerald-700 dark:text-emerald-300 mb-3 flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5" />
              Overall Compliance Score
            </p>
            <div className="flex items-center justify-center gap-5">
              <div className="text-center">
                <p className="text-xs text-muted-foreground mb-1">Before</p>
                <p className="text-3xl font-black text-muted-foreground tabular-nums">
                  {result.original_overall_score}<span className="text-xl">%</span>
                </p>
              </div>
              <ArrowRight className="w-5 h-5 text-emerald-500 shrink-0" />
              <div className="text-center">
                <p className="text-xs text-muted-foreground mb-1">After</p>
                <p className="text-4xl font-black text-emerald-600 dark:text-emerald-400 tabular-nums">
                  {result.new_overall_score}<span className="text-2xl">%</span>
                </p>
              </div>
              <span className={`text-sm font-bold px-2.5 py-1 rounded-full flex items-center gap-1 ${
                deltaPositive ? 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/15'
                : deltaZero   ? 'text-muted-foreground bg-muted/50'
                :               'text-red-700 dark:text-red-300 bg-red-500/15'
              }`}>
                {deltaPositive && <TrendingUp className="w-3.5 h-3.5" />}
                {!deltaPositive && !deltaZero && <TrendingDown className="w-3.5 h-3.5" />}
                {deltaPositive ? '+' : ''}{result.overall_delta}%
              </span>
            </div>
            <p className="text-xs text-muted-foreground text-center mt-2">
              Based on all {result.total_controls} framework controls · {result.duration_seconds}s
            </p>
          </div>

          {/* ── Section 2: Remediation Results ── */}
          <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-4">
            <p className="text-xs uppercase font-semibold text-blue-700 dark:text-blue-300 mb-3 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Remediation Results
            </p>
            <div className="grid grid-cols-3 gap-2 text-center mb-3">
              <div className="rounded-lg bg-muted/30 py-2">
                <p className="text-2xl font-black text-foreground tabular-nums">{result.targeted_controls}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Targeted</p>
              </div>
              <div className="rounded-lg bg-emerald-500/10 py-2">
                <p className="text-2xl font-black text-emerald-600 dark:text-emerald-400 tabular-nums">{result.fixed_controls}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Fixed</p>
              </div>
              <div className="rounded-lg bg-amber-500/10 py-2">
                <p className="text-2xl font-black text-amber-600 dark:text-amber-400 tabular-nums">
                  {result.still_partial + result.still_non_compliant}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">Remaining</p>
              </div>
            </div>
            <div className="flex items-center justify-between text-xs px-0.5 mb-1.5">
              <span className="text-muted-foreground">Remediation success rate</span>
              <span className="font-bold text-blue-700 dark:text-blue-300 tabular-nums">{result.remediation_score}%</span>
            </div>
            <div className="w-full bg-muted/40 rounded-full h-1.5">
              <div
                className="bg-blue-500 h-1.5 rounded-full transition-all"
                style={{ width: `${result.remediation_score}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground text-center mt-2">
              Of the {result.targeted_controls} previously partial or non-compliant controls
            </p>
          </div>

          {/* ── Section 3: Per-framework breakdown ── */}
          {result.frameworks?.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs uppercase font-semibold text-muted-foreground">
                Frameworks Analyzed
              </p>
              {result.frameworks.map((fw) => (
                <div key={fw.framework_id} className="p-3 rounded-lg border border-border bg-muted/20 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <Shield className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span className="font-mono text-xs font-semibold truncate">{fw.framework_id}</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs tabular-nums">
                      <span className="text-muted-foreground line-through">{fw.original_score}%</span>
                      <ArrowRight className="w-3 h-3 text-muted-foreground" />
                      <span className="font-bold text-foreground">{fw.new_score}%</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-xs tabular-nums">
                    <span className="text-emerald-600 dark:text-emerald-400">✓ {fw.new_compliant}</span>
                    <span className="text-amber-600 dark:text-amber-400">~ {fw.new_partial}</span>
                    <span className="text-red-600 dark:text-red-400">✗ {fw.new_non_compliant}</span>
                    <span className="text-muted-foreground">/ {fw.total_controls}</span>
                  </div>
                  {fw.targeted_controls > 0 && (
                    <p className="text-xs text-muted-foreground border-t border-border/50 pt-1.5">
                      Fixed {fw.fixed_controls}/{fw.targeted_controls} targeted controls ({fw.remediation_score}% success)
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

        </div>

        <div className="flex flex-wrap justify-end gap-2 pt-2 border-t border-border/60">
          <Button variant="outline" onClick={onClose}>Close</Button>
          <Button
            onClick={handleDownloadPdf}
            disabled={pdfDownloading}
            className="bg-emerald-600 hover:bg-emerald-700 gap-1.5"
          >
            {pdfDownloading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FileDown className="w-4 h-4" />
            )}
            {pdfDownloading ? 'Preparing PDF…' : 'Download PDF'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
