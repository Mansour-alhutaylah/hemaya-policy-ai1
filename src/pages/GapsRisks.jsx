import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { api } from '@/api/apiClient';
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
import { useToast } from '@/components/ui/use-toast';
import {
  AlertTriangle,
  Search,
  Filter,
  Edit,
  Shield,
  User,
  ArrowUpCircle,
  ArrowDownCircle,
  Minus,
  FileText,
  ArrowUpDown,
  Flame,
} from 'lucide-react';
import { SEVERITY_COLORS, getSeverityColor } from '@/components/charts/severityColors';
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

const Gap = api.entities.Gap;
const Policy = api.entities.Policy;
const AuditLog = api.entities.AuditLog;

// Severity tints — text/border tints stay here (badge styling); chart and
// accent colours come from the shared token module so the dashboard, gaps
// page, and any future chart pages all agree on the palette.
const severityConfig = {
  Critical: {
    color:
      'bg-red-100 text-red-700 border-red-200 ' +
      'dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30',
    chartColor: SEVERITY_COLORS.Critical,
    accent:     SEVERITY_COLORS.Critical,
    icon: ArrowUpCircle,
  },
  High: {
    color:
      'bg-orange-100 text-orange-700 border-orange-200 ' +
      'dark:bg-orange-500/15 dark:text-orange-300 dark:border-orange-500/30',
    chartColor: SEVERITY_COLORS.High,
    accent:     SEVERITY_COLORS.High,
    icon: ArrowUpCircle,
  },
  Medium: {
    color:
      'bg-amber-100 text-amber-700 border-amber-200 ' +
      'dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30',
    chartColor: SEVERITY_COLORS.Medium,
    accent:     SEVERITY_COLORS.Medium,
    icon: Minus,
  },
  Low: {
    color:
      'bg-green-100 text-green-700 border-green-200 ' +
      'dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30',
    chartColor: SEVERITY_COLORS.Low,
    accent:     SEVERITY_COLORS.Low,
    icon: ArrowDownCircle,
  },
};

// Phase E.2: priority score = severity weight × age factor.
// Severity weights mirror the dashboard's top-risky-controls SQL
// (Critical=4 / High=3 / Medium=2 / Low=1). Age factor grows from
// 1 (new gap) to a cap of 3 (90+ days old) so a long-open Medium can
// still outrank a fresh Low. Returns an integer 0-100ish for display.
const SEVERITY_WEIGHT = { Critical: 4, High: 3, Medium: 2, Low: 1 };
function computePriority(gap) {
  const sev = SEVERITY_WEIGHT[gap.severity] || 1;
  let ageFactor = 1;
  if (gap.created_at) {
    const days = Math.max(0, (Date.now() - new Date(gap.created_at).getTime()) / 86400000);
    ageFactor = Math.min(3, 1 + days / 30);
  }
  // Closed gaps get a baseline so they sort to the bottom by default.
  if (gap.status && gap.status !== 'Open') return 0;
  return Math.round(sev * ageFactor * 8); // tuned to land in ~0-100 range
}

// KPI card matching the Executive Dashboard pattern: dark card surface with
// a thin left accent stripe, a tinted icon container, and theme-token text.
// Kept local because the Dashboard's KpiCard has a slightly different shape
// (trend chips, skeleton variants) we don't need here.
function KpiCard({ title, value, icon: Icon, accentColor }) {
  return (
    <div
      className="bg-card rounded-2xl border border-border shadow-sm hover:shadow-md transition-shadow duration-200 p-5 flex flex-col gap-4"
      style={{ borderLeftWidth: 3, borderLeftColor: accentColor }}
    >
      <div className="flex items-start justify-between">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: `${accentColor}26` }}
        >
          <Icon className="w-4 h-4" style={{ color: accentColor }} />
        </div>
      </div>
      <div>
        <p className="text-2xl font-bold tracking-tight text-foreground leading-none">{value}</p>
        <p className="text-sm font-medium text-muted-foreground mt-1.5">{title}</p>
      </div>
    </div>
  );
}

// Dashboard-style colored icon container for chart-card titles.
function CardIcon({ children, className }) {
  return (
    <div
      className={`w-7 h-7 rounded-lg flex items-center justify-center ${className || ''}`}
    >
      {children}
    </div>
  );
}

export default function GapsRisks() {
  const [searchQuery, setSearchQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('priority'); // priority | severity | recent
  const [selectedGap, setSelectedGap] = useState(null);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editForm, setEditForm] = useState({
    status: '',
    owner: '',
    remediation: '',
  });

  const { toast } = useToast();
  const queryClient = useQueryClient();

  // ── Phase 4: read severity from URL (?severity=High etc.) ────────────────
  const [searchParams] = useSearchParams();
  const policyIdFilter = searchParams.get('policy_id');

  useEffect(() => {
    const sv = searchParams.get('severity');
    if (sv) setSeverityFilter(sv);
  }, [searchParams]);

  const { data: gaps = [], isLoading } = useQuery({
    queryKey: ['gaps'],
    queryFn: () => Gap.list('-created_at'),
  });

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list(),
  });

  const policyMap = policies.reduce((acc, p) => {
    acc[p.id] = p;
    return acc;
  }, {});

  const updateGapMutation = useMutation({
    // Phase G.1: routed through apiClient so 401 handling and FastAPI error
    // parsing match the rest of the app.
    mutationFn: ({ id, data }) => api.put(`/gaps/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gaps'] });
      queryClient.invalidateQueries({ queryKey: ['dashboardStats'] });
      toast({ title: 'Gap Updated', description: 'Gap details have been updated successfully.' });
      setShowEditDialog(false);
    },
    onError: (err) => toast({ title: 'Update failed', description: err.message, variant: 'destructive' }),
  });

  const filteredGaps = gaps
    .filter(gap => {
      const matchesSearch = gap.control_id?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        gap.control_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        gap.description?.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesSeverity = severityFilter === 'all' || gap.severity === severityFilter;
      const matchesStatus = statusFilter === 'all' || gap.status === statusFilter;
      const matchesPolicyId = !policyIdFilter || gap.policy_id === policyIdFilter;
      return matchesSearch && matchesSeverity && matchesStatus && matchesPolicyId;
    })
    .map(g => ({ ...g, _priority: computePriority(g) }))
    .sort((a, b) => {
      if (sortBy === 'priority') return b._priority - a._priority;
      if (sortBy === 'severity') {
        return (SEVERITY_WEIGHT[b.severity] || 0) - (SEVERITY_WEIGHT[a.severity] || 0);
      }
      // recent
      const at = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bt = b.created_at ? new Date(b.created_at).getTime() : 0;
      return bt - at;
    });

  // Calculate stats
  const criticalCount = gaps.filter(g => g.severity === 'Critical' && g.status === 'Open').length;
  const highCount = gaps.filter(g => g.severity === 'High' && g.status === 'Open').length;
  const openCount = gaps.filter(g => g.status === 'Open').length;
  const overdueCount = 0; // due_date not in schema

  // Chart data
  const severityDistribution = [
    { name: 'Critical', value: gaps.filter(g => g.severity === 'Critical').length, color: '#ef4444' },
    { name: 'High', value: gaps.filter(g => g.severity === 'High').length, color: '#f97316' },
    { name: 'Medium', value: gaps.filter(g => g.severity === 'Medium').length, color: '#f59e0b' },
    { name: 'Low', value: gaps.filter(g => g.severity === 'Low').length, color: '#22c55e' },
  ].filter(d => d.value > 0);

  const statusDistribution = [
    { name: 'Open', value: gaps.filter(g => g.status === 'Open').length },
    { name: 'In Progress', value: gaps.filter(g => g.status === 'In Progress').length },
    { name: 'Resolved', value: gaps.filter(g => g.status === 'Resolved').length },
    { name: 'Deferred', value: gaps.filter(g => g.status === 'Deferred').length },
  ];

  const handleEdit = (gap) => {
    setSelectedGap(gap);
    setEditForm({
      status:     gap.status     || 'Open',
      owner:      gap.owner_name || '',
      remediation: gap.remediation || '',
    });
    setShowEditDialog(true);
  };

  const handleSubmitEdit = () => {
    updateGapMutation.mutate({
      id: selectedGap.id,
      data: {
        status:     editForm.status,
        owner_name: editForm.owner,
        remediation: editForm.remediation,
      },
    });
  };

  const SeverityBadge = ({ severity }) => {
    const config = severityConfig[severity] || severityConfig.Medium;
    const Icon = config.icon;
    return (
      <Badge className={`${config.color} border gap-1`}>
        <Icon className="w-3 h-3" />
        {severity}
      </Badge>
    );
  };

  const PriorityBadge = ({ score }) => {
    const tone =
      score >= 60 ? 'bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30' :
      score >= 30 ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30' :
      score > 0   ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30' :
                    'bg-muted text-muted-foreground border-border/60';
    return (
      <Badge className={`${tone} border gap-1 tabular-nums`}>
        <Flame className="w-3 h-3" />
        {score}
      </Badge>
    );
  };

  const columns = [
    {
      header: 'Priority',
      accessor: '_priority',
      cell: (row) => <PriorityBadge score={row._priority} />,
    },
    {
      header: 'Control',
      accessor: 'control_id',
      cell: (row) => (
        <div>
          <Badge variant="outline" className="font-mono text-xs">
            {row.control_id}
          </Badge>
          <p className="text-sm text-muted-foreground mt-1">{row.control_name}</p>
        </div>
      ),
    },
    {
      header: 'Framework',
      accessor: 'framework',
      cell: (row) => (
        <Badge className="bg-muted text-foreground border border-border/60 hover:bg-muted">
          <Shield className="w-3 h-3 mr-1" />
          {row.framework}
        </Badge>
      ),
    },
    {
      header: 'Severity',
      accessor: 'severity',
      cell: (row) => <SeverityBadge severity={row.severity} />,
    },
    {
      header: 'Status',
      accessor: 'status',
      cell: (row) => <StatusBadge status={row.status || 'Open'} />,
    },
    {
      header: 'Owner',
      accessor: 'owner_name',
      cell: (row) => (
        <span className="text-sm text-muted-foreground">{row.owner_name || 'Unassigned'}</span>
      ),
    },
    {
      header: 'Description',
      accessor: 'description',
      cell: (row) => (
        <p className="text-xs text-muted-foreground line-clamp-2 max-w-xs">{row.description || '—'}</p>
      ),
    },
    {
      header: '',
      accessor: 'actions',
      cell: (row) => (
        <Button variant="ghost" size="sm" onClick={() => handleEdit(row)}>
          <Edit className="w-4 h-4 mr-1" />
          Edit
        </Button>
      ),
    },
  ];

  return (
    <PageContainer
      title="Gaps & Risks"
      subtitle="Track and manage compliance gaps and risk remediation"
    >
      {/* Stats Cards — match Executive Dashboard KpiCard pattern */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <KpiCard
          title="Critical Gaps"
          value={criticalCount}
          icon={AlertTriangle}
          accentColor="#ef4444"
        />
        <KpiCard
          title="High Priority"
          value={highCount}
          icon={AlertTriangle}
          accentColor="#f97316"
        />
        <KpiCard
          title="Open Gaps"
          value={openCount}
          icon={AlertTriangle}
          accentColor="#f59e0b"
        />
        <KpiCard
          title="In Progress"
          value={gaps.filter(g => g.status === 'In Progress').length}
          icon={AlertTriangle}
          accentColor="#3b82f6"
        />
      </div>

      {/* Charts Row — Dashboard-style chart cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <Card className="shadow-sm">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base font-semibold flex items-center gap-2.5 text-foreground">
              <CardIcon className="bg-amber-50 dark:bg-amber-500/15">
                <AlertTriangle className="w-4 h-4 text-amber-500 dark:text-amber-400" />
              </CardIcon>
              Severity Distribution
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-5">
            {severityDistribution.length > 0 ? (
              <div className="flex items-center">
                <ResponsiveContainer width="50%" height={200}>
                  <PieChart>
                    <Pie
                      data={severityDistribution}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={80}
                      dataKey="value"
                    >
                      {severityDistribution.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'hsl(var(--popover))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: 'calc(var(--radius) - 2px)',
                        color: 'hsl(var(--popover-foreground))',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-2">
                  {severityDistribution.map((item, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />
                      <span className="text-sm text-muted-foreground flex-1">{item.name}</span>
                      <span className="text-sm font-semibold text-foreground tabular-nums">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="h-48 flex items-center justify-center text-muted-foreground text-sm">
                No gap data available
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base font-semibold flex items-center gap-2.5 text-foreground">
              <CardIcon className="bg-blue-50 dark:bg-blue-500/15">
                <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              </CardIcon>
              Status Overview
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-5">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={statusDistribution} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  cursor={{ fill: 'rgba(148,163,184,0.12)', radius: 4 }}
                  contentStyle={{
                    backgroundColor: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: 'calc(var(--radius) - 2px)',
                    color: 'hsl(var(--popover-foreground))',
                  }}
                />
                <Bar dataKey="value" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search gaps..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={severityFilter} onValueChange={setSeverityFilter}>
          <SelectTrigger className="w-36">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Severity</SelectItem>
            <SelectItem value="Critical">Critical</SelectItem>
            <SelectItem value="High">High</SelectItem>
            <SelectItem value="Medium">Medium</SelectItem>
            <SelectItem value="Low">Low</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-36">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="Open">Open</SelectItem>
            <SelectItem value="In Progress">In Progress</SelectItem>
            <SelectItem value="Resolved">Resolved</SelectItem>
            <SelectItem value="Deferred">Deferred</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sortBy} onValueChange={setSortBy}>
          <SelectTrigger className="w-44">
            <ArrowUpDown className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Sort by" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="priority">Sort: Priority</SelectItem>
            <SelectItem value="severity">Sort: Severity</SelectItem>
            <SelectItem value="recent">Sort: Most recent</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={filteredGaps}
        isLoading={isLoading}
        emptyState={
          <EmptyState
            icon={AlertTriangle}
            title="No gaps found"
            description="Run a compliance analysis to identify gaps in your policies"
          />
        }
      />

      {/* Edit Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Edit className="w-5 h-5 text-emerald-600" />
              Update Gap
            </DialogTitle>
          </DialogHeader>

          {selectedGap && (
            <div className="space-y-4 py-4">
              {/* Gap Info */}
              <div className="bg-muted/50 border border-border/60 rounded-lg p-4 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline" className="font-mono">
                    {selectedGap.control_id}
                  </Badge>
                  <SeverityBadge severity={selectedGap.severity} />
                </div>
                <p className="text-sm font-medium">{selectedGap.control_name}</p>
                {selectedGap.description && (
                  <div>
                    <p className="text-xs font-semibold text-red-600 dark:text-red-400 mb-0.5">Gap identified:</p>
                    <p className="text-sm text-muted-foreground">{selectedGap.description}</p>
                  </div>
                )}
              </div>

              {/* Status */}
              <div className="space-y-2">
                <Label>Status</Label>
                <Select 
                  value={editForm.status} 
                  onValueChange={(value) => setEditForm(prev => ({ ...prev, status: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Open">Open</SelectItem>
                    <SelectItem value="In Progress">In Progress</SelectItem>
                    <SelectItem value="Resolved">Resolved</SelectItem>
                    <SelectItem value="Deferred">Deferred</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Owner */}
              <div className="space-y-2">
                <Label>Assigned Owner</Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Enter owner name or email"
                    value={editForm.owner}
                    onChange={(e) => setEditForm(prev => ({ ...prev, owner: e.target.value }))}
                    className="pl-10"
                  />
                </div>
              </div>

              {/* Remediation */}
              <div className="space-y-2">
                <Label>Remediation Plan</Label>
                <Textarea
                  placeholder="Describe the remediation steps to close this gap..."
                  value={editForm.remediation}
                  onChange={(e) => setEditForm(prev => ({ ...prev, remediation: e.target.value }))}
                  rows={4}
                />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleSubmitEdit}
              disabled={updateGapMutation.isPending}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              Save Changes
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}