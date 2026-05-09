import React, { useState, useMemo } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
import NextAction from '@/components/layout/NextAction';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import { createPageUrl } from '@/utils';
import DataTable from '@/components/ui/DataTable';
import StatusBadge from '@/components/ui/StatusBadge';
import EmptyState from '@/components/ui/EmptyState';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
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
  FileBarChart,
  Download,
  Plus,
  Search,
  FileText,
  FileSpreadsheet,
  Loader2,
  Calendar,
  Trash2,
  Package,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';
import { format } from 'date-fns';
import {
  buildPolicyReport,
  fetchPolicyReportData,
  persistReport,
  triggerBrowserDownload,
  downloadFromUrl,
} from '@/lib/policyReport';

// ── Compliance Package download helper ───────────────────────────────────────
// Calls POST /api/reports/export and triggers a browser file download.
// Returns true on success, throws on error.
async function downloadCompliancePackage(policyId, includeDraftText = true) {
  const token = localStorage.getItem('token');
  const res = await fetch('/api/reports/export', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      policy_id: policyId,
      include_draft_text: includeDraftText,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Export failed' }));
    throw new Error(err.detail || 'Export failed');
  }

  const blob = await res.blob();
  // Extract filename from Content-Disposition if present, otherwise use a fallback.
  const disposition = res.headers.get('Content-Disposition') || '';
  const match       = disposition.match(/filename="([^"]+)"/);
  const filename    = match ? match[1] : 'himaya_compliance_package.docx';

  const url = URL.createObjectURL(blob);
  const a   = document.createElement('a');
  a.href     = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  return filename;
}

const Report = api.entities.Report;
const Policy = api.entities.Policy;

export default function Reports() {
  const [searchQuery, setSearchQuery] = useState('');
  const [showGenerateDialog, setShowGenerateDialog] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [reportConfig, setReportConfig] = useState({
    policy_id: '',
    format: 'PDF',
  });

  // Compliance Package (DOCX) state
  const [showPackageDialog,   setShowPackageDialog]   = useState(false);
  const [packagePolicyId,     setPackagePolicyId]     = useState('');
  const [packageIncludeText,  setPackageIncludeText]  = useState(true);
  const [generatingPackage,   setGeneratingPackage]   = useState(false);

  // Phase H: replace window.confirm with a proper Dialog so the destructive
  // confirmation is consistent with the rest of the app's modals.
  const [deleteTarget, setDeleteTarget] = useState(null);

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['reports'],
    queryFn: () => Report.list('-created_at'),
  });

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-created_at'),
  });

  const deleteReportMutation = useMutation({
    mutationFn: (id) => Report.delete(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['reports'] });
      const previous = queryClient.getQueryData(['reports']);
      queryClient.setQueryData(['reports'], (old = []) => old.filter(r => r.id !== id));
      return { previous };
    },
    onError: (error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(['reports'], context.previous);
      toast({
        title: 'Delete Failed',
        description: error?.message || 'Could not delete the report.',
        variant: 'destructive',
      });
    },
    onSuccess: () => {
      toast({
        title: 'Report Deleted',
        description: 'The report and its file have been removed.',
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['reports'] });
      queryClient.invalidateQueries({ queryKey: ['auditLogs'] });
    },
  });

  const handleDelete = (report) => setDeleteTarget(report);

  const confirmDelete = () => {
    if (!deleteTarget) return;
    deleteReportMutation.mutate(deleteTarget.id);
    setDeleteTarget(null);
  };

  // Phase UI-7: memoised so the map only rebuilds when policies actually
  // changes — not on every search/filter keystroke.
  const policyMap = useMemo(
    () => policies.reduce((acc, p) => { acc[p.id] = p; return acc; }, {}),
    [policies],
  );

  const filteredReports = reports.filter(report => {
    const policy = policyMap[report.policy_id];
    const haystack = `${policy?.file_name || ''} ${report.format || ''} ${report.report_type || ''}`.toLowerCase();
    return haystack.includes(searchQuery.toLowerCase());
  });

  const handleGenerateReport = async () => {
    if (!reportConfig.policy_id) {
      toast({
        title: 'Select Policy',
        description: 'Please select a policy to generate the report for.',
        variant: 'destructive',
      });
      return;
    }

    setGenerating(true);
    try {
      const fmt = reportConfig.format.toLowerCase();
      const data = await fetchPolicyReportData(reportConfig.policy_id);
      const { blob, filename, mime } = await buildPolicyReport(data, fmt);

      await persistReport({
        blob,
        filename,
        mime,
        policyId: reportConfig.policy_id,
        format: reportConfig.format,
      });

      triggerBrowserDownload(blob, filename);

      queryClient.invalidateQueries({ queryKey: ['reports'] });
      queryClient.invalidateQueries({ queryKey: ['auditLogs'] });

      toast({
        title: 'Report Generated',
        description: `${reportConfig.format} report saved and downloaded.`,
      });
      setShowGenerateDialog(false);
      setReportConfig({ policy_id: '', format: 'PDF' });
    } catch (error) {
      toast({
        title: 'Generation Failed',
        description: error?.message || 'Failed to generate report',
        variant: 'destructive',
      });
    }
    setGenerating(false);
  };

  const handleGeneratePackage = async () => {
    if (!packagePolicyId) {
      toast({ title: 'Select a policy', variant: 'destructive' });
      return;
    }
    setGeneratingPackage(true);
    try {
      const filename = await downloadCompliancePackage(packagePolicyId, packageIncludeText);
      toast({ title: 'Compliance Package downloaded', description: filename });
      setShowPackageDialog(false);
      setPackagePolicyId('');
    } catch (err) {
      toast({
        title: 'Export failed',
        description: err.message || 'Could not generate the compliance package.',
        variant: 'destructive',
      });
    } finally {
      setGeneratingPackage(false);
    }
  };

  const handleDownload = (report) => {
    if (!report.download_url) {
      toast({
        title: 'Download Unavailable',
        description: 'This report file is no longer available.',
        variant: 'destructive',
      });
      return;
    }
    const policyName = policyMap[report.policy_id]?.file_name || 'policy';
    const ext = (report.format || 'pdf').toLowerCase();
    const filename = `himaya_report_${policyName}.${ext === 'pdf' ? 'pdf' : ext}`;
    downloadFromUrl(report.download_url, filename);
  };

  const getFormatIcon = (fmt) => {
    switch ((fmt || '').toUpperCase()) {
      case 'CSV':
        return <FileSpreadsheet className="w-4 h-4 text-green-600 dark:text-green-400" />;
      default:
        return <FileText className="w-4 h-4 text-red-600 dark:text-red-400" />;
    }
  };

  const columns = [
    {
      header: 'Report',
      accessor: 'policy_id',
      cell: (row) => (
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center">
            <FileBarChart className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <p className="font-medium text-foreground">
              {policyMap[row.policy_id]?.file_name || 'Unknown Policy'}
            </p>
            <p className="text-xs text-muted-foreground">
              {row.report_type || 'Compliance Report'}
            </p>
          </div>
        </div>
      ),
    },
    {
      header: 'Format',
      accessor: 'format',
      cell: (row) => (
        <div className="flex items-center gap-2">
          {getFormatIcon(row.format)}
          <span className="text-sm">{(row.format || 'PDF').toUpperCase()}</span>
        </div>
      ),
    },
    {
      header: 'Generated',
      accessor: 'generated_at',
      cell: (row) => (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Calendar className="w-4 h-4" />
          {row.generated_at
            ? format(new Date(row.generated_at), 'MMM d, yyyy HH:mm')
            : row.created_at
              ? format(new Date(row.created_at), 'MMM d, yyyy HH:mm')
              : '—'}
        </div>
      ),
    },
    {
      header: 'Status',
      accessor: 'status',
      cell: (row) => <StatusBadge status={row.status || 'Completed'} />,
    },
    {
      header: '',
      accessor: 'actions',
      cell: (row) => (
        <div className="flex items-center justify-end gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => handleDownload(row)}
            disabled={!row.download_url || row.status === 'Generating'}
          >
            <Download className="w-4 h-4 mr-1" />
            Download
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => handleDelete(row)}
            className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-500/10"
            aria-label="Delete report"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      ),
    },
  ];

  // Phase UI-1: recommended next action — drives the banner above the table.
  const nextAction = useMemo(() => {
    if (isLoading) return null;
    if (policies.length === 0) {
      return {
        primary: {
          label: 'Upload a policy first',
          helper: 'Reports are generated from analysed policies — start there.',
          to: createPageUrl('Policies'),
          icon: FileText,
        },
      };
    }
    const analysedCount = policies.filter(p => p.status === 'analyzed').length;
    if (reports.length === 0 && analysedCount > 0) {
      return {
        primary: {
          label: 'Generate your first report',
          helper: 'Per-policy PDF / CSV, or a full DOCX compliance package across everything.',
          onClick: () => setShowGenerateDialog(true),
          icon: FileBarChart,
        },
        secondary: [
          { label: 'Compliance package (DOCX)', onClick: () => setShowPackageDialog(true) },
        ],
      };
    }
    return null;
  }, [isLoading, policies, reports.length]);

  return (
    <PageContainer
      title="Reports"
      subtitle="Generate and download compliance reports"
      actions={
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setShowPackageDialog(true)}
            className="border-purple-500/40 text-purple-700 dark:text-purple-300 hover:bg-purple-500/10 gap-1.5"
          >
            <Package className="w-4 h-4" />
            Compliance Package
            <Badge className="ml-1 text-[10px] bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/20 dark:text-purple-300 dark:border-purple-500/30">
              DOCX
            </Badge>
          </Button>
          <Button
            onClick={() => setShowGenerateDialog(true)}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            <Plus className="w-4 h-4 mr-2" />
            Generate Report
          </Button>
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

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search reports..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={filteredReports}
        isLoading={isLoading}
        emptyState={
          <EmptyState
            icon={FileBarChart}
            title="No reports generated"
            description="Generate your first compliance report to track your security posture"
            action={() => setShowGenerateDialog(true)}
            actionLabel="Generate Report"
          />
        }
      />

      {/* ── Compliance Package Dialog ─────────────────────────────────────────── */}
      <Dialog
        open={showPackageDialog}
        onOpenChange={(open) => !generatingPackage && setShowPackageDialog(open)}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Package className="w-5 h-5 text-purple-600 dark:text-purple-400" />
              Generate Compliance Package
            </DialogTitle>
            <DialogDescription>
              Export a full enterprise-grade DOCX package containing compliance scores,
              open gaps, AI remediation drafts, and version history.
            </DialogDescription>
          </DialogHeader>

          {/* What's included */}
          <Card className="border-purple-500/20 bg-purple-500/5">
            <CardContent className="p-4">
              <p className="text-xs font-semibold text-purple-700 dark:text-purple-300 mb-2 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                What&apos;s included in this package:
              </p>
              <ul className="space-y-1.5">
                {[
                  'Executive summary with compliance scores per framework',
                  'Open gaps table with severity color-coding',
                  'AI remediation drafts with control-satisfaction mapping',
                  'Policy version history',
                  'Legal disclaimer',
                ].map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-purple-800 dark:text-purple-200">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mt-0.5 shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>Select Policy</Label>
              <Select value={packagePolicyId} onValueChange={setPackagePolicyId}>
                <SelectTrigger>
                  <SelectValue placeholder="Choose a policy…" />
                </SelectTrigger>
                <SelectContent>
                  {policies.length === 0 ? (
                    <SelectItem value="__none" disabled>No policies available</SelectItem>
                  ) : (
                    policies.map(p => (
                      <SelectItem key={p.id} value={p.id}>{p.file_name}</SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="include-draft-text"
                checked={packageIncludeText}
                onChange={e => setPackageIncludeText(e.target.checked)}
                className="rounded border-border"
              />
              <Label htmlFor="include-draft-text" className="cursor-pointer font-normal text-sm">
                Include full AI draft text in the document
                <span className="block text-xs text-muted-foreground">
                  Uncheck for a shorter summary-only package
                </span>
              </Label>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-1 border-t border-border/60">
            <Button
              variant="outline"
              onClick={() => setShowPackageDialog(false)}
              disabled={generatingPackage}
            >
              Cancel
            </Button>
            <Button
              onClick={handleGeneratePackage}
              disabled={generatingPackage || !packagePolicyId}
              className="bg-purple-600 hover:bg-purple-700 gap-2"
            >
              {generatingPackage ? (
                <><Loader2 className="w-4 h-4 animate-spin" />Building package…</>
              ) : (
                <><Package className="w-4 h-4" />Download DOCX</>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Standard Report Dialog ────────────────────────────────────────────── */}
      <Dialog
        open={showGenerateDialog}
        onOpenChange={(open) => !generating && setShowGenerateDialog(open)}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileBarChart className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              Generate Compliance Report
            </DialogTitle>
            <DialogDescription>
              Create a branded compliance report for one of your policies.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Select Policy</Label>
              <Select
                value={reportConfig.policy_id}
                onValueChange={(value) => setReportConfig(prev => ({ ...prev, policy_id: value }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Choose a policy..." />
                </SelectTrigger>
                <SelectContent>
                  {policies.length === 0 ? (
                    <SelectItem value="__none" disabled>No policies available</SelectItem>
                  ) : (
                    policies.map((policy) => (
                      <SelectItem key={policy.id} value={policy.id}>
                        {policy.file_name}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Format</Label>
              <Select
                value={reportConfig.format}
                onValueChange={(value) => setReportConfig(prev => ({ ...prev, format: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PDF">PDF — Branded report with cover, charts and findings</SelectItem>
                  <SelectItem value="CSV">CSV — Tabular export for spreadsheets</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Includes policy details, compliance results, findings, gaps, mapped evidence and AI insights from the database.
              </p>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <Button
              variant="outline"
              onClick={() => setShowGenerateDialog(false)}
              disabled={generating}
            >
              Cancel
            </Button>
            <Button
              onClick={handleGenerateReport}
              disabled={generating || !reportConfig.policy_id}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {generating ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <FileBarChart className="w-4 h-4 mr-2" />
                  Generate Report
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Phase UI-2: Delete-report confirm — migrated from inline Dialog to
          the shared ConfirmDialog so the destructive-action UX is consistent
          across Reports + Policies + (future) other destructive flows. */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Delete report?"
        description={
          deleteTarget
            ? `This permanently removes the ${deleteTarget.format || 'report'} for "${
                policyMap[deleteTarget.policy_id]?.file_name || 'this policy'
              }", including the stored file. This cannot be undone.`
            : ''
        }
        confirmLabel="Delete report"
        onConfirm={confirmDelete}
        pending={deleteReportMutation.isPending}
      />
    </PageContainer>
  );
}
