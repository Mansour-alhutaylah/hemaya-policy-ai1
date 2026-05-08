import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import {
  GitFork, TrendingUp, Clock, CheckCircle2, XCircle, AlertTriangle,
  ChevronRight, FileText, Eye, ThumbsUp, ThumbsDown, Loader2,
  ArrowLeft, Layers, Sparkles,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import PageContainer from '@/components/layout/PageContainer';
import EmptyState from '@/components/ui/EmptyState';
import DiffViewer from '@/components/DiffViewer';
import RemediationExplainability from '@/components/RemediationExplainability';

// ── API helpers ───────────────────────────────────────────────────────────────

const token = () => localStorage.getItem('token');

async function apiFetch(url) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token()}` } });
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(e.detail || 'Request failed');
  }
  return res.json();
}

async function apiPatch(url, body) {
  const res = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(e.detail || 'Request failed');
  }
  return res.json();
}

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS = {
  draft:        { label: 'Draft',        color: 'text-amber-600 dark:text-amber-400  bg-amber-500/10  border-amber-500/30', icon: Clock },
  under_review: { label: 'Under Review', color: 'text-blue-600  dark:text-blue-400   bg-blue-500/10   border-blue-500/30',  icon: Eye   },
  approved:     { label: 'Approved',     color: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/30', icon: CheckCircle2 },
  rejected:     { label: 'Rejected',     color: 'text-red-600   dark:text-red-400    bg-red-500/10    border-red-500/30',   icon: XCircle },
  superseded:   { label: 'Superseded',   color: 'text-muted-foreground bg-muted/50 border-border',                          icon: GitFork },
};

function StatusChip({ status }) {
  const cfg = STATUS[status] || STATUS.draft;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.color}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

// ── Score bar ─────────────────────────────────────────────────────────────────

function ScoreBar({ label, value, color }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-semibold">{value}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${Math.min(100, value)}%` }}
        />
      </div>
    </div>
  );
}

// ── Draft card ────────────────────────────────────────────────────────────────

function DraftCard({ draft, isSelected, onClick }) {
  const ts = draft.created_at
    ? format(new Date(draft.created_at), 'MMM d, yyyy • HH:mm')
    : '—';

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-xl border transition-all duration-150 ${
        isSelected
          ? 'border-emerald-500/60 bg-emerald-500/5 dark:bg-emerald-500/8 shadow-sm'
          : 'border-border bg-card hover:border-border/80 hover:bg-muted/30'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-mono text-xs font-semibold text-foreground/80">
              {draft.control_code || 'Unknown Control'}
            </span>
            <StatusChip status={draft.remediation_status} />
          </div>
          <p className="text-xs text-muted-foreground truncate">
            {draft.control_title || draft.framework_name || '—'}
          </p>
          {draft.section_headers?.length > 0 && (
            <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 truncate">
              {draft.section_headers.slice(0, 2).join(' · ')}
              {draft.section_headers.length > 2 && ` +${draft.section_headers.length - 2} more`}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <ChevronRight className={`w-4 h-4 transition-transform ${isSelected ? 'rotate-90 text-emerald-500' : 'text-muted-foreground'}`} />
          <span className="text-[10px] text-muted-foreground">{ts}</span>
        </div>
      </div>
    </button>
  );
}

// ── Review modal ──────────────────────────────────────────────────────────────

function ReviewModal({ draft, onClose, onSuccess }) {
  const [action, setAction]   = useState(null);  // 'approve' | 'reject'
  const [notes, setNotes]     = useState('');
  const [notesErr, setNotesErr] = useState(false);
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: ({ status, notes }) =>
      apiPatch(`/api/remediation/drafts/${draft.id}`, {
        remediation_status: status,
        review_notes: notes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remediationDrafts'] });
      toast({ title: action === 'approve' ? 'Draft approved.' : 'Draft rejected.' });
      onSuccess();
    },
    onError: (e) => toast({ title: 'Action failed', description: e.message, variant: 'destructive' }),
  });

  const handleSubmit = () => {
    if (action === 'reject' && !notes.trim()) {
      setNotesErr(true);
      return;
    }
    mutation.mutate({ status: action === 'approve' ? 'approved' : 'rejected', notes });
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-emerald-600" />
            Review Draft — {draft.control_code}
          </DialogTitle>
          <DialogDescription>
            Approve to promote this draft to your policy. Reject to discard it.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Action selection */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setAction('approve')}
              className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all ${
                action === 'approve'
                  ? 'border-emerald-500 bg-emerald-500/10'
                  : 'border-border hover:border-emerald-500/50'
              }`}
            >
              <ThumbsUp className={`w-6 h-6 ${action === 'approve' ? 'text-emerald-500' : 'text-muted-foreground'}`} />
              <span className="text-sm font-medium">Approve</span>
            </button>
            <button
              onClick={() => setAction('reject')}
              className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all ${
                action === 'reject'
                  ? 'border-red-500 bg-red-500/10'
                  : 'border-border hover:border-red-500/50'
              }`}
            >
              <ThumbsDown className={`w-6 h-6 ${action === 'reject' ? 'text-red-500' : 'text-muted-foreground'}`} />
              <span className="text-sm font-medium">Reject</span>
            </button>
          </div>

          <div>
            <label className={`text-xs font-medium mb-1.5 block ${notesErr ? 'text-red-500' : 'text-muted-foreground'}`}>
              Review Notes {action === 'reject' && <span className="text-red-500">*</span>}
            </label>
            <Textarea
              placeholder="Explain your decision…"
              value={notes}
              onChange={(e) => { setNotes(e.target.value); if (e.target.value.trim()) setNotesErr(false); }}
              rows={3}
              className={notesErr ? 'border-red-400' : ''}
            />
            {notesErr && (
              <p className="text-xs text-red-500 mt-1">Notes are required when rejecting.</p>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-1 border-t border-border/60">
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            disabled={!action || mutation.isPending}
            className={
              action === 'approve' ? 'bg-emerald-600 hover:bg-emerald-700' :
              action === 'reject'  ? 'bg-red-600 hover:bg-red-700' :
              ''
            }
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            {mutation.isPending ? 'Saving…' : action ? `Confirm ${action === 'approve' ? 'Approval' : 'Rejection'}` : 'Select action'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Detail panel ──────────────────────────────────────────────────────────────

function DraftDetail({ draftId, policyName, onReview }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['draftDetail', draftId],
    queryFn: () => apiFetch(`/api/remediation/drafts/${draftId}`),
    enabled: !!draftId,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
          <p className="text-sm">Loading draft…</p>
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-red-500 text-sm">
        Failed to load draft: {error.message}
      </div>
    );
  }
  if (!data) return null;

  const mergedText = data.original_policy_text
    ? `${data.original_policy_text}\n\n${data.suggested_policy_text}`
    : data.suggested_policy_text;

  const canReview = ['draft', 'under_review'].includes(data.remediation_status);

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-sm font-bold">{data.control_code || '—'}</span>
            <StatusChip status={data.remediation_status} />
          </div>
          <p className="text-xs text-muted-foreground">
            {data.framework_name} · {data.control_title}
          </p>
        </div>
        {canReview && (
          <Button
            size="sm"
            onClick={onReview}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            <CheckCircle2 className="w-4 h-4 mr-1.5" />
            Review & Decide
          </Button>
        )}
      </div>

      {/* Missing requirements */}
      {data.missing_requirements?.length > 0 && (
        <Card className="border-amber-500/20 bg-amber-500/5">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-xs font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              Requirements This Draft Addresses ({data.missing_requirements.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <ul className="space-y-1">
              {data.missing_requirements.map((req, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-amber-800 dark:text-amber-300">
                  <span className="mt-0.5 shrink-0 w-4 h-4 rounded-full bg-amber-500/20 flex items-center justify-center text-[10px] font-bold">
                    {i + 1}
                  </span>
                  {req}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Section headers generated */}
      {data.section_headers?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-emerald-500" />
            New Policy Sections Generated
          </p>
          <div className="flex flex-wrap gap-2">
            {data.section_headers.map((h, i) => (
              <span key={i} className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-emerald-700 dark:text-emerald-300 font-medium">
                {h}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* AI Rationale */}
      {data.ai_rationale && (
        <div className="p-3.5 bg-blue-500/8 border border-blue-500/20 rounded-xl">
          <p className="text-xs font-semibold text-blue-600 dark:text-blue-400 mb-1.5">AI Rationale</p>
          <p className="text-xs text-blue-800 dark:text-blue-300/90 leading-relaxed">{data.ai_rationale}</p>
        </div>
      )}

      {/* Explainability — why this draft was suggested */}
      <RemediationExplainability data={data} />

      {/* Side-by-side diff */}
      <div>
        <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">
          <GitFork className="w-3.5 h-3.5" />
          Policy Diff — Before vs. With Draft Applied
        </p>
        <DiffViewer
          oldText={data.original_policy_text || '(no original text on record)'}
          newText={mergedText}
          oldLabel="Original Policy"
          newLabel="Policy + AI Draft"
          height={500}
        />
      </div>

      {/* Review notes if already decided */}
      {data.review_notes && (
        <div className="p-3.5 bg-muted/40 border border-border rounded-xl">
          <p className="text-xs font-semibold text-muted-foreground mb-1">Review Notes</p>
          <p className="text-xs text-foreground/80">{data.review_notes}</p>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PolicyVersions() {
  const [searchParams]    = useSearchParams();
  const navigate          = useNavigate();
  const { toast }         = useToast();

  const urlPolicyId  = searchParams.get('policy_id');
  const urlDraftId   = searchParams.get('draft_id');

  const [policyId,   setPolicyId]   = useState(urlPolicyId || '');
  const [selectedId, setSelectedId] = useState(urlDraftId || null);
  const [showReview, setShowReview] = useState(false);

  // Policy list for selector
  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => apiFetch('/api/entities/Policy?limit=50'),
  });

  // Draft list for selected policy.
  // Uses the path-param endpoint /api/remediation/policies/{id}/drafts.
  // retry:false ensures isLoading flips to false immediately on any error
  // (including 404) instead of retrying 3× and leaving the spinner alive.
  const {
    data: drafts = [],
    isLoading,
    isError: draftsError,
  } = useQuery({
    queryKey: ['remediationDrafts', policyId],
    queryFn: () => apiFetch(`/api/remediation/policies/${policyId}/drafts`),
    enabled: !!policyId,
    retry: false,
  });

  const selectedDraft = drafts.find(d => d.id === selectedId) || null;

  const handlePolicyChange = (pid) => {
    setPolicyId(pid);
    setSelectedId(null);
  };

  return (
    <PageContainer
      title="Policy Versions"
      subtitle="Review AI-generated remediation drafts and track policy version history"
    >
      {/* Top bar */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/MappingReview')}
          className="gap-1.5"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Mapping Review
        </Button>

        <div className="ml-auto">
          <Select value={policyId} onValueChange={handlePolicyChange}>
            <SelectTrigger className="w-64">
              <FileText className="w-4 h-4 mr-2 shrink-0" />
              <SelectValue placeholder="Select a policy…" />
            </SelectTrigger>
            <SelectContent>
              {policies.map(p => (
                <SelectItem key={p.id} value={p.id}>
                  {p.file_name || p.id}
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
          description="Choose a policy above to view its AI remediation drafts and version history."
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 items-start">
          {/* Left: draft list */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1 mb-3">
              Remediation Drafts ({drafts.length})
            </p>

            {isLoading ? (
              // isLoading is false as soon as the query settles (data OR error).
              // retry:false above guarantees this never spins indefinitely.
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
              </div>
            ) : draftsError ? (
              <div className="text-center py-12 text-sm text-red-500/80 border border-dashed border-red-500/30 rounded-xl">
                Could not load drafts for this policy.
                <br />
                <span className="text-xs opacity-70">
                  The policy may not have been analysed yet, or a server error occurred.
                </span>
              </div>
            ) : drafts.length === 0 ? (
              <div className="text-center py-12 text-sm text-muted-foreground border border-dashed border-border rounded-xl">
                No drafts generated yet for this policy.
                <br />
                <span className="text-xs opacity-70">
                  Go to Mapping Review and click "Accept &amp; Generate Draft".
                </span>
              </div>
            ) : (
              drafts.map(d => (
                <DraftCard
                  key={d.id}
                  draft={d}
                  isSelected={d.id === selectedId}
                  onClick={() => setSelectedId(d.id)}
                />
              ))
            )}
          </div>

          {/* Right: detail + diff */}
          <div>
            {selectedId ? (
              <Card className="border-border/60">
                <CardContent className="p-5">
                  <DraftDetail
                    key={selectedId}
                    draftId={selectedId}
                    policyName={policies.find(p => p.id === policyId)?.file_name}
                    onReview={() => setShowReview(true)}
                  />
                </CardContent>
              </Card>
            ) : (
              <div className="flex items-center justify-center h-64 border border-dashed border-border rounded-xl text-muted-foreground text-sm">
                Select a draft on the left to view its diff
              </div>
            )}
          </div>
        </div>
      )}

      {/* Review modal */}
      {showReview && selectedDraft && (
        <ReviewModal
          draft={selectedDraft}
          onClose={() => setShowReview(false)}
          onSuccess={() => { setShowReview(false); setSelectedId(null); }}
        />
      )}
    </PageContainer>
  );
}
