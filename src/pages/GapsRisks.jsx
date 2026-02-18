import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import PageContainer from '@/components/layout/PageContainer';
import DataTable from '@/components/ui/DataTable';
import StatusBadge from '@/components/ui/StatusBadge';
import EmptyState from '@/components/ui/EmptyState';
import StatsCard from '@/components/ui/StatsCard';
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
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useToast } from '@/components/ui/use-toast';
import {
  AlertTriangle,
  Search,
  Filter,
  Edit,
  Shield,
  Calendar as CalendarIcon,
  User,
  ArrowUpCircle,
  ArrowDownCircle,
  Minus
} from 'lucide-react';
import { format } from 'date-fns';
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

const Gap = base44.entities.Gap;
const Policy = base44.entities.Policy;
const AuditLog = base44.entities.AuditLog;

const severityConfig = {
  Critical: { color: 'bg-red-100 text-red-700 border-red-200', chartColor: '#ef4444', icon: ArrowUpCircle },
  High: { color: 'bg-orange-100 text-orange-700 border-orange-200', chartColor: '#f97316', icon: ArrowUpCircle },
  Medium: { color: 'bg-amber-100 text-amber-700 border-amber-200', chartColor: '#f59e0b', icon: Minus },
  Low: { color: 'bg-green-100 text-green-700 border-green-200', chartColor: '#22c55e', icon: ArrowDownCircle },
};

export default function GapsRisks() {
  const [searchQuery, setSearchQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedGap, setSelectedGap] = useState(null);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editForm, setEditForm] = useState({
    status: '',
    owner: '',
    due_date: null,
    remediation_notes: '',
  });

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const urlParams = new URLSearchParams(window.location.search);
  const policyIdFilter = urlParams.get('policy_id');

  const { data: gaps = [], isLoading } = useQuery({
    queryKey: ['gaps'],
    queryFn: () => Gap.list('-created_date'),
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
    mutationFn: ({ id, data }) => Gap.update(id, data),
    onSuccess: async (_, variables) => {
      queryClient.invalidateQueries(['gaps']);
      await AuditLog.create({
        actor: 'Current User',
        action: 'gap_update',
        target_type: 'gap',
        target_id: variables.id,
        details: `Updated gap status to: ${variables.data.status}`,
      });
      toast({
        title: 'Gap Updated',
        description: 'Gap details have been updated successfully.',
      });
      setShowEditDialog(false);
    },
  });

  const filteredGaps = gaps.filter(gap => {
    const matchesSearch = gap.control_id?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      gap.control_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      gap.description?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesSeverity = severityFilter === 'all' || gap.severity === severityFilter;
    const matchesStatus = statusFilter === 'all' || gap.status === statusFilter;
    const matchesPolicyId = !policyIdFilter || gap.policy_id === policyIdFilter;
    return matchesSearch && matchesSeverity && matchesStatus && matchesPolicyId;
  });

  // Calculate stats
  const criticalCount = gaps.filter(g => g.severity === 'Critical' && g.status === 'Open').length;
  const highCount = gaps.filter(g => g.severity === 'High' && g.status === 'Open').length;
  const openCount = gaps.filter(g => g.status === 'Open').length;
  const overdueCount = gaps.filter(g => g.due_date && new Date(g.due_date) < new Date() && g.status !== 'Resolved').length;

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
      status: gap.status || 'Open',
      owner: gap.owner || '',
      due_date: gap.due_date ? new Date(gap.due_date) : null,
      remediation_notes: gap.remediation_notes || '',
    });
    setShowEditDialog(true);
  };

  const handleSubmitEdit = () => {
    updateGapMutation.mutate({
      id: selectedGap.id,
      data: {
        ...editForm,
        due_date: editForm.due_date ? format(editForm.due_date, 'yyyy-MM-dd') : null,
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

  const columns = [
    {
      header: 'Control',
      accessor: 'control_id',
      cell: (row) => (
        <div>
          <Badge variant="outline" className="font-mono text-xs">
            {row.control_id}
          </Badge>
          <p className="text-sm text-slate-600 mt-1">{row.control_name}</p>
        </div>
      ),
    },
    {
      header: 'Framework',
      accessor: 'framework',
      cell: (row) => (
        <Badge className="bg-slate-100 text-slate-700">
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
      accessor: 'owner',
      cell: (row) => (
        <span className="text-sm text-slate-600">{row.owner || 'Unassigned'}</span>
      ),
    },
    {
      header: 'Due Date',
      accessor: 'due_date',
      cell: (row) => {
        if (!row.due_date) return <span className="text-slate-400">-</span>;
        const isOverdue = new Date(row.due_date) < new Date() && row.status !== 'Resolved';
        return (
          <span className={`text-sm ${isOverdue ? 'text-red-600 font-medium' : 'text-slate-600'}`}>
            {format(new Date(row.due_date), 'MMM d, yyyy')}
            {isOverdue && ' (Overdue)'}
          </span>
        );
      },
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
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <StatsCard
          title="Critical Gaps"
          value={criticalCount}
          icon={AlertTriangle}
          variant={criticalCount > 0 ? 'red' : 'default'}
        />
        <StatsCard
          title="High Priority"
          value={highCount}
          icon={AlertTriangle}
          variant={highCount > 0 ? 'amber' : 'default'}
        />
        <StatsCard
          title="Open Gaps"
          value={openCount}
          icon={AlertTriangle}
        />
        <StatsCard
          title="Overdue"
          value={overdueCount}
          icon={CalendarIcon}
          variant={overdueCount > 0 ? 'red' : 'default'}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Severity Distribution</CardTitle>
          </CardHeader>
          <CardContent>
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
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-2">
                  {severityDistribution.map((item, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
                      <span className="text-sm text-slate-600 flex-1">{item.name}</span>
                      <span className="text-sm font-medium">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="h-48 flex items-center justify-center text-slate-400">
                No gap data available
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Status Overview</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={statusDistribution}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
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
              <div className="bg-slate-50 rounded-lg p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="font-mono">
                    {selectedGap.control_id}
                  </Badge>
                  <SeverityBadge severity={selectedGap.severity} />
                </div>
                <p className="text-sm font-medium">{selectedGap.control_name}</p>
                {selectedGap.description && (
                  <p className="text-sm text-slate-600">{selectedGap.description}</p>
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
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <Input
                    placeholder="Enter owner name or email"
                    value={editForm.owner}
                    onChange={(e) => setEditForm(prev => ({ ...prev, owner: e.target.value }))}
                    className="pl-10"
                  />
                </div>
              </div>

              {/* Due Date */}
              <div className="space-y-2">
                <Label>Due Date</Label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="w-full justify-start text-left">
                      <CalendarIcon className="w-4 h-4 mr-2" />
                      {editForm.due_date 
                        ? format(editForm.due_date, 'PPP')
                        : 'Select date'}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0">
                    <Calendar
                      mode="single"
                      selected={editForm.due_date}
                      onSelect={(date) => setEditForm(prev => ({ ...prev, due_date: date }))}
                    />
                  </PopoverContent>
                </Popover>
              </div>

              {/* Notes */}
              <div className="space-y-2">
                <Label>Remediation Notes</Label>
                <Textarea
                  placeholder="Add notes about remediation progress..."
                  value={editForm.remediation_notes}
                  onChange={(e) => setEditForm(prev => ({ ...prev, remediation_notes: e.target.value }))}
                  rows={3}
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