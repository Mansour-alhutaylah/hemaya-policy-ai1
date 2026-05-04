import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import { useAuth } from '@/lib/AuthContext';
import PageContainer from '@/components/layout/PageContainer';
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
  FileText,
  TrendingUp,
  Database,
  Info,
  Lock,
  Download,
  Calendar,
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
  ResponsiveContainer,
} from 'recharts';
import { format } from 'date-fns';

const ComplianceResult = api.entities.ComplianceResult;
const Framework = api.entities.Framework;

const ADMIN_EMAIL = 'himayaadmin@gmail.com';

// Visual rotation reused across all frameworks rendered from the DB.
// Frameworks themselves carry no color/icon — these stay UI-only.
const PALETTE = [
  { color: 'emerald', bg: 'bg-emerald-50', text: 'text-emerald-600', border: 'border-emerald-200', gradient: 'from-emerald-500 to-teal-600',  stroke: '#10b981' },
  { color: 'blue',    bg: 'bg-blue-50',    text: 'text-blue-600',    border: 'border-blue-200',    gradient: 'from-blue-500 to-indigo-600',   stroke: '#3b82f6' },
  { color: 'purple',  bg: 'bg-purple-50',  text: 'text-purple-600',  border: 'border-purple-200',  gradient: 'from-purple-500 to-violet-600', stroke: '#8b5cf6' },
  { color: 'amber',   bg: 'bg-amber-50',   text: 'text-amber-600',   border: 'border-amber-200',   gradient: 'from-amber-500 to-orange-600',  stroke: '#f59e0b' },
  { color: 'rose',    bg: 'bg-rose-50',    text: 'text-rose-600',    border: 'border-rose-200',    gradient: 'from-rose-500 to-pink-600',     stroke: '#f43f5e' },
];

function paletteFor(idx) {
  return PALETTE[idx % PALETTE.length];
}

function safeFmt(d) {
  if (!d) return '—';
  try { return format(new Date(d), 'MMM d, yyyy'); } catch { return '—'; }
}

export default function Frameworks() {
  const [selectedFramework, setSelectedFramework] = useState(null);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const { user } = useAuth();
  const isAdmin = user?.email === ADMIN_EMAIL;

  // Real frameworks (DB-backed) — include_empty so admins can also see
  // frameworks that exist as records but have no document yet.
  const { data: rawFrameworks = [], isLoading: fwLoading } = useQuery({
    queryKey: ['frameworks', isAdmin ? 'all' : 'loaded-only'],
    queryFn: () => Framework.list(isAdmin ? { include_empty: 'true' } : {}),
  });

  const frameworks = rawFrameworks.map((fw, idx) => ({
    ...fw,
    palette: paletteFor(idx),
    isLoaded: (fw.chunks || 0) > 0,
  }));

  const allLoaded = frameworks.length > 0 && frameworks.every(fw => fw.isLoaded);

  const { data: results = [] } = useQuery({
    queryKey: ['complianceResults'],
    queryFn: () => ComplianceResult.list('-analyzed_at', 200),
  });

  const getFrameworkStats = (frameworkName) => {
    const frameworkResults = results.filter(r => r.framework === frameworkName);
    if (frameworkResults.length === 0) return null;

    const latest = frameworkResults.reduce((prev, curr) =>
      new Date(curr.analyzed_at) > new Date(prev.analyzed_at) ? curr : prev
    );

    const sorted = [...frameworkResults]
      .sort((a, b) => new Date(b.analyzed_at) - new Date(a.analyzed_at))
      .slice(0, 5);

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

  return (
    <PageContainer
      title="Compliance Frameworks"
      subtitle={
        isAdmin
          ? 'Database-backed framework reference documents and analysis results.'
          : 'Review the loaded framework reference documents and your analysis results.'
      }
    >
      {/* ── Knowledge Base banner ── */}
      <div className={`flex items-start gap-4 p-4 rounded-lg border mb-6 ${allLoaded ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'}`}>
        <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${allLoaded ? 'bg-emerald-100' : 'bg-amber-100'}`}>
          {allLoaded ? <CheckCircle2 className="w-5 h-5 text-emerald-600" /> : <Info className="w-5 h-5 text-amber-600" />}
        </div>
        <div>
          <p className={`font-semibold ${allLoaded ? 'text-emerald-800' : 'text-amber-800'}`}>
            {fwLoading
              ? 'Loading frameworks…'
              : frameworks.length === 0
                ? 'No frameworks in the system yet'
                : allLoaded
                  ? 'Framework Knowledge Base Ready'
                  : 'Some Framework Documents Are Missing'}
          </p>
          <p className={`text-sm mt-0.5 ${allLoaded ? 'text-emerald-700' : 'text-amber-700'}`}>
            {frameworks.length === 0
              ? isAdmin
                ? 'Upload your first framework reference document from the Admin panel to get started.'
                : 'Frameworks are managed by the platform administrator.'
              : allLoaded
                ? 'All listed frameworks have a reference document loaded for deep AI analysis.'
                : isAdmin
                  ? 'Some frameworks need a reference document. Upload one from the Admin panel.'
                  : 'An administrator needs to upload reference documents for the missing frameworks.'}
          </p>
        </div>
      </div>

      {/* ── Read-only notice for non-admins ── */}
      {!isAdmin && (
        <div className="flex items-start gap-3 p-4 rounded-lg border border-slate-200 bg-slate-50 mb-8">
          <div className="w-9 h-9 rounded-full bg-white border border-slate-200 flex items-center justify-center flex-shrink-0">
            <Lock className="w-4 h-4 text-slate-500" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-700">Framework management is admin-only</p>
            <p className="text-xs text-slate-500 mt-0.5">
              Reference documents are managed by the platform administrator. You can review framework status, scores, and analyses below.
            </p>
          </div>
        </div>
      )}

      {/* ── Framework Knowledge Base — real DB-backed file documents ── */}
      <h2 className="text-base font-semibold text-slate-700 mb-3 flex items-center gap-2">
        <Database className="w-4 h-4 text-slate-500" />
        Framework Knowledge Base
      </h2>

      {fwLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-10">
          {[0, 1, 2].map(i => (
            <Card key={i} className="border-slate-200">
              <CardContent className="p-5">
                <div className="h-32 bg-slate-100 rounded animate-pulse" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : frameworks.length === 0 ? (
        <Card className="border-slate-200 mb-10">
          <CardContent className="p-10 text-center">
            <Shield className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <p className="text-sm text-slate-500">
              No frameworks have been added yet.
              {isAdmin && ' Use the Admin panel to upload the first framework reference document.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-10">
          {frameworks.map((fw) => (
            <Card key={fw.id} className={`overflow-hidden border-2 ${fw.isLoaded ? fw.palette.border : 'border-slate-200'}`}>
              <div className={`h-1.5 bg-gradient-to-r ${fw.palette.gradient}`} />
              <CardContent className="p-5">
                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-11 h-11 rounded-xl ${fw.palette.bg} flex items-center justify-center`}>
                    <Shield className={`w-5 h-5 ${fw.palette.text}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-slate-900 truncate">{fw.name}</p>
                    <p className="text-xs text-slate-500">{fw.version ? `v${fw.version}` : '—'}</p>
                  </div>
                  {fw.isLoaded ? (
                    <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 border">
                      <CheckCircle2 className="w-3 h-3 mr-1" />
                      Loaded
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-slate-500 border-slate-300">Not Loaded</Badge>
                  )}
                </div>

                <p className="text-xs text-slate-500 mb-3 line-clamp-2 min-h-[2rem]">
                  {fw.description || 'No description provided.'}
                </p>

                {/* Real file metadata from the DB */}
                {fw.file_url ? (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 mb-3">
                    <div className="flex items-center gap-2 text-xs text-slate-700">
                      <FileText className={`w-3.5 h-3.5 ${fw.palette.text} flex-shrink-0`} />
                      <span className="truncate font-medium" title={fw.original_file_name}>
                        {fw.original_file_name || 'Reference document'}
                      </span>
                      {fw.file_type && (
                        <span className="text-[10px] bg-white border border-slate-200 px-1.5 py-0.5 rounded">{fw.file_type}</span>
                      )}
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1 flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      Uploaded {safeFmt(fw.uploaded_at)}
                      {fw.uploaded_by ? ` · ${fw.uploaded_by}` : ''}
                    </p>
                  </div>
                ) : (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3 flex items-center gap-2 text-xs text-amber-700">
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                    <span>Awaiting reference document upload.</span>
                  </div>
                )}

                {fw.isLoaded && (
                  <div className="flex items-center gap-2 text-xs text-emerald-600 bg-emerald-50 px-3 py-1.5 rounded mb-3">
                    <Database className="w-3.5 h-3.5" />
                    <span>{Number(fw.chunks || 0).toLocaleString()} indexed chunks</span>
                  </div>
                )}

                {fw.file_url && (
                  <a
                    href={fw.file_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700 hover:text-emerald-700 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" /> Download reference document
                  </a>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ── Analysis Results by Framework ── */}
      <h2 className="text-base font-semibold text-slate-700 mb-3 flex items-center gap-2">
        <TrendingUp className="w-4 h-4 text-slate-500" />
        Analysis Results by Framework
      </h2>
      {frameworks.length === 0 ? (
        <Card className="border-slate-200 mb-8">
          <CardContent className="p-10 text-center text-sm text-slate-500">
            Analysis results will appear here once frameworks are loaded and policies are analyzed.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {frameworks.map((framework) => {
            const stats = getFrameworkStats(framework.name);
            const score = stats?.latest?.compliance_score || 0;

            return (
              <Card
                key={framework.id}
                className="overflow-hidden hover:shadow-lg transition-shadow cursor-pointer"
                onClick={() => { setSelectedFramework(framework); setShowDetailDialog(true); }}
              >
                <div className={`h-2 bg-gradient-to-r ${framework.palette.gradient}`} />
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-12 h-12 rounded-xl ${framework.palette.bg} flex items-center justify-center`}>
                        <Shield className={`w-6 h-6 ${framework.palette.text}`} />
                      </div>
                      <div>
                        <CardTitle className="text-lg">{framework.name}</CardTitle>
                        <p className="text-xs text-slate-500">{framework.version ? `v${framework.version}` : '—'}</p>
                      </div>
                    </div>
                    <Badge variant="outline" className={`${framework.palette.text} ${framework.palette.border}`}>
                      {framework.controls || 0} Controls
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-slate-600 mb-4 line-clamp-2 min-h-[2.5rem]">
                    {framework.description || 'No description provided.'}
                  </p>

                  {stats ? (
                    <div className="space-y-4">
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-slate-500">Compliance Score</span>
                          <span className={`text-lg font-bold ${framework.palette.text}`}>{Math.round(score)}%</span>
                        </div>
                        <Progress value={score} className="h-2" />
                      </div>
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
                      {stats.trendData.length > 1 && (
                        <div className="h-16">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={stats.trendData}>
                              <Line
                                type="monotone"
                                dataKey="score"
                                stroke={framework.palette.stroke}
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
                        <Button size="sm" variant="outline">Run Analysis</Button>
                      </Link>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* ── Framework Comparison Table ── */}
      {frameworks.length > 0 && (
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
                    <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Reference Doc</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Indexed</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Controls</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Latest Score</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Analyses</th>
                    <th className="text-center py-3 px-4 text-sm font-semibold text-slate-700">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {frameworks.map((framework) => {
                    const stats = getFrameworkStats(framework.name);
                    return (
                      <tr key={framework.id} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-4 px-4">
                          <div className="flex items-center gap-3">
                            <div className={`w-9 h-9 rounded-lg ${framework.palette.bg} flex items-center justify-center`}>
                              <Shield className={`w-4 h-4 ${framework.palette.text}`} />
                            </div>
                            <div>
                              <p className="font-medium text-slate-900">{framework.name}</p>
                              <p className="text-xs text-slate-500">{framework.version ? `v${framework.version}` : '—'}</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-4 px-4 text-center">
                          {framework.file_url ? (
                            <a
                              href={framework.file_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-emerald-700"
                              title={framework.original_file_name}
                            >
                              <FileText className="w-3 h-3" />
                              {framework.file_type || 'File'}
                            </a>
                          ) : (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                        </td>
                        <td className="py-4 px-4 text-center">
                          {framework.isLoaded ? (
                            <Badge className="bg-emerald-100 text-emerald-700 border-0">
                              <CheckCircle2 className="w-3 h-3 mr-1" />
                              {Number(framework.chunks || 0).toLocaleString()}
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-slate-400">Not loaded</Badge>
                          )}
                        </td>
                        <td className="py-4 px-4 text-center">
                          <span className="font-medium">{framework.controls || 0}</span>
                        </td>
                        <td className="py-4 px-4 text-center">
                          {stats ? (
                            <Badge className={`${framework.palette.bg} ${framework.palette.text} border-0`}>
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
                            <Button size="sm" variant="ghost" className={framework.palette.text}>
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
      )}

      {/* ── Detail Dialog ── */}
      <Dialog open={showDetailDialog} onOpenChange={setShowDetailDialog}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3">
              <Shield className={`w-5 h-5 ${selectedFramework?.palette?.text || 'text-emerald-600'}`} />
              {selectedFramework?.name}
            </DialogTitle>
          </DialogHeader>

          {selectedFramework && (
            <div className="space-y-6 py-4">
              <p className="text-sm text-slate-600">
                {selectedFramework.description || 'No description provided.'}
              </p>

              <div className="grid grid-cols-3 gap-4">
                <Card className="bg-slate-50 border-slate-200">
                  <CardContent className="p-4 text-center">
                    <Shield className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                    <p className="text-2xl font-bold">{selectedFramework.controls || 0}</p>
                    <p className="text-xs text-slate-500">Controls</p>
                  </CardContent>
                </Card>
                <Card className="bg-slate-50 border-slate-200">
                  <CardContent className="p-4 text-center">
                    <Database className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                    <p className="text-2xl font-bold">{Number(selectedFramework.chunks || 0).toLocaleString()}</p>
                    <p className="text-xs text-slate-500">Indexed chunks</p>
                  </CardContent>
                </Card>
                <Card className="bg-slate-50 border-slate-200">
                  <CardContent className="p-4 text-center">
                    <FileText className="w-6 h-6 text-slate-600 mx-auto mb-2" />
                    <p className="text-2xl font-bold">{selectedFramework.version || '—'}</p>
                    <p className="text-xs text-slate-500">Version</p>
                  </CardContent>
                </Card>
              </div>

              {selectedFramework.file_url && (
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                  <p className="text-xs font-semibold text-slate-700 mb-2">Reference document</p>
                  <a
                    href={selectedFramework.file_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 text-sm text-emerald-700 hover:underline"
                  >
                    <FileText className="w-4 h-4" />
                    {selectedFramework.original_file_name || 'Download'}
                  </a>
                  <p className="text-xs text-slate-500 mt-2">
                    Uploaded {safeFmt(selectedFramework.uploaded_at)}
                    {selectedFramework.uploaded_by ? ` by ${selectedFramework.uploaded_by}` : ''}
                  </p>
                </div>
              )}

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
                            <Line type="monotone" dataKey="score" stroke="#10b981" strokeWidth={2} dot={{ fill: '#10b981' }} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  );
                }
                return null;
              })()}
            </div>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setShowDetailDialog(false)}>Close</Button>
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
