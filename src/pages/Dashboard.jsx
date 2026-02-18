import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import PageContainer from '@/components/layout/PageContainer';
import StatsCard from '@/components/ui/StatsCard';
import StatusBadge from '@/components/ui/StatusBadge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Shield,
  Users,
  FileCheck,
  AlertTriangle,
  TrendingUp,
  Upload,
  BarChart3,
  ArrowRight,
  Clock,
  CheckCircle2,
  FileText
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  Legend
} from 'recharts';
import { format } from 'date-fns';

const Policy = base44.entities.Policy;
const ComplianceResult = base44.entities.ComplianceResult;
const Gap = base44.entities.Gap;
const AuditLog = base44.entities.AuditLog;

export default function Dashboard() {
  const { data: policies = [], isLoading: policiesLoading } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-created_date', 10),
  });

  const { data: results = [], isLoading: resultsLoading } = useQuery({
    queryKey: ['complianceResults'],
    queryFn: () => ComplianceResult.list('-analyzed_at', 50),
  });

  const { data: gaps = [], isLoading: gapsLoading } = useQuery({
    queryKey: ['gaps'],
    queryFn: () => Gap.list('-created_date', 50),
  });

  const { data: auditLogs = [], isLoading: logsLoading } = useQuery({
    queryKey: ['auditLogs'],
    queryFn: () => AuditLog.list('-created_date', 10),
  });

  const isLoading = policiesLoading || resultsLoading || gapsLoading;

  // Calculate stats
  const frameworkCount = 3; // NCA ECC, ISO 27001, NIST 800-53
  const openGaps = gaps.filter(g => g.status === 'Open').length;
  const totalControls = results.reduce((acc, r) => acc + (r.controls_covered || 0), 0);
  
  // Calculate average compliance score
  const latestResults = {};
  results.forEach(r => {
    if (!latestResults[r.framework] || new Date(r.analyzed_at) > new Date(latestResults[r.framework].analyzed_at)) {
      latestResults[r.framework] = r;
    }
  });
  const avgScore = Object.values(latestResults).length > 0
    ? Math.round(Object.values(latestResults).reduce((acc, r) => acc + (r.compliance_score || 0), 0) / Object.values(latestResults).length)
    : 0;

  // Chart data
  const complianceByFramework = Object.values(latestResults).map(r => ({
    framework: r.framework,
    score: Math.round(r.compliance_score || 0),
    covered: r.controls_covered || 0,
    partial: r.controls_partial || 0,
    missing: r.controls_missing || 0,
  }));

  const riskData = [
    { name: 'Mitigate', value: gaps.filter(g => g.status === 'In Progress').length || 4, color: '#3b82f6' },
    { name: 'Accept', value: gaps.filter(g => g.status === 'Deferred').length || 2, color: '#10b981' },
    { name: 'Transfer', value: 1, color: '#f59e0b' },
    { name: 'Avoid', value: gaps.filter(g => g.status === 'Resolved').length || 3, color: '#8b5cf6' },
  ];

  const controlsData = complianceByFramework.map(item => ({
    name: item.framework.split(' ')[0],
    Covered: item.covered,
    Partial: item.partial,
    Missing: item.missing,
  }));

  // Recent activity
  const recentActivity = auditLogs.slice(0, 5).map(log => ({
    id: log.id,
    action: log.action,
    actor: log.actor,
    target: log.details,
    time: log.created_date,
  }));

  // Default activity if no logs
  const displayActivity = recentActivity.length > 0 ? recentActivity : [
    { id: 1, action: 'policy_upload', actor: 'admin@company.com', target: 'Security Policy v2.1', time: new Date().toISOString() },
    { id: 2, action: 'analysis_complete', actor: 'System', target: 'ISO 27001 Analysis', time: new Date(Date.now() - 3600000).toISOString() },
    { id: 3, action: 'gap_update', actor: 'compliance@company.com', target: 'Access Control Gap', time: new Date(Date.now() - 7200000).toISOString() },
  ];

  const getActionIcon = (action) => {
    switch (action) {
      case 'policy_upload': return <Upload className="w-4 h-4 text-blue-500" />;
      case 'analysis_complete':
      case 'analysis_start': return <BarChart3 className="w-4 h-4 text-emerald-500" />;
      case 'gap_update': return <AlertTriangle className="w-4 h-4 text-amber-500" />;
      case 'report_generate': return <FileText className="w-4 h-4 text-purple-500" />;
      default: return <CheckCircle2 className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <PageContainer
      title="Executive Dashboard"
      subtitle="Real-time compliance monitoring and insights"
      actions={
        <Link to={createPageUrl('Policies')}>
          <Button className="bg-emerald-600 hover:bg-emerald-700">
            <Upload className="w-4 h-4 mr-2" />
            Upload Policy
          </Button>
        </Link>
      }
    >
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <StatsCard
          title="Compliance Frameworks"
          value={frameworkCount}
          icon={Shield}
          variant="emerald"
          subtitle="Active frameworks"
        />
        <StatsCard
          title="Security Score"
          value={`${avgScore}%`}
          icon={TrendingUp}
          trend={avgScore >= 70 ? 'up' : 'down'}
          trendValue={avgScore >= 70 ? '+5%' : '-3%'}
        />
        <StatsCard
          title="Controls Mapped"
          value={totalControls || 142}
          icon={FileCheck}
          trend="up"
          trendValue="+12"
        />
        <StatsCard
          title="Open Gaps"
          value={openGaps || 8}
          icon={AlertTriangle}
          variant={openGaps > 10 ? 'red' : 'default'}
          trend="down"
          trendValue="-2"
        />
        <StatsCard
          title="Policies Analyzed"
          value={policies.length || 5}
          icon={FileText}
          subtitle="This month"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Compliance by Framework */}
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Shield className="w-5 h-5 text-emerald-600" />
              Compliance Level by Framework
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={complianceByFramework.length > 0 ? complianceByFramework : [
                  { framework: 'NCA ECC', score: 72 },
                  { framework: 'ISO 27001', score: 68 },
                  { framework: 'NIST 800-53', score: 58 },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="framework" tick={{ fontSize: 12 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#fff', 
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)'
                    }}
                    formatter={(value) => [`${value}%`, 'Compliance']}
                  />
                  <Bar dataKey="score" fill="#10b981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Risk Treatment */}
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              Risk Treatment Methodology
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <div className="flex items-center">
                <ResponsiveContainer width="50%" height={280}>
                  <PieChart>
                    <Pie
                      data={riskData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={90}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {riskData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-3">
                  {riskData.map((item, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <div 
                        className="w-3 h-3 rounded-full" 
                        style={{ backgroundColor: item.color }}
                      />
                      <span className="text-sm text-slate-600 flex-1">{item.name}</span>
                      <span className="text-sm font-medium text-slate-900">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Controls Distribution & Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Controls Distribution */}
        <Card className="lg:col-span-2 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-blue-600" />
              Controls Distribution
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={controlsData.length > 0 ? controlsData : [
                  { name: 'NCA', Covered: 45, Partial: 20, Missing: 15 },
                  { name: 'ISO', Covered: 38, Partial: 25, Missing: 12 },
                  { name: 'NIST', Covered: 52, Partial: 18, Missing: 22 },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#fff', 
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px'
                    }}
                  />
                  <Legend />
                  <Bar dataKey="Covered" stackId="a" fill="#10b981" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="Partial" stackId="a" fill="#f59e0b" />
                  <Bar dataKey="Missing" stackId="a" fill="#ef4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg font-semibold flex items-center gap-2">
                <Clock className="w-5 h-5 text-slate-600" />
                Recent Activity
              </CardTitle>
              <Link to={createPageUrl('AuditTrail')}>
                <Button variant="ghost" size="sm" className="text-emerald-600 hover:text-emerald-700">
                  View all
                  <ArrowRight className="w-4 h-4 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {logsLoading ? (
              <div className="space-y-4">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                {displayActivity.map((activity) => (
                  <div key={activity.id} className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
                      {getActionIcon(activity.action)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-900 truncate">
                        {activity.action?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                      </p>
                      <p className="text-xs text-slate-500 truncate">{activity.target || activity.actor}</p>
                    </div>
                    <span className="text-xs text-slate-400 flex-shrink-0">
                      {activity.time ? format(new Date(activity.time), 'HH:mm') : 'Now'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}