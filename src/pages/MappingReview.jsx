import React, { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
import DataTable from '@/components/ui/DataTable';
import StatusBadge from '@/components/ui/StatusBadge';
import EmptyState from '@/components/ui/EmptyState';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  GitCompare, Search, Filter, CheckCircle2, XCircle, Edit,
  AlertTriangle, Eye, Brain, Save, RotateCcw, Wand2, ArrowRight,
  TrendingUp, Loader2, ExternalLink, Sparkles, ListChecks, ChevronDown,
} from 'lucide-react';
import { format } from 'date-fns';

const MappingReview = api.entities.MappingReview;
const Policy        = api.entities.Policy;

const LOADING_STEPS = [
  { icon: Brain,      text: 'Analyzing missing compliance requirements…'   },
  { icon: Wand2,      text: 'Generating targeted policy additions…'        },
  { icon: TrendingUp, text: 'Running re-analysis simulation…'              },
  { icon: Sparkles,   text: 'Calculating compliance improvement scores…'   },
];

// ─── Helper ───────────────────────────────────────────────────────────────────

/** Remove AI confidence-level markers like [High], [Medium], [Low], [Critical]. */
function cleanAiRationale(text) {
  if (!text) return '';
  return text.replace(/\[(Critical|High|Medium|Low)\]/gi, '').replace(/\s+/g, ' ').trim();
}

// ─── Auth helper ──────────────────────────────────────────────────────────────

async function authPost(url, body) {
  const token = localStorage.getItem('token');
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

// ─── Summary card ─────────────────────────────────────────────────────────────
//
// One shared card for all three top-of-page metrics. The card uses the app's
// neutral surface (bg-card / border-border) and applies the semantic color
// only as accents: a left border, a tinted icon container, and the number.
// This avoids the pale pastel blocks that read as "light-mode leftovers" in
// dark mode while keeping the meaning obvious at a glance.

const SUMMARY_TONES = {
  amber: {
    bar: 'bg-amber-500/80 dark:bg-amber-400/70',
    iconBg: 'bg-amber-100 dark:bg-amber-500/15',
    iconText: 'text-amber-600 dark:text-amber-400',
    value: 'text-amber-700 dark:text-amber-300',
    label: 'text-amber-700/80 dark:text-amber-300/80',
  },
  red: {
    bar: 'bg-red-500/80 dark:bg-red-400/70',
    iconBg: 'bg-red-100 dark:bg-red-500/15',
    iconText: 'text-red-600 dark:text-red-400',
    value: 'text-red-700 dark:text-red-300',
    label: 'text-red-700/80 dark:text-red-300/80',
  },
  emerald: {
    bar: 'bg-emerald-500/80 dark:bg-emerald-400/70',
    iconBg: 'bg-emerald-100 dark:bg-emerald-500/15',
    iconText: 'text-emerald-600 dark:text-emerald-400',
    value: 'text-emerald-700 dark:text-emerald-300',
    label: 'text-emerald-700/80 dark:text-emerald-300/80',
  },
};

function SummaryCard({ tone, icon: Icon, value, label }) {
  const t = SUMMARY_TONES[tone] || SUMMARY_TONES.amber;
  return (
    <Card className="relative overflow-hidden shadow-sm">
      {/* Accent bar — only colored hint on the chrome itself */}
      <span aria-hidden className={`absolute left-0 top-0 h-full w-1 ${t.bar}`} />
      <CardContent className="p-4 pl-5 flex items-center gap-4">
        <div
          className={`w-12 h-12 rounded-xl flex items-center justify-center ${t.iconBg}`}
        >
          <Icon className={`w-6 h-6 ${t.iconText}`} />
        </div>
        <div>
          <p className={`text-2xl font-bold leading-none ${t.value}`}>{value}</p>
          <p className={`text-sm mt-1 font-medium ${t.label}`}>{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function MappingReviewPage() {
  const [searchQuery,       setSearchQuery]       = useState('');
  const [statusFilter,      setStatusFilter]       = useState('all');
  const [confidenceFilter,  setConfidenceFilter]   = useState('all');

  // Dialog state
  const [selectedMapping,   setSelectedMapping]    = useState(null);
  const [showReviewDialog,  setShowReviewDialog]   = useState(false);
  const [reviewNotes,       setReviewNotes]        = useState('');
  const [notesError,        setNotesError]         = useState(false);

  // Modify (edit) mode
  const [isEditing,         setIsEditing]          = useState(false);
  const [editedEvidence,    setEditedEvidence]     = useState('');
  const [editedRationale,   setEditedRationale]    = useState('');

  // Remediation draft workflow  ('review' | 'generating' | 'result')
  const [draftStep,         setDraftStep]          = useState('review');
  const [draftResult,       setDraftResult]        = useState(null);
  const [draftExpanded,     setDraftExpanded]      = useState(false);
  const [loadingMsgIdx,     setLoadingMsgIdx]      = useState(0);

  const { toast }        = useToast();
  const queryClient      = useQueryClient();
  const navigate         = useNavigate();

  const urlParams      = new URLSearchParams(window.location.search);
  const policyIdFilter = urlParams.get('policy_id');

  // ── Queries ─────────────────────────────────────────────────────────────────

  const { data: mappings = [], isLoading } = useQuery({
    queryKey: ['mappingReviews'],
    queryFn: () => MappingReview.list('-created_at'),
  });

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list(),
  });

  const policyMap = policies.reduce((acc, p) => { acc[p.id] = p; return acc; }, {});

  // ── Mutations ────────────────────────────────────────────────────────────────

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['mappingReviews'] });
    queryClient.invalidateQueries({ queryKey: ['gaps'] });
    queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
  };

  /** Accept — agrees with AI's Non-Compliant assessment, auto-creates gap */
  const acceptMutation = useMutation({
    mutationFn: (id) => authPost(`/api/mappings/${id}/accept`),
    onSuccess: () => {
      invalidate();
      toast({ title: 'Mapping accepted. Gap created.' });
      closeDialog();
    },
    onError: (err) => toast({ title: 'Accept failed', description: err.message, variant: 'destructive' }),
  });

  /** Reject — overrides AI, marks as Compliant (Manual Override), no gap */
  const rejectMutation = useMutation({
    mutationFn: ({ id, notes }) =>
      authPost(`/api/mappings/${id}/reject`, { review_notes: notes }),
    onSuccess: () => {
      invalidate();
      toast({ title: 'AI rejected. Marked as Compliant.' });
      closeDialog();
    },
    onError: (err) => toast({ title: 'Reject failed', description: err.message, variant: 'destructive' }),
  });

  /** Save edits — saves modified evidence_snippet / ai_rationale via generic entity update */
  const editMutation = useMutation({
    mutationFn: ({ id, data }) => MappingReview.update(id, data),
    onSuccess: () => {
      invalidate();
      toast({ title: 'Changes saved.' });
      setIsEditing(false);
    },
    onError: (err) => toast({ title: 'Save failed', description: err.message, variant: 'destructive' }),
  });

  /** Accept & Generate Draft — calls POST /api/remediation/generate */
  const generateDraftMutation = useMutation({
    mutationFn: ({ mapping_review_id, policy_id, control_id, framework_name, ai_rationale }) =>
      authPost('/api/remediation/generate', {
        // Required by the backend Pydantic schema:
        mapping_review_id: mapping_review_id || null,
        policy_id,
        // Supplementary context — the backend resolves FK IDs from the mapping
        // review row itself. Send null (not "") so the server never receives an
        // empty string that could propagate into a FK column.
        control_id:     control_id     || null,
        framework_name: framework_name || null,
        ai_rationale:   ai_rationale   || null,
      }),
    onSuccess: (data) => {
      setDraftResult(data);
      setDraftStep('result');
      setDraftExpanded(false);
      invalidate();
    },
    onError: (err) => {
      // Always reset to 'review' so the dialog is interactive again.
      setDraftStep('review');
      toast({
        title: 'Draft generation failed',
        description: err.message || 'The server could not generate a remediation draft. Please try again.',
        variant: 'destructive',
      });
    },
  });

  // Cycle loading messages while generating
  useEffect(() => {
    if (draftStep !== 'generating') return;
    const id = setInterval(() => setLoadingMsgIdx(i => (i + 1) % LOADING_STEPS.length), 2800);
    return () => clearInterval(id);
  }, [draftStep]);

  // ── Handlers ─────────────────────────────────────────────────────────────────

  const openDialog = (mapping) => {
    setSelectedMapping(mapping);
    setReviewNotes(mapping.review_notes || '');
    setNotesError(false);
    setIsEditing(false);
    setEditedEvidence(mapping.evidence_snippet || '');
    setEditedRationale(mapping.ai_rationale || '');
    setShowReviewDialog(true);
  };

  const closeDialog = () => {
    setShowReviewDialog(false);
    setIsEditing(false);
    setNotesError(false);
    setDraftStep('review');
    setDraftResult(null);
    setLoadingMsgIdx(0);
  };

  const handleAccept = () => {
    acceptMutation.mutate(selectedMapping.id);
  };

  const handleAcceptAndGenerate = () => {
    setDraftStep('generating');
    setLoadingMsgIdx(0);
    generateDraftMutation.mutate({
      mapping_review_id: selectedMapping.id         || null,
      policy_id:         selectedMapping.policy_id,
      // The entity endpoint returns the control code string under 'control_id'
      // and the framework name (not UUID) under 'framework'.
      // Use null (not "") so empty values never reach FK columns as bad strings.
      control_id:     selectedMapping.control_id   || null,
      framework_name: selectedMapping.framework    || null,
      ai_rationale:   selectedMapping.ai_rationale || null,
    });
  };

  const handleReject = () => {
    if (!reviewNotes.trim()) {
      setNotesError(true);
      toast({
        title: 'Justification required to override AI',
        description: 'Please provide review notes before rejecting.',
        variant: 'destructive',
      });
      return;
    }
    setNotesError(false);
    rejectMutation.mutate({ id: selectedMapping.id, notes: reviewNotes.trim() });
  };

  const handleModify = () => {
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditedEvidence(selectedMapping.evidence_snippet || '');
    setEditedRationale(selectedMapping.ai_rationale || '');
  };

  const handleSaveEdits = () => {
    editMutation.mutate({
      id: selectedMapping.id,
      data: {
        evidence_snippet: editedEvidence,
        ai_rationale: editedRationale,
        decision: 'Modified',
      },
    });
  };

  // ── Derived data ──────────────────────────────────────────────────────────────

  const filteredMappings = mappings.filter(mapping => {
    const matchesSearch =
      mapping.control_id?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      mapping.evidence_snippet?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus     = statusFilter === 'all' || mapping.decision === statusFilter;
    const cs                = mapping.confidence_score || 0;
    const matchesConfidence = confidenceFilter === 'all' ||
      (confidenceFilter === 'needs_review' && cs < 0.5) ||
      (confidenceFilter === 'low'          && cs >= 0.5 && cs < 0.8) ||
      (confidenceFilter === 'high'         && cs >= 0.8);
    const matchesPolicyId   = !policyIdFilter || mapping.policy_id === policyIdFilter;
    return matchesSearch && matchesStatus && matchesConfidence && matchesPolicyId;
  });

  const pendingCount       = mappings.filter(m => m.decision === 'Pending').length;
  const lowConfidenceCount = mappings.filter(m => (m.confidence_score || 0) < 0.5).length;
  const acceptedCount      = mappings.filter(m => m.decision === 'Accepted').length;

  // Tinted, dark-mode-aware confidence chips. Same semantic meaning as
  // before, but the dark variants use translucent tints (bg-color/15) so
  // they stop looking like pale-mode leftovers on a dark surface.
  const getConfidenceBadge = (score) => {
    if (score >= 0.8) {
      return {
        color:
          'text-emerald-700 bg-emerald-50 border border-emerald-200 ' +
          'dark:text-emerald-300 dark:bg-emerald-500/15 dark:border-emerald-500/30',
        label: 'High',
      };
    }
    if (score >= 0.5) {
      return {
        color:
          'text-amber-700 bg-amber-50 border border-amber-200 ' +
          'dark:text-amber-300 dark:bg-amber-500/15 dark:border-amber-500/30',
        label: 'Medium',
      };
    }
    return {
      color:
        'text-red-700 bg-red-50 border border-red-200 ' +
        'dark:text-red-300 dark:bg-red-500/15 dark:border-red-500/30',
      label: 'Low',
    };
  };

  const isPending = ['Pending', 'Flagged'].includes(selectedMapping?.decision);
  const isBusy    = acceptMutation.isPending || rejectMutation.isPending
                    || editMutation.isPending || generateDraftMutation.isPending;

  // ── Table columns ─────────────────────────────────────────────────────────────

  const columns = [
    {
      header: 'Control ID',
      accessor: 'control_id',
      cell: (row) => (
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="font-mono text-xs">{row.control_id}</Badge>
          {(row.confidence_score || 0) < 0.5 && (
            <AlertTriangle className="w-4 h-4 text-amber-500" />
          )}
        </div>
      ),
    },
    {
      header: 'Framework',
      accessor: 'framework',
      cell: (row) => (
        <Badge className="bg-muted text-foreground border border-border/60 hover:bg-muted">{row.framework}</Badge>
      ),
    },
    {
      header: 'Evidence Snippet',
      accessor: 'evidence_snippet',
      cell: (row) => (
        <p className="text-sm text-muted-foreground line-clamp-2 max-w-md">
          {row.evidence_snippet || 'No evidence available'}
        </p>
      ),
    },
    {
      header: 'Confidence',
      accessor: 'confidence_score',
      cell: (row) => {
        const score = row.confidence_score || 0;
        const badge = getConfidenceBadge(score);
        return (
          <div className={`inline-flex items-center gap-1 px-2 py-1 rounded ${badge.color}`}>
            <span className="text-sm font-medium">{badge.label}</span>
            <span className="text-xs opacity-75">{Math.round(score * 100)}%</span>
          </div>
        );
      },
    },
    {
      header: 'Decision',
      accessor: 'decision',
      cell: (row) => <StatusBadge status={row.decision || 'Pending'} />,
    },
    {
      header: '',
      accessor: 'actions',
      cell: (row) => (
        <Button variant="ghost" size="sm" onClick={() => openDialog(row)}>
          {row.decision === 'Pending' ? (
            <><Edit className="w-4 h-4 mr-1" />Review</>
          ) : (
            <><Eye className="w-4 h-4 mr-1" />View</>
          )}
        </Button>
      ),
    },
  ];

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <PageContainer
      title="Mapping Review"
      subtitle="Human-in-the-loop validation of AI-generated control mappings"
    >
      {/* Stats — semantic accents on a shared dark/light surface */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <SummaryCard
          tone="amber"
          icon={AlertTriangle}
          value={pendingCount}
          label="Pending Reviews"
        />
        <SummaryCard
          tone="red"
          icon={Brain}
          value={lowConfidenceCount}
          label="Needs Review"
        />
        <SummaryCard
          tone="emerald"
          icon={CheckCircle2}
          value={acceptedCount}
          label="Accepted"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by control ID or evidence..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Decision" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Decisions</SelectItem>
            <SelectItem value="Pending">Pending</SelectItem>
            <SelectItem value="Accepted">Accepted</SelectItem>
            <SelectItem value="Rejected">Rejected</SelectItem>
            <SelectItem value="Modified">Modified</SelectItem>
          </SelectContent>
        </Select>
        <Select value={confidenceFilter} onValueChange={setConfidenceFilter}>
          <SelectTrigger className="w-40">
            <Brain className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Confidence" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Confidence</SelectItem>
            <SelectItem value="needs_review">Needs Review (&lt;50%)</SelectItem>
            <SelectItem value="low">Medium (50-80%)</SelectItem>
            <SelectItem value="high">High (80%+)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={filteredMappings}
        isLoading={isLoading}
        emptyState={
          <EmptyState
            icon={GitCompare}
            title="No mappings to review"
            description="Run a compliance analysis to generate control mappings for review"
          />
        }
      />

      {/* ── Review Dialog ──────────────────────────────────────────────────────── */}
      <Dialog open={showReviewDialog} onOpenChange={closeDialog}>
        <DialogContent
          className={`max-h-[90vh] overflow-y-auto transition-all ${
            draftStep === 'result' ? 'sm:max-w-3xl' : 'sm:max-w-2xl'
          }`}
        >
          {/* ── STEP: generating ─────────────────────────────────────────── */}
          {draftStep === 'generating' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Wand2 className="w-5 h-5 text-emerald-500" />
                  Generating Remediation Draft
                </DialogTitle>
                <DialogDescription>
                  AI is analyzing the gap and writing targeted policy additions…
                </DialogDescription>
              </DialogHeader>

              <div className="flex flex-col items-center justify-center gap-6 py-10">
                {/* Pulsing ring */}
                <div className="relative flex items-center justify-center">
                  <div className="absolute w-20 h-20 rounded-full border-4 border-emerald-500/20 animate-ping" />
                  <div className="absolute w-16 h-16 rounded-full border-4 border-emerald-500/30 animate-ping [animation-delay:300ms]" />
                  <div className="relative w-12 h-12 rounded-full bg-emerald-500/15 border-2 border-emerald-500/40 flex items-center justify-center">
                    <Loader2 className="w-6 h-6 text-emerald-500 animate-spin" />
                  </div>
                </div>

                {/* Cycling message */}
                <div className="text-center space-y-1">
                  {(() => {
                    const step = LOADING_STEPS[loadingMsgIdx];
                    const Icon = step.icon;
                    return (
                      <>
                        <div className="flex items-center justify-center gap-2 text-foreground font-medium">
                          <Icon className="w-4 h-4 text-emerald-500" />
                          <span>{step.text}</span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          This usually takes 30–60 seconds. Please wait.
                        </p>
                      </>
                    );
                  })()}
                </div>

                {/* Progress steps */}
                <div className="flex gap-1.5">
                  {LOADING_STEPS.map((_, i) => (
                    <div
                      key={i}
                      className={`h-1 rounded-full transition-all duration-500 ${
                        i <= loadingMsgIdx
                          ? 'w-6 bg-emerald-500'
                          : 'w-3 bg-muted'
                      }`}
                    />
                  ))}
                </div>
              </div>
            </>
          )}

          {/* ── STEP: result ─────────────────────────────────────────────── */}
          {draftStep === 'result' && draftResult && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-emerald-500" />
                  Remediation Draft Ready
                </DialogTitle>
                <DialogDescription>
                  AI generated targeted policy additions. Review the improvement below.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-5 py-2">
                {/* Score improvement banner */}
                <div className="rounded-xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/8 to-teal-500/5 p-5">
                  <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 mb-4 flex items-center gap-1.5">
                    <TrendingUp className="w-3.5 h-3.5" />
                    Compliance Score Projection
                  </p>
                  <div className="flex items-center justify-center gap-6">
                    {/* Before */}
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground mb-1">Before</p>
                      <p className="text-4xl font-black text-red-500 dark:text-red-400 tabular-nums">
                        {draftResult.old_score}
                        <span className="text-2xl font-bold">%</span>
                      </p>
                    </div>

                    {/* Arrow + delta */}
                    <div className="flex flex-col items-center gap-1">
                      <ArrowRight className="w-7 h-7 text-emerald-500" />
                      <span className={`text-sm font-bold px-2 py-0.5 rounded-full ${
                        draftResult.improvement_pct >= 0
                          ? 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/15'
                          : 'text-red-600 bg-red-500/15'
                      }`}>
                        {draftResult.improvement_pct >= 0 ? '+' : ''}{draftResult.improvement_pct}%
                      </span>
                    </div>

                    {/* After */}
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground mb-1">After Draft</p>
                      <p className="text-4xl font-black text-emerald-600 dark:text-emerald-400 tabular-nums">
                        {draftResult.new_score}
                        <span className="text-2xl font-bold">%</span>
                      </p>
                    </div>
                  </div>

                  {/* Checkpoint summary */}
                  <div className="mt-4 pt-4 border-t border-emerald-500/20 flex items-center justify-center gap-1.5 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    <span className="font-semibold text-emerald-700 dark:text-emerald-300">
                      {draftResult.checkpoints_fixed}
                    </span>
                    <span className="text-muted-foreground">
                      of {draftResult.checkpoints_total} missing requirements now addressed
                    </span>
                  </div>
                </div>

                {/* Section headers */}
                {draftResult.section_headers?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">
                      <ListChecks className="w-3.5 h-3.5" />
                      New Sections Generated
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {draftResult.section_headers.map((h, i) => (
                        <span
                          key={i}
                          className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-emerald-700 dark:text-emerald-300 font-medium"
                        >
                          {h}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Draft text preview (collapsible) */}
                <div className="border border-border rounded-xl overflow-hidden">
                  <button
                    onClick={() => setDraftExpanded(v => !v)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-muted/30 hover:bg-muted/50 transition-colors text-sm font-medium"
                  >
                    <span className="flex items-center gap-2">
                      <Brain className="w-4 h-4 text-muted-foreground" />
                      AI-Generated Policy Addition
                    </span>
                    <ChevronDown
                      className={`w-4 h-4 text-muted-foreground transition-transform ${draftExpanded ? 'rotate-180' : ''}`}
                    />
                  </button>
                  {draftExpanded && (
                    <div className="p-4 bg-muted/10 max-h-64 overflow-y-auto">
                      <pre className="text-xs font-mono text-foreground/85 whitespace-pre-wrap break-words leading-relaxed">
                        {draftResult.suggested_policy_text}
                      </pre>
                    </div>
                  )}
                </div>

                {/* Per-checkpoint breakdown */}
                {draftResult.checkpoint_details?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">
                      <ListChecks className="w-3.5 h-3.5" />
                      Checkpoint Breakdown
                    </p>
                    <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                      {draftResult.checkpoint_details.map((cp, i) => (
                        <div
                          key={i}
                          className={`flex items-start gap-2.5 p-2.5 rounded-lg text-xs border ${
                            cp.is_now_met
                              ? 'bg-emerald-500/8 border-emerald-500/20'
                              : 'bg-muted/30 border-border/60'
                          }`}
                        >
                          {cp.is_now_met
                            ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mt-0.5 shrink-0" />
                            : <XCircle className="w-3.5 h-3.5 text-muted-foreground mt-0.5 shrink-0" />
                          }
                          <span className={cp.is_now_met ? 'text-emerald-800 dark:text-emerald-200' : 'text-muted-foreground'}>
                            {cp.requirement}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Result footer */}
              <div className="flex items-center justify-between pt-2 border-t border-border/60 mt-2 gap-2 flex-wrap">
                <Button variant="outline" onClick={closeDialog}>
                  Close
                </Button>
                <Button
                  onClick={() => {
                    closeDialog();
                    navigate(
                      `/PolicyVersions?policy_id=${selectedMapping.policy_id}&draft_id=${draftResult.draft_id}`
                    );
                  }}
                  className="bg-emerald-600 hover:bg-emerald-700 gap-1.5"
                >
                  <ExternalLink className="w-4 h-4" />
                  View Full Diff &amp; Manage Draft
                </Button>
              </div>
            </>
          )}

          {/* ── STEP: review (normal UI) ──────────────────────────────────── */}
          {draftStep === 'review' && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <GitCompare className="w-5 h-5 text-emerald-600" />
                  {isPending ? 'Review Mapping' : 'Mapping Details'}
                </DialogTitle>
                <DialogDescription>
                  {isPending
                    ? 'Accept, reject, or modify the AI-generated control mapping.'
                    : `Decision: ${selectedMapping?.decision}`}
                </DialogDescription>
              </DialogHeader>

              {selectedMapping && (
                <div className="space-y-5 py-2">
                  {/* Low-confidence warning */}
                  {(selectedMapping.confidence_score || 0) < 0.5 && (
                    <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg dark:bg-amber-500/10 dark:border-amber-500/30">
                      <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="font-medium text-amber-800 dark:text-amber-200">Needs Review — Low Confidence</p>
                        <p className="text-sm text-amber-700 dark:text-amber-200/90">
                          The AI found ambiguous or conflicting evidence. Please review carefully.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Meta */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Control ID</p>
                      <Badge variant="outline" className="font-mono">
                        {selectedMapping.control_id}
                      </Badge>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Framework</p>
                      <Badge className="bg-muted text-foreground border border-border/60 hover:bg-muted">{selectedMapping.framework}</Badge>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Confidence</p>
                      {(() => {
                        const s = selectedMapping.confidence_score || 0;
                        const b = getConfidenceBadge(s);
                        return (
                          <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded ${b.color}`}>
                            <span className="font-medium">{b.label}</span>
                            <span className="text-sm opacity-75">{Math.round(s * 100)}%</span>
                          </div>
                        );
                      })()}
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Policy</p>
                      <p className="text-sm font-medium">
                        {policyMap[selectedMapping.policy_id]?.file_name || selectedMapping.policy_id}
                      </p>
                    </div>
                  </div>

                  {/* Evidence */}
                  <div>
                    <p className="text-xs text-muted-foreground mb-1.5">Evidence Snippet</p>
                    {isEditing ? (
                      <Textarea
                        value={editedEvidence}
                        onChange={(e) => setEditedEvidence(e.target.value)}
                        rows={4}
                        className="text-sm"
                      />
                    ) : (
                      <div className="bg-muted/50 border border-border rounded-lg p-4">
                        <p className="text-sm text-foreground/90 italic">
                          "{selectedMapping.evidence_snippet || 'No evidence available'}"
                        </p>
                      </div>
                    )}
                  </div>

                  {/* AI Rationale */}
                  {(selectedMapping.ai_rationale || isEditing) && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1.5 flex items-center gap-1">
                        <Brain className="w-3.5 h-3.5" />
                        AI Rationale
                        {!isEditing && (
                          <span className="text-[10px] text-muted-foreground/70 ml-1">
                            ({cleanAiRationale(selectedMapping.ai_rationale) !== selectedMapping.ai_rationale
                              ? 'cleaned'
                              : 'raw'})
                          </span>
                        )}
                      </p>
                      {isEditing ? (
                        <Textarea
                          value={editedRationale}
                          onChange={(e) => setEditedRationale(e.target.value)}
                          rows={4}
                          className="text-sm"
                        />
                      ) : (
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 dark:bg-blue-500/10 dark:border-blue-500/30">
                          <p className="text-sm text-blue-700 dark:text-blue-300">
                            {cleanAiRationale(selectedMapping.ai_rationale)}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Review Notes — shown when not in edit mode */}
                  {!isEditing && (
                    <div>
                      <Label className={notesError ? 'text-red-600' : ''}>
                        Review Notes
                        {isPending && (
                          <span className="text-muted-foreground font-normal ml-1">
                            (required when rejecting)
                          </span>
                        )}
                      </Label>
                      <Textarea
                        placeholder="Add justification for your decision…"
                        value={reviewNotes}
                        onChange={(e) => { setReviewNotes(e.target.value); if (e.target.value.trim()) setNotesError(false); }}
                        rows={3}
                        className={`mt-1.5 ${notesError ? 'border-red-400 focus:border-red-500 focus:ring-red-200' : ''}`}
                        disabled={!isPending}
                      />
                      {notesError && (
                        <p className="text-xs text-red-600 mt-1 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" />
                          Justification is required to override the AI assessment.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* ── Action buttons ──────────────────────────────────────────── */}
              <div className="flex items-center justify-between pt-2 border-t border-border/60 mt-2">
                {isEditing ? (
                  <div className="flex gap-2 ml-auto">
                    <Button variant="outline" onClick={handleCancelEdit} disabled={isBusy}>
                      <RotateCcw className="w-4 h-4 mr-1" />
                      Cancel
                    </Button>
                    <Button
                      onClick={handleSaveEdits}
                      disabled={isBusy}
                      className="bg-purple-600 hover:bg-purple-700"
                    >
                      <Save className="w-4 h-4 mr-1" />
                      {editMutation.isPending ? 'Saving…' : 'Save Changes'}
                    </Button>
                  </div>
                ) : isPending ? (
                  <div className="flex items-center gap-2 w-full flex-wrap">
                    <Button variant="outline" onClick={closeDialog} className="mr-auto">
                      Cancel
                    </Button>
                    <Button
                      onClick={handleModify}
                      disabled={isBusy}
                      className="bg-purple-600 hover:bg-purple-700"
                    >
                      <Edit className="w-4 h-4 mr-1" />
                      Modify
                    </Button>
                    <Button
                      onClick={handleReject}
                      disabled={isBusy}
                      className="bg-red-600 hover:bg-red-700"
                    >
                      <XCircle className="w-4 h-4 mr-1" />
                      {rejectMutation.isPending ? 'Rejecting…' : 'Reject'}
                    </Button>
                    {/* Plain accept — agree with AI without generating a draft */}
                    <Button
                      onClick={handleAccept}
                      disabled={isBusy}
                      variant="outline"
                      className="border-emerald-500/50 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/10"
                    >
                      <CheckCircle2 className="w-4 h-4 mr-1" />
                      {acceptMutation.isPending ? 'Accepting…' : 'Accept'}
                    </Button>
                    {/* Primary CTA: accept + generate AI draft */}
                    <Button
                      onClick={handleAcceptAndGenerate}
                      disabled={isBusy}
                      className="bg-emerald-600 hover:bg-emerald-700 gap-1.5"
                    >
                      <Wand2 className="w-4 h-4" />
                      Accept &amp; Generate Draft
                    </Button>
                  </div>
                ) : (
                  <Button variant="outline" onClick={closeDialog} className="ml-auto">
                    Close
                  </Button>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
