import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
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
  FlaskConical,
  Shield,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  Sparkles,
  FileText,
  Info,
  Calendar,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { formatDate } from '@/lib/format';

const ComplianceResult = api.entities.ComplianceResult;
const Gap = api.entities.Gap;
const Policy = api.entities.Policy;

// Transparent frontend estimate. Matches the formula in the page spec:
//   compliant     = 1 point
//   partial       = 0.5 point
//   non_compliant = 0 point
// For each selected gap we add +1 point (treats the fix as a
// non_compliant -> compliant transition; we cannot know precisely
// without re-running analysis, which the disclaimer states).
function projectFramework(result, selectedCountForFw) {
  const cov = Number(result.controls_covered ?? 0);
  const par = Number(result.controls_partial ?? 0);
  const mis = Number(result.controls_missing ?? 0);
  const total = cov + par + mis;
  const current = Number(result.compliance_score ?? 0);
  if (!total) {
    return { total: 0, current, projected: current, improvement: 0 };
  }
  const currentPoints = cov + par * 0.5;
  const gain = Math.min(selectedCountForFw, mis + par); // can't fix more than exist
  const projectedPoints = Math.min(currentPoints + gain, total);
  const projected = Math.round((projectedPoints / total) * 100 * 10) / 10;
  return {
    total,
    current: Math.round(current * 10) / 10,
    projected,
    improvement: Math.round((projected - current) * 10) / 10,
  };
}

export default function Simulation() {
  const [policyId, setPolicyId] = useState('');
  const [frameworkFilter, setFrameworkFilter] = useState('all');
  const [selectedGapIds, setSelectedGapIds] = useState([]);
  const [showResults, setShowResults] = useState(false);

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-last_analyzed_at'),
  });

  // Default selection: most recent analyzed policy. Done once so the user
  // can switch back to "" (none) without us overriding it.
  const [hasInitedSelection, setHasInitedSelection] = useState(false);
  useEffect(() => {
    if (hasInitedSelection) return;
    if (policies.length === 0) return;
    const analyzed = policies.find(p => p.status === 'analyzed');
    if (analyzed) setPolicyId(analyzed.id);
    setHasInitedSelection(true);
  }, [policies, hasInitedSelection]);

  const selectedPolicy = useMemo(
    () => policies.find(p => p.id === policyId) || null,
    [policies, policyId],
  );

  // Gaps and compliance_results both need a policy_id to be meaningful here.
  const { data: gaps = [], isLoading: gapsLoading } = useQuery({
    queryKey: ['gaps', policyId, 'Open'],
    queryFn: () => Gap.filter({ policy_id: policyId, status: 'Open' }),
    enabled: !!policyId,
  });

  const { data: results = [] } = useQuery({
    queryKey: ['complianceResults', policyId],
    queryFn: () => ComplianceResult.list('-analyzed_at', 50),
    enabled: !!policyId,
  });

  const policyResults = useMemo(
    () => results.filter(r => r.policy_id === policyId),
    [results, policyId],
  );

  // Reset the selection + results when the user switches policy or filter so
  // we don't leave stale "X gaps selected" referring to a different policy.
  useEffect(() => {
    setSelectedGapIds([]);
    setShowResults(false);
  }, [policyId]);

  useEffect(() => { setShowResults(false); }, [frameworkFilter, selectedGapIds]);

  const frameworkOptions = useMemo(() => {
    const set = new Set();
    gaps.forEach(g => { if (g.framework) set.add(g.framework); });
    policyResults.forEach(r => { if (r.framework) set.add(r.framework); });
    return Array.from(set).sort();
  }, [gaps, policyResults]);

  const filteredGaps = useMemo(() => (
    frameworkFilter === 'all'
      ? gaps
      : gaps.filter(g => g.framework === frameworkFilter)
  ), [gaps, frameworkFilter]);

  const toggleGap = (gapId) => {
    setSelectedGapIds(prev => prev.includes(gapId) ? prev.filter(x => x !== gapId) : [...prev, gapId]);
  };

  const resetSimulation = () => {
    setSelectedGapIds([]);
    setShowResults(false);
  };

  // Derived: how many selected gaps fall in each framework. Used by the
  // per-framework projection.
  const selectedByFramework = useMemo(() => {
    const acc = {};
    selectedGapIds.forEach(id => {
      const g = gaps.find(x => x.id === id);
      if (!g) return;
      const fw = g.framework || 'Unknown';
      acc[fw] = (acc[fw] || 0) + 1;
    });
    return acc;
  }, [selectedGapIds, gaps]);

  // Aggregate score across all frameworks of this policy, weighted by control count.
  const overall = useMemo(() => {
    let totalControls = 0;
    let currentPoints = 0;
    let projectedPoints = 0;
    policyResults.forEach(r => {
      const proj = projectFramework(r, selectedByFramework[r.framework] || 0);
      totalControls += proj.total;
      if (proj.total) {
        currentPoints += (r.controls_covered ?? 0) + (r.controls_partial ?? 0) * 0.5;
        const gain = Math.min(
          selectedByFramework[r.framework] || 0,
          (r.controls_missing ?? 0) + (r.controls_partial ?? 0),
        );
        projectedPoints += Math.min(((r.controls_covered ?? 0) + (r.controls_partial ?? 0) * 0.5) + gain, proj.total);
      }
    });
    if (!totalControls) return null;
    const current = Math.round((currentPoints / totalControls) * 1000) / 10;
    const projected = Math.round((projectedPoints / totalControls) * 1000) / 10;
    return { current, projected, improvement: Math.round((projected - current) * 10) / 10 };
  }, [policyResults, selectedByFramework]);

  const chartData = useMemo(() => (
    policyResults.map(r => {
      const proj = projectFramework(r, selectedByFramework[r.framework] || 0);
      return {
        framework: r.framework || 'Unknown',
        current: proj.current,
        projected: proj.projected,
      };
    })
  ), [policyResults, selectedByFramework]);

  // Disabled-state explanation. The button stays disabled until the user
  // has both an analysed policy with compliance_results and at least one
  // selected gap.
  const disabledReason = (() => {
    if (!policyId) return 'Select a policy first.';
    if (selectedPolicy && selectedPolicy.status !== 'analyzed') return 'This policy has not been analysed yet. Run analysis from the Policies page first.';
    if (policyResults.length === 0) return 'Compliance score not yet available for this policy. Re-run analysis to refresh.';
    if (selectedGapIds.length === 0) return 'Select at least one control to preview impact.';
    return null;
  })();

  // Empty-state copy for the candidate list.
  const candidateEmpty = (() => {
    if (!policyId) return { title: 'Select a policy', body: 'Pick a policy from the dropdown above to load its open compliance gaps.' };
    if (selectedPolicy && selectedPolicy.status !== 'analyzed') return { title: 'Policy not analysed yet', body: 'Run analysis on this policy first to generate simulation candidates.' };
    if (gaps.length === 0 && !gapsLoading) return { title: 'No open gaps for this policy', body: 'There is nothing to simulate — all controls are already compliant.' };
    if (filteredGaps.length === 0) return { title: 'No gaps match this framework filter', body: 'Switch the framework filter back to "All frameworks".' };
    return null;
  })();

  // Banner: current policy context shown above the columns.
  const totalOpenGaps = gaps.length;

  return (
    <PageContainer
      title="Compliance Simulation"
      subtitle="Estimate the impact of fixing open gaps on your compliance score"
      actions={
        <Badge className="bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30 gap-1">
          <FlaskConical className="w-3 h-3" />
          BETA
        </Badge>
      }
    >
      {/* Info banner */}
      <Card className="mb-6 bg-gradient-to-r from-amber-50 to-orange-50 border-amber-200 dark:from-amber-500/10 dark:to-orange-500/10 dark:border-amber-500/30">
        <CardContent className="p-4 flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h3 className="font-semibold text-amber-900 dark:text-amber-200 mb-1">What-If Analysis</h3>
            <p className="text-sm text-amber-700 dark:text-amber-300">
              Pick a policy, select the open gaps you plan to fix, and preview the predicted compliance score.
              This is a transparent estimate (compliant = 1, partial = 0.5, non-compliant = 0); the actual
              score is confirmed only after updating the policy and re-running analysis.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Policy context */}
      <Card className="mb-6 shadow-sm">
        <CardContent className="p-4 flex flex-col lg:flex-row gap-4 lg:items-center">
          <Select value={policyId} onValueChange={setPolicyId}>
            <SelectTrigger className="w-full lg:w-80">
              <FileText className="w-4 h-4 mr-2" />
              <SelectValue placeholder="Select a policy" />
            </SelectTrigger>
            <SelectContent>
              {policies.length === 0 ? (
                <SelectItem disabled value="__none__">No policies yet</SelectItem>
              ) : (
                policies.map(p => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.file_name || p.id}
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>

          {selectedPolicy && (
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <div className="flex items-center gap-1.5">
                <Shield className="w-4 h-4 text-muted-foreground" />
                <span className="text-muted-foreground">Framework:</span>
                <span className="font-medium text-foreground">
                  {selectedPolicy.framework_code || policyResults.map(r => r.framework).filter(Boolean).join(', ') || '—'}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-muted-foreground" />
                <span className="text-muted-foreground">Current score:</span>
                <span className="font-medium text-foreground">
                  {overall ? `${overall.current}%` : '—'}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-muted-foreground" />
                <span className="text-muted-foreground">Open gaps:</span>
                <span className="font-medium text-foreground">{totalOpenGaps}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Calendar className="w-4 h-4 text-muted-foreground" />
                <span className="text-muted-foreground">Last analysed:</span>
                <span className="font-medium text-foreground">
                  {formatDate(selectedPolicy.last_analyzed_at)}
                </span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Candidate list */}
        <Card className="lg:col-span-1 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Shield className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              Select Gaps to Fix
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="mb-4">
              <Select value={frameworkFilter} onValueChange={setFrameworkFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="Filter by framework" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All frameworks</SelectItem>
                  {frameworkOptions.map(fw => (
                    <SelectItem key={fw} value={fw}>{fw}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {candidateEmpty ? (
              <div className="py-12 text-center">
                <Info className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
                <h3 className="text-sm font-semibold text-foreground mb-1">{candidateEmpty.title}</h3>
                <p className="text-xs text-muted-foreground">{candidateEmpty.body}</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
                {filteredGaps.map(gap => {
                  const isSel = selectedGapIds.includes(gap.id);
                  const sevColor =
                    gap.severity === 'High'   ? 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300'
                    : gap.severity === 'Medium' ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300'
                    : 'bg-muted text-muted-foreground';
                  return (
                    <div
                      key={gap.id}
                      className={`p-3 rounded-lg border transition-all cursor-pointer ${
                        isSel
                          ? 'bg-emerald-50 border-emerald-300 dark:bg-emerald-500/10 dark:border-emerald-500/40'
                          : 'bg-card border-border hover:border-emerald-200 dark:hover:border-emerald-500/40'
                      }`}
                      onClick={() => toggleGap(gap.id)}
                    >
                      <div className="flex items-start gap-3">
                        <Checkbox checked={isSel} onCheckedChange={() => toggleGap(gap.id)} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            {gap.control_id && (
                              <Badge variant="outline" className="font-mono text-xs">
                                {gap.control_id}
                              </Badge>
                            )}
                            {gap.severity && (
                              <Badge className={`${sevColor} text-xs border-0`}>
                                {gap.severity}
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm font-medium text-foreground line-clamp-2">
                            {gap.control_name || 'Untitled gap'}
                          </p>
                          <p className="text-xs text-muted-foreground">{gap.framework || 'Unknown framework'}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="mt-4 pt-4 border-t border-border">
              <p className="text-sm text-muted-foreground mb-3">
                {selectedGapIds.length} gap{selectedGapIds.length === 1 ? '' : 's'} selected
              </p>
              <div className="flex gap-2">
                <Button
                  onClick={() => setShowResults(true)}
                  disabled={!!disabledReason}
                  className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                  title={disabledReason || 'Preview the projected compliance score'}
                >
                  <Play className="w-4 h-4 mr-2" />
                  Run Simulation
                </Button>
                <Button
                  variant="outline"
                  onClick={resetSimulation}
                  disabled={selectedGapIds.length === 0 && !showResults}
                  title="Clear selection"
                >
                  <RotateCcw className="w-4 h-4" />
                </Button>
              </div>
              {disabledReason && (
                <p className="text-xs text-muted-foreground mt-2">{disabledReason}</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        <Card className="lg:col-span-2 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              Simulation Results
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!showResults || !overall ? (
              <div className="h-80 flex flex-col items-center justify-center text-center">
                <FlaskConical className="w-16 h-16 text-muted-foreground/40 mb-4" />
                <h3 className="text-lg font-semibold text-foreground mb-1">No simulation run yet</h3>
                <p className="text-sm text-muted-foreground max-w-md">
                  {disabledReason
                    || 'Select gaps from the left and click "Run Simulation" to preview the predicted impact.'}
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Headline metrics */}
                <div className="grid grid-cols-3 gap-4">
                  <Card className="bg-emerald-50 border-emerald-200 dark:bg-emerald-500/10 dark:border-emerald-500/30">
                    <CardContent className="p-4 text-center">
                      <TrendingUp className="w-6 h-6 text-emerald-600 dark:text-emerald-400 mx-auto mb-2" />
                      <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">
                        {overall.improvement >= 0 ? '+' : ''}{overall.improvement}%
                      </p>
                      <p className="text-xs text-emerald-600 dark:text-emerald-400">Estimated improvement</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-blue-50 border-blue-200 dark:bg-blue-500/10 dark:border-blue-500/30">
                    <CardContent className="p-4 text-center">
                      <CheckCircle2 className="w-6 h-6 text-blue-600 dark:text-blue-400 mx-auto mb-2" />
                      <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">{selectedGapIds.length}</p>
                      <p className="text-xs text-blue-600 dark:text-blue-400">Gaps targeted</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-slate-50 border-slate-200 dark:bg-slate-500/10 dark:border-slate-500/30">
                    <CardContent className="p-4 text-center">
                      <FlaskConical className="w-6 h-6 text-slate-600 dark:text-slate-400 mx-auto mb-2" />
                      <p className="text-2xl font-bold text-slate-700 dark:text-slate-300">
                        {overall.current}% → {overall.projected}%
                      </p>
                      <p className="text-xs text-slate-600 dark:text-slate-400">Overall score</p>
                    </CardContent>
                  </Card>
                </div>

                {/* Per-framework chart */}
                {chartData.length > 0 && (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={chartData} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 12 }} />
                        <YAxis dataKey="framework" type="category" tick={{ fontSize: 12 }} width={120} />
                        <Tooltip formatter={(value) => [`${value}%`]} />
                        <Legend />
                        <Bar dataKey="current"   name="Current"   fill="#94a3b8" radius={[0, 4, 4, 0]} />
                        <Bar dataKey="projected" name="Projected" fill="#10b981" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Per-framework detail */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-foreground">Per-framework breakdown</h4>
                  {policyResults.map(r => {
                    const proj = projectFramework(r, selectedByFramework[r.framework] || 0);
                    if (!proj.total) return null;
                    return (
                      <div key={r.id} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="font-medium text-foreground">{r.framework || 'Unknown'}</span>
                          <span>
                            <span className="text-muted-foreground">{proj.current}%</span>
                            <span className="mx-2 text-muted-foreground">→</span>
                            <span className="text-emerald-600 dark:text-emerald-400 font-medium">{proj.projected}%</span>
                            <span className="text-emerald-600 dark:text-emerald-400 text-xs ml-1">
                              ({proj.improvement >= 0 ? '+' : ''}{proj.improvement}%)
                            </span>
                          </span>
                        </div>
                        <div className="relative h-2 bg-muted rounded-full overflow-hidden">
                          <div className="absolute h-full bg-slate-300 dark:bg-slate-600 rounded-full"
                               style={{ width: `${proj.current}%` }} />
                          <div className="absolute h-full bg-emerald-500 rounded-full transition-all"
                               style={{ width: `${proj.projected}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Disclaimer — surfaces the estimate caveat per the spec */}
                <div className="bg-muted/50 border border-border rounded-lg p-3 flex gap-2 items-start">
                  <Info className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-muted-foreground">
                    This is an estimate computed on the client (compliant = 1, partial = 0.5, non-compliant = 0).
                    The actual score is confirmed only after updating the policy and re-running analysis.
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
