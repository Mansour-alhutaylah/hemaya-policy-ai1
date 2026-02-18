import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import PageContainer from '@/components/layout/PageContainer';
import DataTable from '@/components/ui/DataTable';
import StatusBadge from '@/components/ui/StatusBadge';
import EmptyState from '@/components/ui/EmptyState';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
} from '@/components/ui/dialog';
import {
  BarChart3,
  Search,
  Filter,
  Eye,
  Shield,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ArrowRight
} from 'lucide-react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid
} from 'recharts';

const ComplianceResult = base44.entities.ComplianceResult;
const Policy = base44.entities.Policy;

export default function Analyses() {
  const [searchQuery, setSearchQuery] = useState('');
  const [frameworkFilter, setFrameworkFilter] = useState('all');
  const [selectedResult, setSelectedResult] = useState(null);
  const [showDetailDialog, setShowDetailDialog] = useState(false);

  const urlParams = new URLSearchParams(window.location.search);
  const policyIdFilter = urlParams.get('policy_id');

  const { data: results = [], isLoading: resultsLoading } = useQuery({
    queryKey: ['complianceResults'],
    queryFn: () => ComplianceResult.list('-analyzed_at'),
  });

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list(),
  });

  const policyMap = policies.reduce((acc, p) => {
    acc[p.id] = p;
    return acc;
  }, {});

  const filteredResults = results.filter(result => {
    const policy = policyMap[result.policy_id];
    const matchesSearch = policy?.file_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      result.framework?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFramework = frameworkFilter === 'all' || result.framework === frameworkFilter;
    const matchesPolicyId = !policyIdFilter || result.policy_id === policyIdFilter;
    return matchesSearch && matchesFramework && matchesPolicyId;
  });

  const handleViewDetails = (result) => {
    setSelectedResult(result);
    setShowDetailDialog(true);
  };

  const getScoreColor = (score) => {
    if (score >= 80) return 'text-emerald-600';
    if (score >= 60) return 'text-amber-600';
    return 'text-red-600';
  };

  const getScoreBg = (score) => {
    if (score >= 80) return 'bg-emerald-50';
    if (score >= 60) return 'bg-amber-50';
    return 'bg-red-50';
  };

  const columns = [
    {
      header: 'Policy',
      accessor: 'policy_id',
      cell: (row) => {
        const policy = policyMap[row.policy_id];
        return (
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="font-medium text-slate-900">{policy?.file_name || 'Unknown Policy'}</p>
              <p className="text-xs text-slate-500">ID: {row.policy_id}</p>
            </div>
          </div>
        );
      },
    },
    {
      header: 'Framework',
      accessor: 'framework',
      cell: (row) => (
        <Badge variant="outline" className="font-medium">
          <Shield className="w-3 h-3 mr-1" />
          {row.framework}
        </Badge>
      ),
    },
    {
      header: 'Compliance Score',
      accessor: 'compliance_score',
      cell: (row) => (
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg ${getScoreBg(row.compliance_score)}`}>
          <span className={`text-lg font-bold ${getScoreColor(row.compliance_score)}`}>
            {Math.round(row.compliance_score || 0)}%
          </span>
        </div>
      ),
    },
    {
      header: 'Controls',
      accessor: 'controls',
      cell: (row) => (
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            <span className="text-sm font-medium">{row.controls_covered || 0}</span>
          </div>
          <div className="flex items-center gap-1">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            <span className="text-sm font-medium">{row.controls_partial || 0}</span>
          </div>
          <div className="flex items-center gap-1">
            <XCircle className="w-4 h-4 text-red-500" />
            <span className="text-sm font-medium">{row.controls_missing || 0}</span>
          </div>
        </div>
      ),
    },
    {
      header: 'Status',
      accessor: 'status',
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      header: 'Analyzed',
      accessor: 'analyzed_at',
      cell: (row) => (
        <span className="text-sm text-slate-600">
          {row.analyzed_at ? format(new Date(row.analyzed_at), 'MMM d, yyyy HH:mm') : '-'}
        </span>
      ),
    },
    {
      header: '',
      accessor: 'actions',
      cell: (row) => (
        <Button variant="ghost" size="sm" onClick={() => handleViewDetails(row)}>
          <Eye className="w-4 h-4 mr-1" />
          Details
        </Button>
      ),
    },
  ];

  // Prepare chart data for selected result
  const getControlsChartData = (result) => {
    if (!result) return [];
    return [
      { name: 'Covered', value: result.controls_covered || 0, color: '#10b981' },
      { name: 'Partial', value: result.controls_partial || 0, color: '#f59e0b' },
      { name: 'Missing', value: result.controls_missing || 0, color: '#ef4444' },
    ];
  };

  return (
    <PageContainer
      title="Compliance Analyses"
      subtitle="View and manage compliance analysis results"
      actions={
        <Link to={createPageUrl('Policies')}>
          <Button className="bg-emerald-600 hover:bg-emerald-700">
            Run New Analysis
          </Button>
        </Link>
      }
    >
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search by policy or framework..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={frameworkFilter} onValueChange={setFrameworkFilter}>
          <SelectTrigger className="w-48">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Framework" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Frameworks</SelectItem>
            <SelectItem value="NCA ECC">NCA ECC</SelectItem>
            <SelectItem value="ISO 27001">ISO 27001</SelectItem>
            <SelectItem value="NIST 800-53">NIST 800-53</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={filteredResults}
        isLoading={resultsLoading}
        emptyState={
          <EmptyState
            icon={BarChart3}
            title="No analysis results"
            description="Run your first compliance analysis to see results here"
            action={() => window.location.href = createPageUrl('Policies')}
            actionLabel="Go to Policies"
          />
        }
      />

      {/* Detail Dialog */}
      <Dialog open={showDetailDialog} onOpenChange={setShowDetailDialog}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-emerald-600" />
              Analysis Details
            </DialogTitle>
          </DialogHeader>

          {selectedResult && (
            <div className="space-y-6 py-4">
              {/* Summary Cards */}
              <div className="grid grid-cols-3 gap-4">
                <Card className="bg-emerald-50 border-emerald-200">
                  <CardContent className="p-4 text-center">
                    <CheckCircle2 className="w-6 h-6 text-emerald-600 mx-auto mb-2" />
                    <p className="text-2xl font-bold text-emerald-700">{selectedResult.controls_covered || 0}</p>
                    <p className="text-xs text-emerald-600">Covered</p>
                  </CardContent>
                </Card>
                <Card className="bg-amber-50 border-amber-200">
                  <CardContent className="p-4 text-center">
                    <AlertTriangle className="w-6 h-6 text-amber-600 mx-auto mb-2" />
                    <p className="text-2xl font-bold text-amber-700">{selectedResult.controls_partial || 0}</p>
                    <p className="text-xs text-amber-600">Partial</p>
                  </CardContent>
                </Card>
                <Card className="bg-red-50 border-red-200">
                  <CardContent className="p-4 text-center">
                    <XCircle className="w-6 h-6 text-red-600 mx-auto mb-2" />
                    <p className="text-2xl font-bold text-red-700">{selectedResult.controls_missing || 0}</p>
                    <p className="text-xs text-red-600">Missing</p>
                  </CardContent>
                </Card>
              </div>

              {/* Score & Chart */}
              <div className="flex items-center gap-8">
                <div className="flex-1">
                  <div className="text-center">
                    <div className={`inline-flex items-center justify-center w-32 h-32 rounded-full ${getScoreBg(selectedResult.compliance_score)}`}>
                      <div>
                        <p className={`text-4xl font-bold ${getScoreColor(selectedResult.compliance_score)}`}>
                          {Math.round(selectedResult.compliance_score || 0)}%
                        </p>
                        <p className="text-xs text-slate-500">Compliance</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="flex-1">
                  <ResponsiveContainer width="100%" height={160}>
                    <PieChart>
                      <Pie
                        data={getControlsChartData(selectedResult)}
                        cx="50%"
                        cy="50%"
                        innerRadius={40}
                        outerRadius={60}
                        dataKey="value"
                      >
                        {getControlsChartData(selectedResult).map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Details */}
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-slate-500">Framework</p>
                  <p className="font-medium">{selectedResult.framework}</p>
                </div>
                <div>
                  <p className="text-slate-500">Status</p>
                  <StatusBadge status={selectedResult.status} />
                </div>
                <div>
                  <p className="text-slate-500">Policy</p>
                  <p className="font-medium">{policyMap[selectedResult.policy_id]?.file_name || selectedResult.policy_id}</p>
                </div>
                <div>
                  <p className="text-slate-500">Analyzed At</p>
                  <p className="font-medium">
                    {selectedResult.analyzed_at 
                      ? format(new Date(selectedResult.analyzed_at), 'MMM d, yyyy HH:mm')
                      : '-'}
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-between">
            <Link to={createPageUrl(`MappingReview?policy_id=${selectedResult?.policy_id}`)}>
              <Button variant="outline">
                Review Mappings
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
            <Link to={createPageUrl(`GapsRisks?policy_id=${selectedResult?.policy_id}`)}>
              <Button className="bg-emerald-600 hover:bg-emerald-700">
                View Gaps
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
          </div>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}