import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
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
  Loader2
} from 'lucide-react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';

const Policy = base44.entities.Policy;
const AuditLog = base44.entities.AuditLog;

export default function Policies() {
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [showPreviewDialog, setShowPreviewDialog] = useState(false);
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
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
    queryFn: () => Policy.list('-created_date'),
  });

  const createPolicyMutation = useMutation({
    mutationFn: async (policyData) => {
      return Policy.create(policyData);
    },
    onSuccess: async (newPolicy) => {
      queryClient.invalidateQueries(['policies']);
      await AuditLog.create({
        actor: 'Current User',
        action: 'policy_upload',
        target_type: 'policy',
        target_id: newPolicy.id,
        details: `Uploaded policy: ${newPolicy.file_name}`,
      });
      toast({
        title: 'Policy Uploaded',
        description: `${newPolicy.file_name} has been uploaded successfully. Policy ID: ${newPolicy.id}`,
      });
      setShowUploadDialog(false);
      resetForm();
    },
    onError: (error) => {
      toast({
        title: 'Upload Failed',
        description: error.message,
        variant: 'destructive',
      });
    },
  });

  const updatePolicyMutation = useMutation({
    mutationFn: ({ id, data }) => Policy.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['policies']);
      toast({
        title: 'Policy Updated',
        description: 'Policy status has been updated.',
      });
    },
  });

  const deletePolicyMutation = useMutation({
    mutationFn: (id) => Policy.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries(['policies']);
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
    setUploadProgress(0);
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);

    try {
      // Simulate progress
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => Math.min(prev + 10, 90));
      }, 200);

      // Upload file
      const { file_url } = await base44.integrations.Core.UploadFile({ file });
      
      clearInterval(progressInterval);
      setUploadProgress(100);

      setNewPolicy(prev => ({
        ...prev,
        file_name: file.name,
        file_url,
        file_type: file.name.split('.').pop(),
      }));

      toast({
        title: 'File Uploaded',
        description: 'File has been uploaded. Please complete the form to save.',
      });
    } catch (error) {
      toast({
        title: 'Upload Failed',
        description: error.message,
        variant: 'destructive',
      });
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = () => {
    if (!newPolicy.file_name) {
      toast({
        title: 'Missing File',
        description: 'Please upload a policy document.',
        variant: 'destructive',
      });
      return;
    }

    createPolicyMutation.mutate({
      ...newPolicy,
      status: 'uploaded',
    });
  };

  const handleRunAnalysis = async (policy) => {
    try {
      updatePolicyMutation.mutate({
        id: policy.id,
        data: { status: 'processing' },
      });

      toast({
        title: 'Analysis Started',
        description: `Analyzing ${policy.file_name} across all frameworks...`,
      });

      // Call backend function
      const result = await base44.functions.invoke('analyze_policy', {
        policy_id: policy.id,
        frameworks: ['NCA ECC', 'ISO 27001', 'NIST 800-53'],
      });

      if (result.success) {
        queryClient.invalidateQueries(['policies']);
        queryClient.invalidateQueries(['complianceResults']);
        queryClient.invalidateQueries(['gaps']);
        
        toast({
          title: 'Analysis Complete',
          description: `Created ${result.mappings_created} mappings and identified ${result.gaps_created} gaps.`,
        });
      }
    } catch (error) {
      toast({
        title: 'Analysis Failed',
        description: error.message || 'Failed to analyze policy',
        variant: 'destructive',
      });
    }
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
            {row.created_date ? format(new Date(row.created_date), 'MMM d, yyyy') : '-'}
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
                accept=".pdf,.docx,.txt"
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
              disabled={!newPolicy.file_name || createPolicyMutation.isPending}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {createPolicyMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Policy'
              )}
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
                    {selectedPolicy.created_date 
                      ? format(new Date(selectedPolicy.created_date), 'MMM d, yyyy HH:mm')
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