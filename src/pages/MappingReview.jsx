import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import PageContainer from '@/components/layout/PageContainer';
import DataTable from '@/components/ui/DataTable';
import StatusBadge from '@/components/ui/StatusBadge';
import EmptyState from '@/components/ui/EmptyState';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
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
  FileText
} from 'lucide-react';
import { format } from 'date-fns';

const MappingReview = base44.entities.MappingReview;
const Policy = base44.entities.Policy;
const AuditLog = base44.entities.AuditLog;

const CONFIDENCE_THRESHOLD = 0.6;

export default function MappingReviewPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [confidenceFilter, setConfidenceFilter] = useState('all');
  const [selectedMapping, setSelectedMapping] = useState(null);
  const [showReviewDialog, setShowReviewDialog] = useState(false);
  const [reviewDecision, setReviewDecision] = useState('');
  const [reviewNotes, setReviewNotes] = useState('');

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const urlParams = new URLSearchParams(window.location.search);
  const policyIdFilter = urlParams.get('policy_id');

  const { data: mappings = [], isLoading } = useQuery({
    queryKey: ['mappingReviews'],
    queryFn: () => MappingReview.list('-created_date'),
  });

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list(),
  });

  const policyMap = policies.reduce((acc, p) => {
    acc[p.id] = p;
    return acc;
  }, {});

  const updateMappingMutation = useMutation({
    mutationFn: ({ id, data }) => MappingReview.update(id, data),
    onSuccess: async (_, variables) => {
      queryClient.invalidateQueries(['mappingReviews']);
      await AuditLog.create({
        actor: 'Current User',
        action: 'mapping_review',
        target_type: 'mapping',
        target_id: variables.id,
        details: `Reviewed mapping with decision: ${variables.data.decision}`,
      });
      toast({
        title: 'Review Saved',
        description: 'Your review decision has been recorded.',
      });
      setShowReviewDialog(false);
    },
  });

  const filteredMappings = mappings.filter(mapping => {
    const matchesSearch = mapping.control_id?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      mapping.evidence_snippet?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || mapping.decision === statusFilter;
    const matchesConfidence = confidenceFilter === 'all' || 
      (confidenceFilter === 'low' && (mapping.confidence_score || 0) < CONFIDENCE_THRESHOLD) ||
      (confidenceFilter === 'high' && (mapping.confidence_score || 0) >= CONFIDENCE_THRESHOLD);
    const matchesPolicyId = !policyIdFilter || mapping.policy_id === policyIdFilter;
    return matchesSearch && matchesStatus && matchesConfidence && matchesPolicyId;
  });

  const pendingCount = mappings.filter(m => m.decision === 'Pending').length;
  const lowConfidenceCount = mappings.filter(m => (m.confidence_score || 0) < CONFIDENCE_THRESHOLD).length;

  const handleReview = (mapping) => {
    setSelectedMapping(mapping);
    setReviewDecision(mapping.decision || 'Pending');
    setReviewNotes(mapping.review_notes || '');
    setShowReviewDialog(true);
  };

  const handleSubmitReview = () => {
    if (!reviewDecision || reviewDecision === 'Pending') {
      toast({
        title: 'Select Decision',
        description: 'Please select Accept, Reject, or Modify.',
        variant: 'destructive',
      });
      return;
    }

    updateMappingMutation.mutate({
      id: selectedMapping.id,
      data: {
        decision: reviewDecision,
        review_notes: reviewNotes,
        reviewer: 'Current User',
        reviewed_at: new Date().toISOString(),
      },
    });
  };

  const getConfidenceColor = (score) => {
    if (score >= 0.8) return 'text-emerald-600 bg-emerald-50';
    if (score >= 0.6) return 'text-amber-600 bg-amber-50';
    return 'text-red-600 bg-red-50';
  };

  const columns = [
    {
      header: 'Control ID',
      accessor: 'control_id',
      cell: (row) => (
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="font-mono text-xs">
            {row.control_id}
          </Badge>
          {(row.confidence_score || 0) < CONFIDENCE_THRESHOLD && (
            <AlertTriangle className="w-4 h-4 text-amber-500" />
          )}
        </div>
      ),
    },
    {
      header: 'Framework',
      accessor: 'framework',
      cell: (row) => (
        <Badge className="bg-slate-100 text-slate-700">
          {row.framework}
        </Badge>
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
        return (
          <div className={`inline-flex items-center px-2 py-1 rounded ${getConfidenceColor(score)}`}>
            <span className="text-sm font-medium">{Math.round(score * 100)}%</span>
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
      header: 'Reviewer',
      accessor: 'reviewer',
      cell: (row) => (
        <span className="text-sm text-slate-600">{row.reviewer || '-'}</span>
      ),
    },
    {
      header: '',
      accessor: 'actions',
      cell: (row) => (
        <Button variant="ghost" size="sm" onClick={() => handleReview(row)}>
          {row.decision === 'Pending' ? (
            <>
              <Edit className="w-4 h-4 mr-1" />
              Review
            </>
          ) : (
            <>
              <Eye className="w-4 h-4 mr-1" />
              View
            </>
          )}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer
      title="Mapping Review"
      subtitle="Human-in-the-loop validation of AI-generated control mappings"
    >
      {/* Stats Cards */}
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
              <p className="text-sm text-red-600">Low Confidence</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-emerald-50 border-emerald-200">
          <CardContent className="p-4 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-emerald-100 flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6 text-emerald-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-emerald-700">
                {mappings.filter(m => m.decision === 'Accepted').length}
              </p>
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
            <SelectItem value="low">Low (&lt;60%)</SelectItem>
            <SelectItem value="high">High (≥60%)</SelectItem>
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

      {/* Review Dialog */}
      <Dialog open={showReviewDialog} onOpenChange={setShowReviewDialog}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <GitCompare className="w-5 h-5 text-emerald-600" />
              Review Mapping
            </DialogTitle>
            <DialogDescription>
              Validate or modify the AI-generated control mapping
            </DialogDescription>
          </DialogHeader>

          {selectedMapping && (
            <div className="space-y-6 py-4">
              {/* Confidence Warning */}
              {(selectedMapping.confidence_score || 0) < CONFIDENCE_THRESHOLD && (
                <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                  <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5" />
                  <div>
                    <p className="font-medium text-amber-800">Low Confidence Mapping</p>
                    <p className="text-sm text-amber-700">
                      This mapping has a confidence score below {CONFIDENCE_THRESHOLD * 100}%. 
                      Please review carefully.
                    </p>
                  </div>
                </div>
              )}

              {/* Mapping Details */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-slate-500">Control ID</p>
                  <Badge variant="outline" className="font-mono mt-1">
                    {selectedMapping.control_id}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-slate-500">Framework</p>
                  <Badge className="bg-slate-100 text-slate-700 mt-1">
                    {selectedMapping.framework}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-slate-500">Confidence Score</p>
                  <div className={`inline-flex items-center px-2 py-1 rounded mt-1 ${getConfidenceColor(selectedMapping.confidence_score || 0)}`}>
                    <span className="font-medium">{Math.round((selectedMapping.confidence_score || 0) * 100)}%</span>
                  </div>
                </div>
                <div>
                  <p className="text-sm text-slate-500">Policy</p>
                  <p className="font-medium mt-1">
                    {policyMap[selectedMapping.policy_id]?.file_name || selectedMapping.policy_id}
                  </p>
                </div>
              </div>

              {/* Evidence */}
              <div>
                <p className="text-sm text-slate-500 mb-2">Evidence Snippet</p>
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                  <p className="text-sm text-slate-700 italic">
                    "{selectedMapping.evidence_snippet || 'No evidence available'}"
                  </p>
                </div>
              </div>

              {/* AI Rationale */}
              {selectedMapping.ai_rationale && (
                <div>
                  <p className="text-sm text-slate-500 mb-2 flex items-center gap-1">
                    <Brain className="w-4 h-4" />
                    AI Rationale
                  </p>
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <p className="text-sm text-blue-700">{selectedMapping.ai_rationale}</p>
                  </div>
                </div>
              )}

              {/* Decision */}
              <div className="space-y-2">
                <Label>Your Decision</Label>
                <div className="flex gap-2">
                  <Button
                    variant={reviewDecision === 'Accepted' ? 'default' : 'outline'}
                    onClick={() => setReviewDecision('Accepted')}
                    className={reviewDecision === 'Accepted' ? 'bg-emerald-600 hover:bg-emerald-700' : ''}
                  >
                    <CheckCircle2 className="w-4 h-4 mr-1" />
                    Accept
                  </Button>
                  <Button
                    variant={reviewDecision === 'Rejected' ? 'default' : 'outline'}
                    onClick={() => setReviewDecision('Rejected')}
                    className={reviewDecision === 'Rejected' ? 'bg-red-600 hover:bg-red-700' : ''}
                  >
                    <XCircle className="w-4 h-4 mr-1" />
                    Reject
                  </Button>
                  <Button
                    variant={reviewDecision === 'Modified' ? 'default' : 'outline'}
                    onClick={() => setReviewDecision('Modified')}
                    className={reviewDecision === 'Modified' ? 'bg-purple-600 hover:bg-purple-700' : ''}
                  >
                    <Edit className="w-4 h-4 mr-1" />
                    Modify
                  </Button>
                </div>
              </div>

              {/* Notes */}
              <div className="space-y-2">
                <Label>Review Notes (Optional)</Label>
                <Textarea
                  placeholder="Add any notes about your decision..."
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  rows={3}
                />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setShowReviewDialog(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleSubmitReview}
              disabled={updateMappingMutation.isPending}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              Save Review
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}