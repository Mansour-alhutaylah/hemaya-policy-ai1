import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import PageContainer from '@/components/layout/PageContainer';
import StatsCard from '@/components/ui/StatsCard';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Shield,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ArrowRight,
  ExternalLink,
  BookOpen,
  FileText,
  TrendingUp
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

const ComplianceResult = base44.entities.ComplianceResult;

const frameworksData = [
  {
    id: 'nca-ecc',
    name: 'NCA ECC',
    fullName: 'National Cybersecurity Authority - Essential Cybersecurity Controls',
    description: 'Saudi Arabia\'s national cybersecurity framework for critical infrastructure and government entities.',
    totalControls: 114,
    domains: 5,
    version: '2.0',
    lastUpdated: '2023',
    icon: '🇸🇦',
    color: 'emerald',
    bgGradient: 'from-emerald-500 to-teal-600',
  },
  {
    id: 'iso-27001',
    name: 'ISO 27001',
    fullName: 'ISO/IEC 27001:2022 Information Security Management',
    description: 'International standard for establishing, implementing, maintaining, and improving an ISMS.',
    totalControls: 93,
    domains: 4,
    version: '2022',
    lastUpdated: '2022',
    icon: '🌐',
    color: 'blue',
    bgGradient: 'from-blue-500 to-indigo-600',
  },
  {
    id: 'nist-800-53',
    name: 'NIST 800-53',
    fullName: 'NIST Special Publication 800-53 Rev. 5',
    description: 'U.S. federal security and privacy controls for information systems and organizations.',
    totalControls: 1007,
    domains: 20,
    version: 'Rev. 5',
    lastUpdated: '2020',
    icon: '🇺🇸',
    color: 'purple',
    bgGradient: 'from-purple-500 to-violet-600',
  },
];

export default function Frameworks() {
  const [selectedFramework, setSelectedFramework] = useState(null);
  const [showDetailDialog, setShowDetailDialog] = useState(false);

  const { data: results = [], isLoading } = useQuery({
    queryKey: ['complianceResults'],
    queryFn: () => ComplianceResult.list('-analyzed_at', 100),
  });

  // Calculate stats per framework
  const getFrameworkStats = (frameworkName) => {
    const frameworkResults = results.filter(r => r.framework === frameworkName);
    if (frameworkResults.length === 0) return null;

    const latest = frameworkResults.reduce((prev, curr) => 
      new Date(curr.analyzed_at) > new Date(prev.analyzed_at) ? curr : prev
    );

    // Calculate trend from last 5 results
    const sorted = [...frameworkResults].sort((a, b) => 
      new Date(b.analyzed_at) - new Date(a.analyzed_at)
    ).slice(0, 5);

    const trendData = sorted.reverse().map((r, i) => ({
      name: `Analysis ${i + 1}`,
      score: Math.round(r.compliance_score || 0),
    }));

    return {
      latest,
      trendData,
      avgScore: Math.round(frameworkResults.reduce((acc, r) => acc + (r.compliance_score || 0), 0) / frameworkResults.length),
      analysesCount: frameworkResults.length,
    };
  };

  const handleViewDetails = (framework) => {
    setSelectedFramework(framework);
    setShowDetailDialog(true);
  };

  const getColorClasses = (color) => {
    const colors = {
      emerald: {
        bg: 'bg-emerald-50',
        text: 'text-emerald-600',
        border: 'border-emerald-200',
        progress: 'bg-emerald-500',
      },
      blue: {
        bg: 'bg-blue-50',
        text: 'text-blue-600',
        border: 'border-blue-200',
        progress: 'bg-blue-500',
      },
      purple: {
        bg: 'bg-purple-50',
        text: 'text-purple-600',
        border: 'border-purple-200',
        progress: 'bg-purple-500',
      },
    };
    return colors[color] || colors.emerald;
  };

  return (
    <PageContainer
      title="Compliance Frameworks"
      subtitle="Manage and monitor compliance against industry standards"
    >
      {/* Framework Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {frameworksData.map((framework) => {
          const stats = getFrameworkStats(framework.name);
          const colorClasses = getColorClasses(framework.color);
          const score = stats?.latest?.compliance_score || 0;

          return (
            <Card 
              key={framework.id} 
              className="overflow-hidden hover:shadow-lg transition-shadow cursor-pointer"
              onClick={() => handleViewDetails(framework)}
            >
              {/* Header with gradient */}
              <div className={`h-2 bg-gradient-to-r ${framework.bgGradient}`} />
              
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-12 h-12 rounded-xl ${colorClasses.bg} flex items-center justify-center text-2xl`}>
                      {framework.icon}
                    </div>
                    <div>
                      <CardTitle className="text-lg">{framework.name}</CardTitle>
                      <p className="text-xs text-slate-500">v{framework.version}</p>
                    </div>
                  </div>
                  <Badge variant="outline" className={`${colorClasses.text} ${colorClasses.border}`}>
                    {framework.totalControls} Controls
                  </Badge>
                </div>
              </CardHeader>

              <CardContent>
                <p className="text-sm text-slate-600 mb-4 line-clamp-2">
                  {framework.description}
                </p>

                {stats ? (
                  <div className="space-y-4">
                    {/* Score Progress */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-slate-500">Compliance Score</span>
                        <span className={`text-lg font-bold ${colorClasses.text}`}>
                          {Math.round(score)}%
                        </span>
                      </div>
                      <Progress 
                        value={score} 
                        className="h-2"
                      />
                    </div>

                    {/* Controls Stats */}
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-1 text-emerald-600">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>{stats.latest.controls_covered || 0}</span>
                      </div>
                      <div className="flex items-center gap-1 text-amber-600">
                        <AlertTriangle className="w-4 h-4" />
                        <span>{stats.latest.controls_partial || 0}</span>
                      </div>
                      <div className="flex items-center gap-1 text-red-600">
                        <XCircle className="w-4 h-4" />
                        <span>{stats.latest.controls_missing || 0}</span>
                      </div>
                    </div>

                    {/* Mini Trend Chart */}
                    {stats.trendData.length > 1 && (
                      <div className="h-16">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={stats.trendData}>
                            <Line 
                              type="monotone" 
                              dataKey="score" 
                              stroke={framework.color === 'emerald' ? '#10b981' : framework.color === 'blue' ? '#3b82f6' : '#8b5cf6'}
                              strokeWidth={2}
                              dot={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-6">
                    <p className="text-sm text-slate-500 mb-3">No analysis data yet</p>
                    <Link to={createPageUrl('Policies')}>
                      <Button size="sm" variant="outline">
                        Run Analysis
                      </Button>
                    </Link>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Framework Comparison */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-emerald-600" />
            Framework Comparison
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700">Framework</th>
                  <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Total Controls</th>
                  <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Domains</th>
                  <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Latest Score</th>
                  <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Analyses</th>
                  <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Actions</th>
                </tr>
              </thead>
              <tbody>
                {frameworksData.map((framework) => {
                  const stats = getFrameworkStats(framework.name);
                  const colorClasses = getColorClasses(framework.color);

                  return (
                    <tr key={framework.id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="py-4 px-4">
                        <div className="flex items-center gap-3">
                          <span className="text-xl">{framework.icon}</span>
                          <div>
                            <p className="font-medium text-slate-900">{framework.name}</p>
                            <p className="text-xs text-slate-500">v{framework.version}</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-4 px-4 text-center">
                        <span className="font-medium">{framework.totalControls}</span>
                      </td>
                      <td className="py-4 px-4 text-center">
                        <span className="font-medium">{framework.domains}</span>
                      </td>
                      <td className="py-4 px-4 text-center">
                        {stats ? (
                          <Badge className={`${colorClasses.bg} ${colorClasses.text} border-0`}>
                            {Math.round(stats.latest.compliance_score || 0)}%
                          </Badge>
                        ) : (
                          <span className="text-slate-400">-</span>
                        )}
                      </td>
                      <td className="py-4 px-4 text-center">
                        <span className="font-medium">{stats?.analysesCount || 0}</span>
                      </td>
                      <td className="py-4 px-4 text-center">
                        <Link to={createPageUrl(`Analyses?framework=${framework.name}`)}>
                          <Button size="sm" variant="ghost" className={colorClasses.text}>
                            View Results
                            <ArrowRight className="w-4 h-4 ml-1" />
                          </Button>
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={showDetailDialog} onOpenChange={setShowDetailDialog}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3">
              <span className="text-2xl">{selectedFramework?.icon}</span>
              {selectedFramework?.name}
            </DialogTitle>
          </DialogHeader>

          {selectedFramework && (
            <div className="space-y-6 py-4">
              <p className="text-slate-600">{selectedFramework.fullName}</p>
              <p className="text-sm text-slate-500">{selectedFramework.description}</p>

              <div className="grid grid-cols-3 gap-4">
                <Card className="bg-slate-50 border-slate-200">
                  <CardContent className="p-4 text-center">
                    <Shield className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                    <p className="text-2xl font-bold">{selectedFramework.totalControls}</p>
                    <p className="text-xs text-slate-500">Total Controls</p>
                  </CardContent>
                </Card>
                <Card className="bg-slate-50 border-slate-200">
                  <CardContent className="p-4 text-center">
                    <BookOpen className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                    <p className="text-2xl font-bold">{selectedFramework.domains}</p>
                    <p className="text-xs text-slate-500">Domains</p>
                  </CardContent>
                </Card>
                <Card className="bg-slate-50 border-slate-200">
                  <CardContent className="p-4 text-center">
                    <FileText className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                    <p className="text-2xl font-bold">{selectedFramework.version}</p>
                    <p className="text-xs text-slate-500">Version</p>
                  </CardContent>
                </Card>
              </div>

              {/* Trend Chart for selected framework */}
              {(() => {
                const stats = getFrameworkStats(selectedFramework.name);
                if (stats && stats.trendData.length > 1) {
                  return (
                    <div>
                      <h4 className="text-sm font-medium text-slate-700 mb-2">Compliance Trend</h4>
                      <div className="h-48">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={stats.trendData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                            <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                            <Tooltip />
                            <Line 
                              type="monotone" 
                              dataKey="score" 
                              stroke="#10b981"
                              strokeWidth={2}
                              dot={{ fill: '#10b981' }}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  );
                }
                return null;
              })()}

              <div className="text-xs text-slate-400">
                Last Updated: {selectedFramework.lastUpdated}
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setShowDetailDialog(false)}>
              Close
            </Button>
            <Link to={createPageUrl(`Analyses?framework=${selectedFramework?.name}`)}>
              <Button className="bg-emerald-600 hover:bg-emerald-700">
                View Analysis Results
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
          </div>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}