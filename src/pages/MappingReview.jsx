import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
  GitCompare,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  Edit,
  AlertTriangle,
  Eye,
  Brain,
  Save,
  RotateCcw,
} from 'lucide-react';
import { format } from 'date-fns';

const MappingReview = api.entities.MappingReview;
const Policy        = api.entities.Policy;

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

  const { toast }        = useToast();
  const queryClient      = useQueryClient();

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
  };

  const handleAccept = () => {
    acceptMutation.mutate(selectedMapping.id);
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

  const getConfidenceBadge = (score) => {
    if (score >= 0.8) return { color: 'text-emerald-600 bg-emerald-50', label: 'High' };
    if (score >= 0.5) return { color: 'text-amber-600 bg-amber-50',   label: 'Medium' };
    return              { color: 'text-red-600 bg-red-50',             label: 'Low' };
  };

  const isPending = selectedMapping?.decision === 'Pending';
  const isBusy    = acceptMutation.isPending || rejectMutation.isPending || editMutation.isPending;

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
        <Badge className="bg-slate-100 text-slate-700">{row.framework}</Badge>
      ),
    },
    {
      header: 'Evidence Snippet',
      accessor: 'evidence_snippet',
      cell: (row) => (
        <p className="text-sm text-slate-600 line-clamp-2 max-w-md">
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
      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card className="bg-amber-50 border-amber-200">
          <CardContent className="p-4 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center">
              <AlertTriangle className="w-6 h-6 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-amber-700">{pendingCount}</p>
              <p className="text-sm text-amber-600">Pending Reviews</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-red-50 border-red-200">
          <CardContent className="p-4 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-red-100 flex items-center justify-center">
              <Brain className="w-6 h-6 text-red-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-red-700">{lowConfidenceCount}</p>
              <p className="text-sm text-red-600">Needs Review</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-emerald-50 border-emerald-200">
          <CardContent className="p-4 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-emerald-100 flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6 text-emerald-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-emerald-700">{acceptedCount}</p>
              <p className="text-sm text-emerald-600">Accepted</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
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
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
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
                <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                  <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="font-medium text-amber-800">Needs Review — Low Confidence</p>
                    <p className="text-sm text-amber-700">
                      The AI found ambiguous or conflicting evidence. Please review carefully.
                    </p>
                  </div>
                </div>
              )}

              {/* Meta */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-slate-500 mb-1">Control ID</p>
                  <Badge variant="outline" className="font-mono">
                    {selectedMapping.control_id}
                  </Badge>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Framework</p>
                  <Badge className="bg-slate-100 text-slate-700">{selectedMapping.framework}</Badge>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Confidence</p>
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
                  <p className="text-xs text-slate-500 mb-1">Policy</p>
                  <p className="text-sm font-medium">
                    {policyMap[selectedMapping.policy_id]?.file_name || selectedMapping.policy_id}
                  </p>
                </div>
              </div>

              {/* Evidence */}
              <div>
                <p className="text-xs text-slate-500 mb-1.5">Evidence Snippet</p>
                {isEditing ? (
                  <Textarea
                    value={editedEvidence}
                    onChange={(e) => setEditedEvidence(e.target.value)}
                    rows={4}
                    className="text-sm"
                  />
                ) : (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                    <p className="text-sm text-slate-700 italic">
                      "{selectedMapping.evidence_snippet || 'No evidence available'}"
                    </p>
                  </div>
                )}
              </div>

              {/* AI Rationale */}
              {(selectedMapping.ai_rationale || isEditing) && (
                <div>
                  <p className="text-xs text-slate-500 mb-1.5 flex items-center gap-1">
                    <Brain className="w-3.5 h-3.5" />
                    AI Rationale
                    {!isEditing && (
                      <span className="text-[10px] text-slate-400 ml-1">
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
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                      <p className="text-sm text-blue-700">
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
                      <span className="text-slate-400 font-normal ml-1">
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

          {/* ── Action buttons ──────────────────────────────────────────────── */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-100 mt-2">

            {isEditing ? (
              /* Edit mode footer */
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
              /* Pending review footer */
              <div className="flex items-center gap-2 w-full">
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
                <Button
                  onClick={handleAccept}
                  disabled={isBusy}
                  className="bg-emerald-600 hover:bg-emerald-700"
                >
                  <CheckCircle2 className="w-4 h-4 mr-1" />
                  {acceptMutation.isPending ? 'Accepting…' : 'Accept'}
                </Button>
              </div>
            ) : (
              /* Read-only view footer */
              <Button variant="outline" onClick={closeDialog} className="ml-auto">
                Close
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
