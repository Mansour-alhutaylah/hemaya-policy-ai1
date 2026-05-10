import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
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
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Brain
} from 'lucide-react';
import { format } from 'date-fns';
import { formatDateTime } from '@/lib/format';
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

const ComplianceResult = api.entities.ComplianceResult;
const Policy = api.entities.Policy;

export default function Analyses() {
  const [searchQuery, setSearchQuery] = useState('');
  const [frameworkFilter, setFrameworkFilter] = useState('all');
  const [selectedResult, setSelectedResult] = useState(null);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const [expandedControl, setExpandedControl] = useState(null);

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

  // Phase UI-7: memoised so the map only rebuilds when policies actually
  // changes — not on every search/filter keystroke.
  const policyMap = useMemo(
    () => policies.reduce((acc, p) => { acc[p.id] = p; return acc; }, {}),
    [policies],
  );

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
    if (score >= 80) return 'text-emerald-600 dark:text-emerald-400';
    if (score >= 60) return 'text-amber-600 dark:text-amber-400';
    return 'text-red-600 dark:text-red-400';
  };

  const getScoreBg = (score) => {
    if (score >= 80) return 'bg-emerald-50 dark:bg-emerald-500/10';
    if (score >= 60) return 'bg-amber-50 dark:bg-amber-500/10';
    return 'bg-red-50 dark:bg-red-500/10';
  };

  const columns = [
    {
      header: 'Policy',
      accessor: 'policy_id',
      cell: (row) => {
        const policy = policyMap[row.policy_id];
        return (
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 dark:bg-blue-500/10 flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="font-medium text-foreground">{policy?.file_name || 'Unknown Policy'}</p>
              <p className="text-xs text-muted-foreground">ID: {row.policy_id}</p>
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
            <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
            <span className="text-sm font-medium text-foreground">{row.controls_covered || 0}</span>
          </div>
          <div className="flex items-center gap-1">
            <AlertTriangle className="w-4 h-4 text-amber-500 dark:text-amber-400" />
            <span className="text-sm font-medium text-foreground">{row.controls_partial || 0}</span>
          </div>
          <div className="flex items-center gap-1">
            <XCircle className="w-4 h-4 text-red-500 dark:text-red-400" />
            <span className="text-sm font-medium text-foreground">{row.controls_missing || 0}</span>
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
        <span className="text-sm text-muted-foreground">
          {formatDateTime(row.analyzed_at)}
        </span>
      ),
    },
    {
      header: '',
      accessor: 'actions',
      cell: (row) => (
        <Button variant="ghost" size="sm" onClick={() => handleViewDetails(row)}>
          <Eye className="w-4 h-4 mr-1" />
          Open results
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
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
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
              <BarChart3 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              Analysis Details
            </DialogTitle>
          </DialogHeader>

          {selectedResult && (() => {
            const perControl = selectedResult.details?.per_control || [];
            const statusIcon = {
              Compliant:     <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 flex-shrink-0" />,
              Partial:       <AlertTriangle className="w-4 h-4 text-amber-500 dark:text-amber-400 flex-shrink-0" />,
              'Non-Compliant': <XCircle className="w-4 h-4 text-red-500 dark:text-red-400 flex-shrink-0" />,
            };
            return (
              <div className="space-y-5 py-2">
                {/* Summary Cards */}
                <div className="grid grid-cols-3 gap-3">
                  <Card className="bg-emerald-50 border-emerald-200 dark:bg-emerald-500/10 dark:border-emerald-500/30">
                    <CardContent className="p-3 text-center">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 mx-auto mb-1" />
                      <p className="text-xl font-bold text-emerald-700 dark:text-emerald-300">{selectedResult.controls_covered || 0}</p>
                      <p className="text-xs text-emerald-600 dark:text-emerald-400">Covered</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-amber-50 border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/30">
                    <CardContent className="p-3 text-center">
                      <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mx-auto mb-1" />
                      <p className="text-xl font-bold text-amber-700 dark:text-amber-300">{selectedResult.controls_partial || 0}</p>
                      <p className="text-xs text-amber-600 dark:text-amber-400">Partial</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-red-50 border-red-200 dark:bg-red-500/10 dark:border-red-500/30">
                    <CardContent className="p-3 text-center">
                      <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 mx-auto mb-1" />
                      <p className="text-xl font-bold text-red-700 dark:text-red-300">{selectedResult.controls_missing || 0}</p>
                      <p className="text-xs text-red-600 dark:text-red-400">Missing</p>
                    </CardContent>
                  </Card>
                </div>

                {/* Score + Pie */}
                <div className="flex items-center gap-6">
                  <div className="flex-1 text-center">
                    <div className={`inline-flex items-center justify-center w-28 h-28 rounded-full ${getScoreBg(selectedResult.compliance_score)}`}>
                      <div>
                        <p className={`text-3xl font-bold ${getScoreColor(selectedResult.compliance_score)}`}>
                          {Math.round(selectedResult.compliance_score || 0)}%
                        </p>
                        <p className="text-xs text-muted-foreground">Compliance</p>
                      </div>
                    </div>
                  </div>
                  <div className="flex-1">
                    <ResponsiveContainer width="100%" height={140}>
                      <PieChart>
                        <Pie data={getControlsChartData(selectedResult)} cx="50%" cy="50%" innerRadius={35} outerRadius={55} dataKey="value">
                          {getControlsChartData(selectedResult).map((entry, i) => (
                            <Cell key={i} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex-1 space-y-1 text-sm">
                    <div><p className="text-muted-foreground text-xs">Framework</p><p className="font-medium text-foreground">{selectedResult.framework}</p></div>
                    <div><p className="text-muted-foreground text-xs">Policy</p><p className="font-medium text-xs text-foreground">{policyMap[selectedResult.policy_id]?.file_name || '—'}</p></div>
                    <div><p className="text-muted-foreground text-xs">Analyzed</p><p className="font-medium text-xs text-foreground">{selectedResult.analyzed_at ? format(new Date(selectedResult.analyzed_at), 'MMM d HH:mm') : '—'}</p></div>
                  </div>
                </div>

                {/* Per-control breakdown */}
                {perControl.length > 0 && (
                  <div>
                    <p className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1">
                      <Brain className="w-4 h-4" /> Per-Control Breakdown ({perControl.length} controls)
                    </p>
                    <div className="border border-border rounded-lg overflow-hidden max-h-64 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-muted/50 sticky top-0">
                          <tr>
                            <th className="text-left py-2 px-3 font-semibold text-muted-foreground">Control</th>
                            <th className="text-center py-2 px-2 font-semibold text-muted-foreground">Status</th>
                            <th className="text-center py-2 px-2 font-semibold text-muted-foreground">Confidence</th>
                            <th className="text-left py-2 px-2 font-semibold text-muted-foreground">Evidence</th>
                          </tr>
                        </thead>
                        <tbody>
                          {perControl.map((ctrl, idx) => (
                            <React.Fragment key={idx}>
                              <tr
                                className="border-t border-border hover:bg-muted/40 cursor-pointer"
                                onClick={() => setExpandedControl(expandedControl === idx ? null : idx)}
                              >
                                <td className="py-2 px-3">
                                  <div className="flex items-center gap-1">
                                    {expandedControl === idx
                                      ? <ChevronDown className="w-3 h-3 text-muted-foreground" />
                                      : <ChevronRight className="w-3 h-3 text-muted-foreground" />}
                                    <span className="font-mono font-medium text-foreground">{ctrl.control_code}</span>
                                  </div>
                                  <p className="text-muted-foreground ml-4 line-clamp-1">{ctrl.control_title}</p>
                                </td>
                                <td className="py-2 px-2 text-center">
                                  <div className="flex items-center justify-center gap-1">
                                    {statusIcon[ctrl.status] || statusIcon['Non-Compliant']}
                                  </div>
                                </td>
                                <td className="py-2 px-2 text-center">
                                  <span className={`font-medium ${(ctrl.confidence || 0) >= 0.7 ? 'text-emerald-600 dark:text-emerald-400' : (ctrl.confidence || 0) >= 0.5 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400'}`}>
                                    {Math.round((ctrl.confidence || 0) * 100)}%
                                  </span>
                                </td>
                                <td className="py-2 px-2 text-muted-foreground max-w-xs">
                                  <p className="line-clamp-1">{ctrl.evidence || '—'}</p>
                                </td>
                              </tr>
                              {expandedControl === idx && (
                                <tr className="bg-muted/40">
                                  <td colSpan={4} className="px-4 py-3 text-xs">
                                    {ctrl.gaps && ctrl.gaps !== 'None' && (
                                      <div className="mb-2">
                                        <p className="font-semibold text-red-600 dark:text-red-400 mb-0.5">Gaps:</p>
                                        <p className="text-muted-foreground">{ctrl.gaps}</p>
                                      </div>
                                    )}
                                    {ctrl.rationale && (
                                      <div className="mb-2">
                                        <p className="font-semibold text-foreground mb-0.5">Rationale:</p>
                                        <p className="text-muted-foreground">{ctrl.rationale}</p>
                                      </div>
                                    )}
                                    {ctrl.recommendation && ctrl.recommendation !== 'None needed' && (
                                      <div>
                                        <p className="font-semibold text-emerald-700 dark:text-emerald-400 mb-0.5">Recommendation:</p>
                                        <p className="text-muted-foreground">{ctrl.recommendation}</p>
                                      </div>
                                    )}
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            );
          })()}

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