import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
import DataTable from '@/components/ui/DataTable';
import StatusBadge from '@/components/ui/StatusBadge';
import EmptyState from '@/components/ui/EmptyState';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
  Upload,
  FileText,
  FileBarChart,
  MoreVertical,
  Play,
  Pause,
  Eye,
  Trash2,
  Search,
  Filter,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  Database,
  Download,
  ShieldCheck,
  PauseCircle
} from 'lucide-react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';
import {
  fetchPolicyReportData,
  buildPolicyReport,
  persistReport,
  triggerBrowserDownload,
} from '@/lib/policyReport';

const Policy = api.entities.Policy;
const AuditLog = api.entities.AuditLog;
const Framework = api.entities.Framework;

export default function Policies() {
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [showPreviewDialog, setShowPreviewDialog] = useState(false);
  const [showFrameworkWarning, setShowFrameworkWarning] = useState(false);
  const [pendingAnalysisPolicy, setPendingAnalysisPolicy] = useState(null);
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [showReportDialog, setShowReportDialog] = useState(false);
  const [reportPolicy, setReportPolicy] = useState(null);
  const [reportFormat, setReportFormat] = useState('pdf');
  const [reportGenerating, setReportGenerating] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedFile, setSelectedFile] = useState(null);
  const [newPolicy, setNewPolicy] = useState({
    file_name: '',
    version: '1.0',
    framework: '',
  });

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: policies = [], isLoading } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-created_at'),
    // Poll every 2s while any policy is in 'processing' (or has a pause
    // request in flight) so live progress + status transitions
    // (processing → paused, paused → processing on resume) stay in sync.
    refetchInterval: (query) => {
      const data = query?.state?.data;
      if (!Array.isArray(data)) return false;
      if (data.some(p => p?.status === 'processing' || p?.pause_requested)) return 2000;
      return false;
    },
    refetchIntervalInBackground: false,
  });

  const pausePolicyMutation = useMutation({
    mutationFn: (id) => api.functions.invoke('pause_policy', { policy_id: id }),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['policies'] });
      const previous = queryClient.getQueryData(['policies']);
      queryClient.setQueryData(['policies'], (old = []) =>
        old.map(p => p.id === id ? { ...p, pause_requested: true, progress_stage: 'Pause requested…' } : p)
      );
      return { previous };
    },
    onError: (error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(['policies'], context.previous);
      toast({
        title: 'Pause Failed',
        description: error?.message || 'Could not request pause.',
        variant: 'destructive',
      });
    },
    onSuccess: () => {
      toast({
        title: 'Pause Requested',
        description: 'Analysis will stop at the next safe checkpoint.',
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] });
    },
  });

  const resumePolicyMutation = useMutation({
    mutationFn: (id) => api.functions.invoke('resume_policy', { policy_id: id }),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['policies'] });
      const previous = queryClient.getQueryData(['policies']);
      queryClient.setQueryData(['policies'], (old = []) =>
        old.map(p => p.id === id
          ? { ...p, status: 'processing', pause_requested: false, progress_stage: 'Resuming…' }
          : p)
      );
      return { previous };
    },
    onError: (error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(['policies'], context.previous);
      toast({
        title: 'Resume Failed',
        description: error?.message || 'Could not resume analysis.',
        variant: 'destructive',
      });
    },
    onSuccess: () => {
      toast({
        title: 'Analysis Resumed',
        description: 'Continuing from where it was paused.',
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] });
      queryClient.invalidateQueries({ queryKey: ['auditLogs'] });
    },
  });

  const {
    data: frameworks = [],
    isLoading: frameworksLoading,
  } = useQuery({
    queryKey: ['frameworks', 'available'],
    queryFn: () => Framework.list('name', 50),
    staleTime: 60_000,
  });


  const updatePolicyMutation = useMutation({
    mutationFn: ({ id, data }) => Policy.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] });
      toast({
        title: 'Policy Updated',
        description: 'Policy status has been updated.',
      });
    },
  });

  const deletePolicyMutation = useMutation({
    mutationFn: (id) => Policy.delete(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['policies'] });
      const previous = queryClient.getQueryData(['policies']);
      queryClient.setQueryData(['policies'], (old = []) => old.filter(p => p.id !== id));
      return { previous };
    },
    onError: (error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(['policies'], context.previous);
      toast({
        title: 'Delete Failed',
        description: error?.message || 'Could not delete the policy.',
        variant: 'destructive',
      });
    },
    onSuccess: () => {
      toast({
        title: 'Policy Deleted',
        description: 'Policy has been removed.',
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] });
      queryClient.invalidateQueries({ queryKey: ['auditLogs'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
    },
  });

  const resetForm = () => {
    setNewPolicy({
      file_name: '',
      version: '1.0',
      framework: '',
    });
    setSelectedFile(null);
    setUploadProgress(0);
  };

  // Just store the file locally — the real upload happens on Submit
  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setNewPolicy(prev => ({
      ...prev,
      file_name: file.name,
      file_type: file.name.split('.').pop(),
    }));
  };

  const handleSubmit = async () => {
    if (!selectedFile) {
      toast({
        title: 'Missing File',
        description: 'Please select a policy document.',
        variant: 'destructive',
      });
      return;
    }

    if (!newPolicy.framework) {
      toast({
        title: 'Framework Required',
        description: 'Select a framework to compare this policy against.',
        variant: 'destructive',
      });
      return;
    }

    setUploading(true);
    setUploadProgress(0);

    const progressInterval = setInterval(() => {
      setUploadProgress(prev => Math.min(prev + 10, 90));
    }, 300);

    try {
      const token = localStorage.getItem('token');
      const form = new FormData();
      form.append('file', selectedFile);
      form.append('version', newPolicy.version || '1.0');
      form.append('framework', newPolicy.framework);

      const res = await fetch('/api/integrations/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });

      clearInterval(progressInterval);
      setUploadProgress(100);

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(err.detail || 'Upload failed');
      }

      const result = await res.json();

      // Refresh policy list with the server-returned status
      queryClient.invalidateQueries({ queryKey: ['policies'] });

      toast({
        title: 'Policy Uploaded',
        description: `${result.file_name} uploaded with ${result.chunks || 0} chunks ready for analysis.`,
      });

      setShowUploadDialog(false);
      resetForm();
    } catch (error) {
      clearInterval(progressInterval);
      toast({
        title: 'Upload Failed',
        description: error.message,
        variant: 'destructive',
      });
    } finally {
      setUploading(false);
    }
  };

  const doRunAnalysis = async (policy) => {
    try {
      updatePolicyMutation.mutate({ id: policy.id, data: { status: 'processing' } });

      // If the policy was uploaded with an explicit framework, analyse only against
      // that one. Legacy policies without framework_code fall back to all three.
      const targetFrameworks = policy.framework_code
        ? [policy.framework_code]
        : ['NCA ECC', 'ISO 27001', 'NIST 800-53'];

      toast({
        title: 'Analysis Started',
        description: `Analyzing ${policy.file_name} against ${targetFrameworks.join(', ')}. This may take a few minutes...`,
      });

      const result = await api.functions.invoke('analyze_policy', {
        policy_id: policy.id,
        frameworks: targetFrameworks,
      });

      if (result.success) {
        // Refetch immediately so the badge flips from Processing → Analyzed
        // without waiting for the next polling tick (which may have already
        // stopped because the API call itself returned).
        await queryClient.refetchQueries({ queryKey: ['policies'] });
        queryClient.invalidateQueries({ queryKey: ['complianceResults'] });
        queryClient.invalidateQueries({ queryKey: ['gaps'] });
        queryClient.invalidateQueries({ queryKey: ['mappingReviews'] });
        queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });

        toast({
          title: 'Analysis Complete',
          description: `Analysis complete for ${policy.file_name}.`,
        });
      }
    } catch (error) {
      // Refetch from DB so the red "Failed" badge from the backend shows through.
      // Do NOT reset to 'uploaded' here — the backend already wrote status='failed'
      // with the error detail in progress_stage.
      await queryClient.refetchQueries({ queryKey: ['policies'] });
      toast({
        title: 'Analysis Failed',
        description: error.message || 'Failed to analyze policy',
        variant: 'destructive',
      });
    }
  };

  const handleRunAnalysis = async (policy) => {
    // Only block when *the policy's actual framework* has no reference
    // document loaded. The previous code checked a hardcoded three-framework
    // bundle, which fired the warning even when the policy's real framework
    // was fully loaded.
    try {
      const token = localStorage.getItem('token');
      const url = policy.framework_code
        ? `/api/functions/framework_status?framework=${encodeURIComponent(policy.framework_code)}`
        : '/api/functions/framework_status';
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const fwStatus = await res.json();
        if (!fwStatus.ready) {
          setPendingAnalysisPolicy({ ...policy, _fwSource: fwStatus.source });
          setShowFrameworkWarning(true);
          return;
        }
      }
    } catch (_) {
      // If the status check fails, fall through and let analysis attempt run.
    }
    doRunAnalysis(policy);
  };

  const handleViewPreview = (policy) => {
    setSelectedPolicy(policy);
    setShowPreviewDialog(true);
  };

  const openReportDialog = (policy) => {
    setReportPolicy(policy);
    setReportFormat('pdf');
    setShowReportDialog(true);
  };

  const handleGenerateReport = async () => {
    if (!reportPolicy) return;
    setReportGenerating(true);
    try {
      const data = await fetchPolicyReportData(reportPolicy.id);
      const { blob, filename, mime } = await buildPolicyReport(data, reportFormat);
      await persistReport({
        blob,
        filename,
        mime,
        policyId: reportPolicy.id,
        format: reportFormat.toUpperCase(),
      });
      triggerBrowserDownload(blob, filename);

      queryClient.invalidateQueries({ queryKey: ['reports'] });
      queryClient.invalidateQueries({ queryKey: ['auditLogs'] });

      toast({
        title: 'Report Generated',
        description: `${reportFormat.toUpperCase()} report for ${reportPolicy.file_name} saved and downloaded.`,
      });
      setShowReportDialog(false);
      setReportPolicy(null);
    } catch (error) {
      toast({
        title: 'Report Failed',
        description: error?.message || 'Could not generate the report.',
        variant: 'destructive',
      });
    } finally {
      setReportGenerating(false);
    }
  };

  const filteredPolicies = policies.filter(policy => {
    const matchesSearch = policy.file_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      policy.description?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || policy.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const columns = [
    {
      header: 'Policy Name',
      accessor: 'file_name',
      cell: (row) => (
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center">
            <FileText className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <p className="font-medium text-foreground">{row.file_name}</p>
            <p className="text-xs text-muted-foreground">{row.file_type?.toUpperCase()} • v{row.version || '1.0'}</p>
          </div>
        </div>
      ),
    },
    {
      header: 'Framework',
      accessor: 'framework_code',
      cell: (row) =>
        row.framework_code ? (
          <Badge
            variant="outline"
            className="gap-1.5 border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300 font-medium"
          >
            <ShieldCheck className="w-3 h-3" />
            {row.framework_code}
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        ),
    },
    {
      header: 'Uploaded',
      accessor: 'created_date',
      cell: (row) => (
        <div>
          <p className="text-sm text-foreground">
            {row.created_at ? format(new Date(row.created_at), 'MMM d, yyyy') : '-'}
          </p>
          <p className="text-xs text-muted-foreground">
            {row.uploaded_by || '—'}
          </p>
        </div>
      ),
    },
    {
      header: 'Last Analysis',
      accessor: 'last_analyzed_at',
      cell: (row) => (
        <span className="text-sm text-muted-foreground">
          {row.last_analyzed_at
            ? format(new Date(row.last_analyzed_at), 'MMM d, yyyy HH:mm')
            : 'Never'}
        </span>
      ),
    },
    {
      header: 'Status',
      accessor: 'status',
      cell: (row) => {
        const pct = Math.max(0, Math.min(100, Number(row.progress) || 0));
        const stage = row.progress_stage || '';

        if (row.status === 'processing') {
          const pausing = !!row.pause_requested;
          const labelColor = pausing ? 'text-muted-foreground' : 'text-amber-700 dark:text-amber-300';
          const trackColor = pausing ? 'bg-muted' : 'bg-amber-100 dark:bg-amber-500/20';
          const fillColor  = pausing
            ? 'bg-gradient-to-r from-slate-400 to-slate-500'
            : 'bg-gradient-to-r from-amber-400 to-emerald-500';
          return (
            <div className="min-w-[160px] max-w-[220px]">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${labelColor}`}>
                  <Loader2 className="w-3 h-3 animate-spin" />
                  {pausing ? 'Pausing…' : 'Processing'}
                </span>
                <span className={`text-xs font-semibold tabular-nums ${labelColor}`}>{pct}%</span>
              </div>
              <div className={`h-1.5 w-full rounded-full overflow-hidden ${trackColor}`}>
                <div
                  className={`h-full transition-all duration-500 ${fillColor}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="text-[10px] text-muted-foreground truncate mt-1" title={stage}>
                {pausing ? 'Pause will take effect at the next safe checkpoint.' : stage}
              </p>
            </div>
          );
        }

        if (row.status === 'paused') {
          return (
            <div className="min-w-[160px] max-w-[220px]">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground">
                  <PauseCircle className="w-3.5 h-3.5" />
                  Paused
                </span>
                <span className="text-xs font-semibold tabular-nums text-foreground">{pct}%</span>
              </div>
              <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-slate-400 dark:bg-slate-500 transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="text-[10px] text-muted-foreground truncate mt-1">
                {stage || 'Resume to continue analysis'}
              </p>
            </div>
          );
        }

        return <StatusBadge status={row.status || 'uploaded'} />;
      },
    },
    {
      header: '',
      accessor: 'actions',
      cell: (row) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreVertical className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {row.status === 'processing' ? (
              <DropdownMenuItem
                onClick={() => pausePolicyMutation.mutate(row.id)}
                disabled={row.pause_requested || pausePolicyMutation.isPending}
              >
                <Pause className="w-4 h-4 mr-2" />
                {row.pause_requested ? 'Pause Requested…' : 'Pause Analysis'}
              </DropdownMenuItem>
            ) : row.status === 'paused' ? (
              <DropdownMenuItem
                onClick={() => resumePolicyMutation.mutate(row.id)}
                disabled={resumePolicyMutation.isPending}
              >
                <Play className="w-4 h-4 mr-2" />
                Resume Analysis
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem onClick={() => handleRunAnalysis(row)}>
                <Play className="w-4 h-4 mr-2" />
                Run Analysis
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => handleViewPreview(row)}>
              <Eye className="w-4 h-4 mr-2" />
              View Details
            </DropdownMenuItem>
            <Link to={createPageUrl(`Analyses?policy_id=${row.id}`)}>
              <DropdownMenuItem>
                <FileText className="w-4 h-4 mr-2" />
                View Results
              </DropdownMenuItem>
            </Link>
            <DropdownMenuItem onClick={() => openReportDialog(row)}>
              <FileBarChart className="w-4 h-4 mr-2" />
              Generate Report
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                if (window.confirm(`Delete "${row.file_name}"? This removes it permanently along with its analyses.`)) {
                  deletePolicyMutation.mutate(row.id);
                }
              }}
              className="text-red-600 dark:text-red-400 focus:text-red-700 dark:focus:text-red-300"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  return (
    <PageContainer
      title="Policy Management"
      subtitle="Upload and manage your organization's security policies"
      actions={
        <Button 
          onClick={() => setShowUploadDialog(true)}
          className="bg-emerald-600 hover:bg-emerald-700"
        >
          <Upload className="w-4 h-4 mr-2" />
          Upload Policy
        </Button>
      }
    >
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search policies..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="uploaded">Uploaded</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="analyzed">Analyzed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={filteredPolicies}
        isLoading={isLoading}
        emptyState={
          <EmptyState
            icon={FileText}
            title="No policies found"
            description="Upload your first security policy to start compliance analysis"
            action={() => setShowUploadDialog(true)}
            actionLabel="Upload Policy"
          />
        }
      />

      {/* Upload Dialog */}
      <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Upload Policy Document</DialogTitle>
            <DialogDescription>
              Upload a security policy document for compliance analysis
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* File Upload Area */}
            <div className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-emerald-400 dark:hover:border-emerald-500 transition-colors">
              <input
                type="file"
                accept=".pdf,.docx,.txt,.xlsx,.xls"
                onChange={handleFileUpload}
                className="hidden"
                id="file-upload"
                disabled={uploading}
              />
              <label htmlFor="file-upload" className="cursor-pointer">
                {uploading ? (
                  <div className="space-y-2">
                    <Loader2 className="w-10 h-10 text-emerald-600 dark:text-emerald-400 mx-auto animate-spin" />
                    <p className="text-sm text-muted-foreground">Uploading... {uploadProgress}%</p>
                  </div>
                ) : newPolicy.file_name ? (
                  <div className="space-y-2">
                    <CheckCircle2 className="w-10 h-10 text-emerald-600 dark:text-emerald-400 mx-auto" />
                    <p className="text-sm font-medium text-foreground">{newPolicy.file_name}</p>
                    <p className="text-xs text-muted-foreground">Click to change file</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Upload className="w-10 h-10 text-muted-foreground mx-auto" />
                    <p className="text-sm text-muted-foreground">
                      Drag & drop or <span className="text-emerald-600 dark:text-emerald-400 font-medium">browse</span>
                    </p>
                    <p className="text-xs text-muted-foreground">Supports PDF, DOCX, TXT</p>
                  </div>
                )}
              </label>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>
                  Framework <span className="text-red-500 dark:text-red-400">*</span>
                </Label>
                <Select
                  value={newPolicy.framework}
                  onValueChange={(value) =>
                    setNewPolicy((prev) => ({ ...prev, framework: value }))
                  }
                  disabled={uploading || frameworksLoading || frameworks.length === 0}
                >
                  <SelectTrigger>
                    <SelectValue
                      placeholder={
                        frameworksLoading
                          ? 'Loading frameworks…'
                          : frameworks.length === 0
                            ? 'No frameworks available'
                            : 'Select a framework'
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {frameworks.map((fw) => (
                      <SelectItem key={fw.id} value={fw.name}>
                        <span className="flex items-center gap-2">
                          {fw.name}
                          {fw.is_structured && (
                            <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                              Structured
                            </span>
                          )}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!frameworksLoading && frameworks.length === 0 && (
                  <p className="text-xs text-amber-600 dark:text-amber-400">
                    Upload a reference document on the Frameworks page first.
                  </p>
                )}
                {!frameworksLoading && frameworks.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {frameworks.find(fw => fw.name === newPolicy.framework)?.is_structured
                      ? 'Uses structured control tables — official control text verified.'
                      : 'The policy will be analyzed against this framework\'s controls.'}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label>Version</Label>
                <Input
                  placeholder="1.0"
                  value={newPolicy.version}
                  onChange={(e) => setNewPolicy(prev => ({ ...prev, version: e.target.value }))}
                />
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setShowUploadDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!selectedFile || !newPolicy.framework || uploading}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Uploading... {uploadProgress}%
                </>
              ) : (
                'Save Policy'
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Generate Report Dialog */}
      <Dialog open={showReportDialog} onOpenChange={(open) => !reportGenerating && setShowReportDialog(open)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileBarChart className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              Generate Report
            </DialogTitle>
            <DialogDescription>
              Export a branded compliance report for{' '}
              <span className="font-medium text-foreground">
                {reportPolicy?.file_name || 'this policy'}
              </span>
              .
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>Format</Label>
              <Select value={reportFormat} onValueChange={setReportFormat}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="pdf">PDF — Branded report with cover, charts and findings</SelectItem>
                  <SelectItem value="csv">CSV — Tabular export for spreadsheets</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Includes policy details, compliance results, findings, gaps, mapped evidence and AI insights from the database.
              </p>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button
              variant="outline"
              onClick={() => setShowReportDialog(false)}
              disabled={reportGenerating}
            >
              Cancel
            </Button>
            <Button
              onClick={handleGenerateReport}
              disabled={reportGenerating}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {reportGenerating ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4 mr-2" />
                  Generate {reportFormat.toUpperCase()}
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Framework Warning Dialog */}
      <Dialog open={showFrameworkWarning} onOpenChange={setShowFrameworkWarning}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500 dark:text-amber-400" />
              Framework Document Not Loaded
            </DialogTitle>
            <DialogDescription>
              {pendingAnalysisPolicy?._fwSource === 'structured_ecc_tables' ? (
                <>
                  The structured control data for{' '}
                  <strong>{pendingAnalysisPolicy.framework_code}</strong> has not been imported
                  into the database yet. This framework does not require a PDF upload — it uses
                  pre-built structured tables that must be populated by an administrator.
                </>
              ) : pendingAnalysisPolicy?.framework_code ? (
                <>
                  The reference document for{' '}
                  <strong>{pendingAnalysisPolicy.framework_code}</strong> hasn't been uploaded yet,
                  so the AI will fall back to basic control definitions instead of comparing this
                  policy against the full framework requirements.
                </>
              ) : (
                <>
                  No reference document is loaded for this policy's framework. The AI will use
                  basic control definitions only.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-start gap-3 p-3 bg-amber-50 border border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/30 rounded-lg my-2">
            <Database className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-amber-700 dark:text-amber-200">
              {pendingAnalysisPolicy?._fwSource === 'structured_ecc_tables'
                ? <>Ask an administrator to restart the server or run the import script for <strong>{pendingAnalysisPolicy.framework_code}</strong>.</>
                : <>Ask an administrator to upload the reference document for{' '}
                    {pendingAnalysisPolicy?.framework_code
                      ? <> <strong>{pendingAnalysisPolicy.framework_code}</strong> </>
                      : ' this framework '}
                    from the Admin <strong>Frameworks</strong> panel for the best results.</>
              }
            </p>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Link to={createPageUrl('Frameworks')}>
              <Button variant="outline" onClick={() => setShowFrameworkWarning(false)}>
                Go to Frameworks Page
              </Button>
            </Link>
            <Button
              className="bg-emerald-600 hover:bg-emerald-700"
              onClick={() => {
                setShowFrameworkWarning(false);
                if (pendingAnalysisPolicy) doRunAnalysis(pendingAnalysisPolicy);
              }}
            >
              <Play className="w-4 h-4 mr-2" />
              Continue Anyway
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Preview Dialog */}
      <Dialog open={showPreviewDialog} onOpenChange={setShowPreviewDialog}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              {selectedPolicy?.file_name}
            </DialogTitle>
          </DialogHeader>

          {selectedPolicy && (
            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <StatusBadge status={selectedPolicy.status} />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Version</p>
                  <p className="font-medium text-foreground">{selectedPolicy.version || '1.0'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Framework</p>
                  <p className="font-medium text-foreground">{selectedPolicy.framework_code || '—'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Upload Date</p>
                  <p className="font-medium text-foreground">
                    {selectedPolicy.created_at
                      ? format(new Date(selectedPolicy.created_at), 'MMM d, yyyy HH:mm')
                      : '-'}
                  </p>
                </div>
              </div>

              {selectedPolicy.description && (
                <div>
                  <p className="text-sm text-muted-foreground mb-1">Description</p>
                  <p className="text-sm text-foreground">{selectedPolicy.description}</p>
                </div>
              )}

              {selectedPolicy.content_preview && (
                <div>
                  <p className="text-sm text-muted-foreground mb-1">Content Preview</p>
                  <div className="bg-muted rounded-lg p-4 text-sm text-foreground max-h-48 overflow-auto">
                    {selectedPolicy.content_preview}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setShowPreviewDialog(false)}>
              Close
            </Button>
            {selectedPolicy?.status !== 'processing' && (
              <Button 
                onClick={() => {
                  handleRunAnalysis(selectedPolicy);
                  setShowPreviewDialog(false);
                }}
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                <Play className="w-4 h-4 mr-2" />
                Run Analysis
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}