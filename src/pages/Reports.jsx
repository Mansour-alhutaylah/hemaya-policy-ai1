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
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
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
  Filter,
  FileText,
  FileSpreadsheet,
  FilePieChart,
  Loader2,
  Calendar,
  Shield
} from 'lucide-react';
import { format } from 'date-fns';

const Report = base44.entities.Report;
const Policy = base44.entities.Policy;
const AuditLog = base44.entities.AuditLog;

const reportTypeConfig = {
  'Executive Summary': { icon: FileText, color: 'bg-blue-100 text-blue-700' },
  'Detailed Analysis': { icon: FilePieChart, color: 'bg-purple-100 text-purple-700' },
  'Gap Report': { icon: FileBarChart, color: 'bg-amber-100 text-amber-700' },
  'Compliance Certificate': { icon: Shield, color: 'bg-emerald-100 text-emerald-700' },
};

export default function Reports() {
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [showGenerateDialog, setShowGenerateDialog] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [reportConfig, setReportConfig] = useState({
    policy_id: '',
    report_type: 'Executive Summary',
    format: 'PDF',
    frameworks_included: ['NCA ECC', 'ISO 27001', 'NIST 800-53'],
  });

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['reports'],
    queryFn: () => Report.list('-created_date'),
  });

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.filter({ status: 'analyzed' }),
  });

  const policyMap = policies.reduce((acc, p) => {
    acc[p.id] = p;
    return acc;
  }, {});

  const createReportMutation = useMutation({
    mutationFn: (reportData) => Report.create(reportData),
    onSuccess: async (newReport) => {
      queryClient.invalidateQueries(['reports']);
      await AuditLog.create({
        actor: 'Current User',
        action: 'report_generate',
        target_type: 'report',
        target_id: newReport.id,
        details: `Generated ${newReport.report_type} report`,
      });
      toast({
        title: 'Report Generated',
        description: 'Your report is ready for download.',
      });
      setShowGenerateDialog(false);
    },
  });

  const filteredReports = reports.filter(report => {
    const policy = policyMap[report.policy_id];
    const matchesSearch = policy?.file_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      report.report_type?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = typeFilter === 'all' || report.report_type === typeFilter;
    return matchesSearch && matchesType;
  });

  const toggleFramework = (framework) => {
    setReportConfig(prev => ({
      ...prev,
      frameworks_included: prev.frameworks_included.includes(framework)
        ? prev.frameworks_included.filter(f => f !== framework)
        : [...prev.frameworks_included, framework],
    }));
  };

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
      const result = await base44.functions.invoke('generate_report', {
        policy_id: reportConfig.policy_id,
        report_type: reportConfig.report_type,
        format: reportConfig.format,
        frameworks_included: reportConfig.frameworks_included,
      });

      if (result.success) {
        queryClient.invalidateQueries(['reports']);
        toast({
          title: 'Report Generated',
          description: 'Your report is ready for download.',
        });
        setShowGenerateDialog(false);
      }
    } catch (error) {
      toast({
        title: 'Generation Failed',
        description: error.message || 'Failed to generate report',
        variant: 'destructive',
      });
    }
    
    setGenerating(false);
  };

  const handleDownload = (report) => {
    // TODO: Implement actual download from backend
    toast({
      title: 'Download Started',
      description: `Downloading ${report.report_type}...`,
    });
  };

  const getFormatIcon = (format) => {
    switch (format) {
      case 'Excel':
        return <FileSpreadsheet className="w-4 h-4 text-green-600" />;
      case 'CSV':
        return <FileText className="w-4 h-4 text-slate-600" />;
      default:
        return <FileText className="w-4 h-4 text-red-600" />;
    }
  };

  const columns = [
    {
      header: 'Report',
      accessor: 'report_type',
      cell: (row) => {
        const config = reportTypeConfig[row.report_type] || reportTypeConfig['Executive Summary'];
        const Icon = config.icon;
        return (
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg ${config.color} flex items-center justify-center`}>
              <Icon className="w-5 h-5" />
            </div>
            <div>
              <p className="font-medium text-slate-900">{row.report_type}</p>
              <p className="text-xs text-slate-500">
                {policyMap[row.policy_id]?.file_name || 'Unknown Policy'}
              </p>
            </div>
          </div>
        );
      },
    },
    {
      header: 'Format',
      accessor: 'format',
      cell: (row) => (
        <div className="flex items-center gap-2">
          {getFormatIcon(row.format)}
          <span className="text-sm">{row.format}</span>
        </div>
      ),
    },
    {
      header: 'Frameworks',
      accessor: 'frameworks_included',
      cell: (row) => (
        <div className="flex flex-wrap gap-1">
          {(row.frameworks_included || []).map((fw) => (
            <Badge key={fw} variant="outline" className="text-xs">
              {fw.split(' ')[0]}
            </Badge>
          ))}
        </div>
      ),
    },
    {
      header: 'Generated',
      accessor: 'generated_at',
      cell: (row) => (
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <Calendar className="w-4 h-4" />
          {row.generated_at 
            ? format(new Date(row.generated_at), 'MMM d, yyyy HH:mm')
            : format(new Date(row.created_date), 'MMM d, yyyy HH:mm')}
        </div>
      ),
    },
    {
      header: 'Status',
      accessor: 'status',
      cell: (row) => <StatusBadge status={row.status || 'completed'} />,
    },
    {
      header: '',
      accessor: 'actions',
      cell: (row) => (
        <Button 
          variant="ghost" 
          size="sm" 
          onClick={() => handleDownload(row)}
          disabled={row.status === 'Generating'}
        >
          <Download className="w-4 h-4 mr-1" />
          Download
        </Button>
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
      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {Object.entries(reportTypeConfig).map(([type, config]) => {
          const Icon = config.icon;
          const count = reports.filter(r => r.report_type === type).length;
          return (
            <Card key={type} className="shadow-sm hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => setTypeFilter(type)}>
              <CardContent className="p-4 flex items-center gap-4">
                <div className={`w-10 h-10 rounded-lg ${config.color} flex items-center justify-center`}>
                  <Icon className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{count}</p>
                  <p className="text-xs text-slate-500">{type}</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search reports..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-48">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Report Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="Executive Summary">Executive Summary</SelectItem>
            <SelectItem value="Detailed Analysis">Detailed Analysis</SelectItem>
            <SelectItem value="Gap Report">Gap Report</SelectItem>
            <SelectItem value="Compliance Certificate">Compliance Certificate</SelectItem>
          </SelectContent>
        </Select>
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
      <Dialog open={showGenerateDialog} onOpenChange={setShowGenerateDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileBarChart className="w-5 h-5 text-emerald-600" />
              Generate Compliance Report
            </DialogTitle>
            <DialogDescription>
              Create a comprehensive compliance report for your analyzed policies
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Policy Selection */}
            <div className="space-y-2">
              <Label>Select Policy</Label>
              <Select 
                value={reportConfig.policy_id} 
                onValueChange={(value) => setReportConfig(prev => ({ ...prev, policy_id: value }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Choose an analyzed policy..." />
                </SelectTrigger>
                <SelectContent>
                  {policies.length === 0 ? (
                    <SelectItem value={null} disabled>No analyzed policies available</SelectItem>
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

            {/* Report Type */}
            <div className="space-y-2">
              <Label>Report Type</Label>
              <Select 
                value={reportConfig.report_type} 
                onValueChange={(value) => setReportConfig(prev => ({ ...prev, report_type: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Executive Summary">Executive Summary</SelectItem>
                  <SelectItem value="Detailed Analysis">Detailed Analysis</SelectItem>
                  <SelectItem value="Gap Report">Gap Report</SelectItem>
                  <SelectItem value="Compliance Certificate">Compliance Certificate</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Format */}
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
                  <SelectItem value="PDF">PDF Document</SelectItem>
                  <SelectItem value="Excel">Excel Spreadsheet</SelectItem>
                  <SelectItem value="CSV">CSV Export</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Frameworks */}
            <div className="space-y-2">
              <Label>Include Frameworks</Label>
              <div className="space-y-2">
                {['NCA ECC', 'ISO 27001', 'NIST 800-53'].map(framework => (
                  <div key={framework} className="flex items-center gap-2">
                    <Checkbox
                      id={framework}
                      checked={reportConfig.frameworks_included.includes(framework)}
                      onCheckedChange={() => toggleFramework(framework)}
                    />
                    <Label htmlFor={framework} className="font-normal cursor-pointer">
                      {framework}
                    </Label>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setShowGenerateDialog(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleGenerateReport}
              disabled={generating || !reportConfig.policy_id || reportConfig.frameworks_included.length === 0}
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