import React, { useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
import DataTable from '@/components/ui/DataTable';
import StatusBadge from '@/components/ui/StatusBadge';
import EmptyState from '@/components/ui/EmptyState';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
} from 'lucide-react';
import { format } from 'date-fns';
import {
  buildPolicyReport,
  fetchPolicyReportData,
  persistReport,
  triggerBrowserDownload,
  downloadFromUrl,
} from '@/lib/policyReport';

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

  const handleDelete = (report) => {
    const policyName = policyMap[report.policy_id]?.file_name || 'this report';
    if (window.confirm(`Delete this ${report.format || 'report'} for "${policyName}"? The stored file will also be removed.`)) {
      deleteReportMutation.mutate(report.id);
    }
  };

  const policyMap = policies.reduce((acc, p) => {
    acc[p.id] = p;
    return acc;
  }, {});

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

  return (
    <PageContainer
      title="Reports"
      subtitle="Generate and download compliance reports"
      actions={
        <Button
          onClick={() => setShowGenerateDialog(true)}
          className="bg-emerald-600 hover:bg-emerald-700"
        >
          <Plus className="w-4 h-4 mr-2" />
          Generate Report
        </Button>
      }
    >
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

      {/* Generate Dialog */}
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
    </PageContainer>
  );
}
