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
import { Textarea } from '@/components/ui/textarea';
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
  MoreVertical,
  Play,
  Eye,
  Trash2,
  Archive,
  Search,
  Filter,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  Database
} from 'lucide-react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';

const Policy = api.entities.Policy;
const AuditLog = api.entities.AuditLog;

export default function Policies() {
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [showPreviewDialog, setShowPreviewDialog] = useState(false);
  const [showFrameworkWarning, setShowFrameworkWarning] = useState(false);
  const [pendingAnalysisPolicy, setPendingAnalysisPolicy] = useState(null);
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedFile, setSelectedFile] = useState(null);
  const [newPolicy, setNewPolicy] = useState({
    file_name: '',
    description: '',
    department: '',
    version: '1.0',
  });

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: policies = [], isLoading } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-created_at'),
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] });
      toast({
        title: 'Policy Deleted',
        description: 'Policy has been removed.',
      });
    },
  });

  const resetForm = () => {
    setNewPolicy({
      file_name: '',
      description: '',
      department: '',
      version: '1.0',
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

    setUploading(true);
    setUploadProgress(0);

    const progressInterval = setInterval(() => {
      setUploadProgress(prev => Math.min(prev + 10, 90));
    }, 300);

    try {
      const token = localStorage.getItem('token');
      const form = new FormData();
      form.append('file', selectedFile);
      form.append('department', newPolicy.department || 'General');
      form.append('version', newPolicy.version || '1.0');
      form.append('description', newPolicy.description || '');

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

      toast({
        title: 'Analysis Started',
        description: `Analyzing ${policy.file_name} across all 3 frameworks (90 controls). This may take a few minutes...`,
      });

      const result = await api.functions.invoke('analyze_policy', {
        policy_id: policy.id,
        frameworks: ['NCA ECC', 'ISO 27001', 'NIST 800-53'],
      });

      if (result.success) {
        queryClient.invalidateQueries({ queryKey: ['policies'] });
        queryClient.invalidateQueries({ queryKey: ['complianceResults'] });
        queryClient.invalidateQueries({ queryKey: ['gaps'] });
        queryClient.invalidateQueries({ queryKey: ['mappingReviews'] });

        toast({
          title: 'Analysis Complete',
          description: `Created ${result.mappings_created} mappings and identified ${result.gaps_created} gaps.`,
        });
      }
    } catch (error) {
      updatePolicyMutation.mutate({ id: policy.id, data: { status: 'uploaded' } });
      toast({
        title: 'Analysis Failed',
        description: error.message || 'Failed to analyze policy',
        variant: 'destructive',
      });
    }
  };

  const handleRunAnalysis = async (policy) => {
    // Check if framework reference documents are loaded
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/functions/framework_status', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const fwStatus = await res.json();
        if (!fwStatus.ready) {
          setPendingAnalysisPolicy(policy);
          setShowFrameworkWarning(true);
          return;
        }
      }
    } catch (_) {
      // If status check fails, proceed anyway
    }
    doRunAnalysis(policy);
  };

  const handleViewPreview = (policy) => {
    setSelectedPolicy(policy);
    setShowPreviewDialog(true);
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
          <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
            <FileText className="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <p className="font-medium text-slate-900">{row.file_name}</p>
            <p className="text-xs text-slate-500">{row.file_type?.toUpperCase()} • v{row.version || '1.0'}</p>
          </div>
        </div>
      ),
    },
    {
      header: 'Department',
      accessor: 'department',
      cell: (row) => (
        <span className="text-sm text-slate-600">{row.department || 'General'}</span>
      ),
    },
    {
      header: 'Uploaded',
      accessor: 'created_date',
      cell: (row) => (
        <div>
          <p className="text-sm text-slate-900">
            {row.created_at ? format(new Date(row.created_at), 'MMM d, yyyy') : '-'}
          </p>
          <p className="text-xs text-slate-500">
            {row.created_by || 'Unknown'}
          </p>
        </div>
      ),
    },
    {
      header: 'Last Analysis',
      accessor: 'last_analyzed_at',
      cell: (row) => (
        <span className="text-sm text-slate-600">
          {row.last_analyzed_at 
            ? format(new Date(row.last_analyzed_at), 'MMM d, yyyy HH:mm')
            : 'Never'}
        </span>
      ),
    },
    {
      header: 'Status',
      accessor: 'status',
      cell: (row) => <StatusBadge status={row.status || 'uploaded'} />,
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
            <DropdownMenuItem onClick={() => handleRunAnalysis(row)}>
              <Play className="w-4 h-4 mr-2" />
              Run Analysis
            </DropdownMenuItem>
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
            <DropdownMenuItem 
              onClick={() => updatePolicyMutation.mutate({ id: row.id, data: { status: 'archived' } })}
            >
              <Archive className="w-4 h-4 mr-2" />
              Archive
            </DropdownMenuItem>
            <DropdownMenuItem 
              onClick={() => deletePolicyMutation.mutate(row.id)}
              className="text-red-600"
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
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
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
            <SelectItem value="archived">Archived</SelectItem>
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
            <div className="border-2 border-dashed border-slate-200 rounded-lg p-8 text-center hover:border-emerald-400 transition-colors">
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
                    <Loader2 className="w-10 h-10 text-emerald-600 mx-auto animate-spin" />
                    <p className="text-sm text-slate-600">Uploading... {uploadProgress}%</p>
                  </div>
                ) : newPolicy.file_name ? (
                  <div className="space-y-2">
                    <CheckCircle2 className="w-10 h-10 text-emerald-600 mx-auto" />
                    <p className="text-sm font-medium text-slate-900">{newPolicy.file_name}</p>
                    <p className="text-xs text-slate-500">Click to change file</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Upload className="w-10 h-10 text-slate-400 mx-auto" />
                    <p className="text-sm text-slate-600">
                      Drag & drop or <span className="text-emerald-600 font-medium">browse</span>
                    </p>
                    <p className="text-xs text-slate-400">Supports PDF, DOCX, TXT</p>
                  </div>
                )}
              </label>
            </div>

            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea
                placeholder="Brief description of the policy..."
                value={newPolicy.description}
                onChange={(e) => setNewPolicy(prev => ({ ...prev, description: e.target.value }))}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Department</Label>
                <Select 
                  value={newPolicy.department} 
                  onValueChange={(value) => setNewPolicy(prev => ({ ...prev, department: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="IT Security">IT Security</SelectItem>
                    <SelectItem value="Compliance">Compliance</SelectItem>
                    <SelectItem value="Operations">Operations</SelectItem>
                    <SelectItem value="HR">HR</SelectItem>
                    <SelectItem value="General">General</SelectItem>
                  </SelectContent>
                </Select>
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
              disabled={!selectedFile || uploading}
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

      {/* Framework Warning Dialog */}
      <Dialog open={showFrameworkWarning} onOpenChange={setShowFrameworkWarning}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              Framework Documents Not Loaded
            </DialogTitle>
            <DialogDescription>
              The AI will use basic control definitions only. For deeper analysis that compares your
              policy against the full framework requirements, upload reference documents in the
              Frameworks page first.
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-start gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg my-2">
            <Database className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-amber-700">
              Upload official NCA ECC, ISO 27001, and NIST 800-53 documents in
              <strong> Frameworks → Upload Reference Document</strong> for best results.
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
              <FileText className="w-5 h-5 text-emerald-600" />
              {selectedPolicy?.file_name}
            </DialogTitle>
          </DialogHeader>

          {selectedPolicy && (
            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-slate-500">Status</p>
                  <StatusBadge status={selectedPolicy.status} />
                </div>
                <div>
                  <p className="text-sm text-slate-500">Version</p>
                  <p className="font-medium">{selectedPolicy.version || '1.0'}</p>
                </div>
                <div>
                  <p className="text-sm text-slate-500">Department</p>
                  <p className="font-medium">{selectedPolicy.department || 'General'}</p>
                </div>
                <div>
                  <p className="text-sm text-slate-500">Upload Date</p>
                  <p className="font-medium">
                    {selectedPolicy.created_at 
                      ? format(new Date(selectedPolicy.created_at), 'MMM d, yyyy HH:mm')
                      : '-'}
                  </p>
                </div>
              </div>

              {selectedPolicy.description && (
                <div>
                  <p className="text-sm text-slate-500 mb-1">Description</p>
                  <p className="text-sm">{selectedPolicy.description}</p>
                </div>
              )}

              {selectedPolicy.content_preview && (
                <div>
                  <p className="text-sm text-slate-500 mb-1">Content Preview</p>
                  <div className="bg-slate-50 rounded-lg p-4 text-sm text-slate-700 max-h-48 overflow-auto">
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