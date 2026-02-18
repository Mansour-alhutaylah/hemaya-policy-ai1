import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import PageContainer from '@/components/layout/PageContainer';
import DataTable from '@/components/ui/DataTable';
import EmptyState from '@/components/ui/EmptyState';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  History,
  Search,
  Filter,
  Calendar as CalendarIcon,
  User,
  Upload,
  BarChart3,
  GitCompare,
  FileBarChart,
  AlertTriangle,
  Settings,
  LogIn,
  LogOut,
  Download
} from 'lucide-react';
import { format } from 'date-fns';

const AuditLog = base44.entities.AuditLog;

const actionConfig = {
  policy_upload: { icon: Upload, color: 'bg-blue-100 text-blue-700', label: 'Policy Upload' },
  policy_delete: { icon: AlertTriangle, color: 'bg-red-100 text-red-700', label: 'Policy Delete' },
  analysis_start: { icon: BarChart3, color: 'bg-purple-100 text-purple-700', label: 'Analysis Started' },
  analysis_complete: { icon: BarChart3, color: 'bg-emerald-100 text-emerald-700', label: 'Analysis Complete' },
  mapping_review: { icon: GitCompare, color: 'bg-indigo-100 text-indigo-700', label: 'Mapping Review' },
  report_generate: { icon: FileBarChart, color: 'bg-amber-100 text-amber-700', label: 'Report Generated' },
  gap_update: { icon: AlertTriangle, color: 'bg-orange-100 text-orange-700', label: 'Gap Update' },
  settings_change: { icon: Settings, color: 'bg-slate-100 text-slate-700', label: 'Settings Change' },
  user_login: { icon: LogIn, color: 'bg-green-100 text-green-700', label: 'User Login' },
  user_logout: { icon: LogOut, color: 'bg-slate-100 text-slate-700', label: 'User Logout' },
};

export default function AuditTrailPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [actionFilter, setActionFilter] = useState('all');
  const [dateRange, setDateRange] = useState({ from: null, to: null });

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['auditLogs'],
    queryFn: () => AuditLog.list('-created_date', 100),
  });

  // Generate sample logs if none exist
  const generateSampleLogs = () => {
    const now = new Date();
    return [
      {
        id: 'sample-1',
        actor: 'admin@company.com',
        action: 'policy_upload',
        target_type: 'policy',
        target_id: 'policy-001',
        details: 'Uploaded Security Policy v2.1',
        created_date: new Date(now - 1000 * 60 * 5).toISOString(),
      },
      {
        id: 'sample-2',
        actor: 'System',
        action: 'analysis_start',
        target_type: 'analysis',
        target_id: 'analysis-001',
        details: 'Started compliance analysis for Security Policy v2.1',
        created_date: new Date(now - 1000 * 60 * 10).toISOString(),
      },
      {
        id: 'sample-3',
        actor: 'System',
        action: 'analysis_complete',
        target_type: 'analysis',
        target_id: 'analysis-001',
        details: 'Completed analysis across 3 frameworks',
        created_date: new Date(now - 1000 * 60 * 15).toISOString(),
      },
      {
        id: 'sample-4',
        actor: 'compliance@company.com',
        action: 'mapping_review',
        target_type: 'mapping',
        target_id: 'mapping-001',
        details: 'Accepted mapping for control A.5.1.1',
        created_date: new Date(now - 1000 * 60 * 60).toISOString(),
      },
      {
        id: 'sample-5',
        actor: 'admin@company.com',
        action: 'gap_update',
        target_type: 'gap',
        target_id: 'gap-001',
        details: 'Updated gap status to In Progress, assigned to IT Security Team',
        created_date: new Date(now - 1000 * 60 * 120).toISOString(),
      },
      {
        id: 'sample-6',
        actor: 'admin@company.com',
        action: 'report_generate',
        target_type: 'report',
        target_id: 'report-001',
        details: 'Generated Executive Summary report (PDF)',
        created_date: new Date(now - 1000 * 60 * 180).toISOString(),
      },
      {
        id: 'sample-7',
        actor: 'compliance@company.com',
        action: 'user_login',
        target_type: 'user',
        target_id: 'user-002',
        details: 'User logged in from 192.168.1.100',
        created_date: new Date(now - 1000 * 60 * 240).toISOString(),
      },
    ];
  };

  const displayLogs = logs.length > 0 ? logs : generateSampleLogs();

  const filteredLogs = displayLogs.filter(log => {
    const matchesSearch = log.actor?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.details?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.target_id?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesAction = actionFilter === 'all' || log.action === actionFilter;
    
    // Date range filter
    if (dateRange.from && log.created_date) {
      const logDate = new Date(log.created_date);
      if (logDate < dateRange.from) return false;
    }
    if (dateRange.to && log.created_date) {
      const logDate = new Date(log.created_date);
      if (logDate > dateRange.to) return false;
    }
    
    return matchesSearch && matchesAction;
  });

  const handleExport = () => {
    // TODO: Implement actual CSV export
    const csvContent = filteredLogs.map(log => 
      `${log.created_date},${log.actor},${log.action},${log.details}`
    ).join('\n');
    
    const blob = new Blob([`Date,Actor,Action,Details\n${csvContent}`], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-trail-${format(new Date(), 'yyyy-MM-dd')}.csv`;
    a.click();
  };

  const columns = [
    {
      header: 'Timestamp',
      accessor: 'created_date',
      cell: (row) => (
        <div className="text-sm">
          <p className="font-medium text-slate-900">
            {row.created_date ? format(new Date(row.created_date), 'MMM d, yyyy') : '-'}
          </p>
          <p className="text-slate-500">
            {row.created_date ? format(new Date(row.created_date), 'HH:mm:ss') : '-'}
          </p>
        </div>
      ),
    },
    {
      header: 'Action',
      accessor: 'action',
      cell: (row) => {
        const config = actionConfig[row.action] || { 
          icon: History, 
          color: 'bg-slate-100 text-slate-700', 
          label: row.action 
        };
        const Icon = config.icon;
        return (
          <div className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-lg ${config.color} flex items-center justify-center`}>
              <Icon className="w-4 h-4" />
            </div>
            <span className="font-medium text-sm">{config.label}</span>
          </div>
        );
      },
    },
    {
      header: 'Actor',
      accessor: 'actor',
      cell: (row) => (
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center">
            <User className="w-4 h-4 text-slate-600" />
          </div>
          <span className="text-sm text-slate-600">{row.actor}</span>
        </div>
      ),
    },
    {
      header: 'Details',
      accessor: 'details',
      cell: (row) => (
        <p className="text-sm text-slate-600 max-w-md">{row.details}</p>
      ),
    },
    {
      header: 'Target',
      accessor: 'target_id',
      cell: (row) => (
        row.target_id ? (
          <Badge variant="outline" className="font-mono text-xs">
            {row.target_type}: {row.target_id}
          </Badge>
        ) : (
          <span className="text-slate-400">-</span>
        )
      ),
    },
  ];

  return (
    <PageContainer
      title="Audit Trail"
      subtitle="Immutable log of all system activities and user actions"
      actions={
        <Button variant="outline" onClick={handleExport}>
          <Download className="w-4 h-4 mr-2" />
          Export CSV
        </Button>
      }
    >
      {/* Info Banner */}
      <Card className="mb-6 bg-slate-50 border-slate-200">
        <CardContent className="p-4 flex items-center gap-3">
          <History className="w-5 h-5 text-slate-600" />
          <p className="text-sm text-slate-600">
            The audit trail provides an immutable record of all activities in the system. 
            Records cannot be modified or deleted to ensure compliance with regulatory requirements.
          </p>
        </CardContent>
      </Card>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search by actor or details..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        
        <Select value={actionFilter} onValueChange={setActionFilter}>
          <SelectTrigger className="w-48">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Action Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Actions</SelectItem>
            <SelectItem value="policy_upload">Policy Upload</SelectItem>
            <SelectItem value="policy_delete">Policy Delete</SelectItem>
            <SelectItem value="analysis_start">Analysis Start</SelectItem>
            <SelectItem value="analysis_complete">Analysis Complete</SelectItem>
            <SelectItem value="mapping_review">Mapping Review</SelectItem>
            <SelectItem value="report_generate">Report Generate</SelectItem>
            <SelectItem value="gap_update">Gap Update</SelectItem>
            <SelectItem value="user_login">User Login</SelectItem>
            <SelectItem value="user_logout">User Logout</SelectItem>
          </SelectContent>
        </Select>

        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-48 justify-start">
              <CalendarIcon className="w-4 h-4 mr-2" />
              {dateRange.from ? (
                dateRange.to ? (
                  `${format(dateRange.from, 'MMM d')} - ${format(dateRange.to, 'MMM d')}`
                ) : (
                  format(dateRange.from, 'MMM d, yyyy')
                )
              ) : (
                'Date Range'
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="range"
              selected={dateRange}
              onSelect={setDateRange}
              numberOfMonths={2}
            />
          </PopoverContent>
        </Popover>

        {(dateRange.from || dateRange.to) && (
          <Button 
            variant="ghost" 
            size="sm"
            onClick={() => setDateRange({ from: null, to: null })}
          >
            Clear dates
          </Button>
        )}
      </div>

      {/* Activity Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {['policy_upload', 'analysis_complete', 'mapping_review', 'report_generate'].map(action => {
          const config = actionConfig[action];
          const count = displayLogs.filter(l => l.action === action).length;
          const Icon = config.icon;
          return (
            <Card 
              key={action} 
              className="cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => setActionFilter(action)}
            >
              <CardContent className="p-4 flex items-center gap-3">
                <div className={`w-10 h-10 rounded-lg ${config.color} flex items-center justify-center`}>
                  <Icon className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{count}</p>
                  <p className="text-xs text-slate-500">{config.label}</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={filteredLogs}
        isLoading={isLoading}
        emptyState={
          <EmptyState
            icon={History}
            title="No audit logs found"
            description="System activities will be recorded here automatically"
          />
        }
      />
    </PageContainer>
  );
}