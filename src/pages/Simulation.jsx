import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import PageContainer from '@/components/layout/PageContainer';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
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
  Sparkles
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell
} from 'recharts';

const ComplianceResult = base44.entities.ComplianceResult;
const Gap = base44.entities.Gap;

// Sample controls for simulation
const sampleControls = [
  { id: 'AC-1', name: 'Access Control Policy', framework: 'NIST 800-53', impact: 3 },
  { id: 'AC-2', name: 'Account Management', framework: 'NIST 800-53', impact: 5 },
  { id: 'A.5.1.1', name: 'Information Security Policies', framework: 'ISO 27001', impact: 4 },
  { id: 'A.9.1.1', name: 'Access Control Policy', framework: 'ISO 27001', impact: 3 },
  { id: '2-1-1', name: 'Cybersecurity Governance', framework: 'NCA ECC', impact: 5 },
  { id: '2-2-1', name: 'Cybersecurity Risk Management', framework: 'NCA ECC', impact: 4 },
  { id: 'A.12.4.1', name: 'Event Logging', framework: 'ISO 27001', impact: 3 },
  { id: 'AU-2', name: 'Audit Events', framework: 'NIST 800-53', impact: 3 },
  { id: '3-1-1', name: 'Human Resource Security', framework: 'NCA ECC', impact: 2 },
  { id: 'A.7.2.2', name: 'Security Awareness Training', framework: 'ISO 27001', impact: 2 },
];

export default function Simulation() {
  const [selectedFramework, setSelectedFramework] = useState('all');
  const [selectedControls, setSelectedControls] = useState([]);
  const [simulationRun, setSimulationRun] = useState(false);
  const [simulationResults, setSimulationResults] = useState(null);
  const { toast } = useToast();

  const { data: results = [] } = useQuery({
    queryKey: ['complianceResults'],
    queryFn: () => ComplianceResult.list('-analyzed_at', 10),
  });

  const { data: gaps = [] } = useQuery({
    queryKey: ['gaps'],
    queryFn: () => Gap.filter({ status: 'Open' }),
  });

  // Get current scores per framework
  const getCurrentScores = () => {
    const scores = {
      'NCA ECC': 72,
      'ISO 27001': 68,
      'NIST 800-53': 58,
    };

    results.forEach(r => {
      if (r.compliance_score) {
        scores[r.framework] = Math.round(r.compliance_score);
      }
    });

    return scores;
  };

  const currentScores = getCurrentScores();

  const filteredControls = selectedFramework === 'all' 
    ? sampleControls 
    : sampleControls.filter(c => c.framework === selectedFramework);

  const toggleControl = (controlId) => {
    setSelectedControls(prev => 
      prev.includes(controlId) 
        ? prev.filter(id => id !== controlId)
        : [...prev, controlId]
    );
    setSimulationRun(false);
    setSimulationResults(null);
  };

  const runSimulation = async () => {
    try {
      // Get latest analyzed policy
      const analyzedPolicies = policies.filter(p => p.status === 'analyzed');
      
      if (analyzedPolicies.length === 0) {
        toast({
          title: 'No Analyzed Policies',
          description: 'Please analyze a policy first before running simulations.',
          variant: 'destructive',
        });
        return;
      }

      const latestPolicy = analyzedPolicies[0];

      // Call backend simulation
      const result = await base44.functions.invoke('run_simulation', {
        policy_id: latestPolicy.id,
        control_ids: selectedControls,
      });

      if (result.success) {
        // Transform backend response to UI format
        const projectedScores = {};
        result.projected_results.forEach(r => {
          projectedScores[r.framework] = r.projected_score;
        });

        setSimulationResults({
          currentScores,
          projectedScores,
          controlsImplemented: result.controls_implemented,
          gapsResolved: result.gaps_resolved,
        });
        setSimulationRun(true);
      }
    } catch (error) {
      toast({
        title: 'Simulation Failed',
        description: error.message || 'Failed to run simulation',
        variant: 'destructive',
      });
    }
  };

  const resetSimulation = () => {
    setSelectedControls([]);
    setSimulationRun(false);
    setSimulationResults(null);
  };

  // Prepare chart data
  const chartData = simulationResults ? [
    {
      framework: 'NCA ECC',
      current: simulationResults.currentScores['NCA ECC'],
      projected: simulationResults.projectedScores['NCA ECC'],
    },
    {
      framework: 'ISO 27001',
      current: simulationResults.currentScores['ISO 27001'],
      projected: simulationResults.projectedScores['ISO 27001'],
    },
    {
      framework: 'NIST 800-53',
      current: simulationResults.currentScores['NIST 800-53'],
      projected: simulationResults.projectedScores['NIST 800-53'],
    },
  ] : [];

  const totalImpact = simulationResults 
    ? Object.keys(simulationResults.projectedScores).reduce((acc, fw) => {
        return acc + (simulationResults.projectedScores[fw] - simulationResults.currentScores[fw]);
      }, 0)
    : 0;

  return (
    <PageContainer
      title="Compliance Simulation"
      subtitle="Predict the impact of implementing additional controls"
      actions={
        <Badge className="bg-amber-100 text-amber-700 border-amber-200 gap-1">
          <FlaskConical className="w-3 h-3" />
          BETA
        </Badge>
      }
    >
      {/* Info Banner */}
      <Card className="mb-6 bg-gradient-to-r from-amber-50 to-orange-50 border-amber-200">
        <CardContent className="p-4 flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <h3 className="font-semibold text-amber-900 mb-1">What-If Analysis</h3>
            <p className="text-sm text-amber-700">
              Select controls you plan to implement and see the predicted impact on your compliance scores. 
              This simulation helps prioritize remediation efforts for maximum compliance improvement.
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Control Selection */}
        <Card className="lg:col-span-1 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Shield className="w-5 h-5 text-emerald-600" />
              Select Controls to Implement
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="mb-4">
              <Select value={selectedFramework} onValueChange={setSelectedFramework}>
                <SelectTrigger>
                  <SelectValue placeholder="Filter by framework" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Frameworks</SelectItem>
                  <SelectItem value="NCA ECC">NCA ECC</SelectItem>
                  <SelectItem value="ISO 27001">ISO 27001</SelectItem>
                  <SelectItem value="NIST 800-53">NIST 800-53</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
              {filteredControls.map(control => (
                <div 
                  key={control.id}
                  className={`p-3 rounded-lg border transition-all cursor-pointer ${
                    selectedControls.includes(control.id)
                      ? 'bg-emerald-50 border-emerald-300'
                      : 'bg-white border-slate-200 hover:border-emerald-200'
                  }`}
                  onClick={() => toggleControl(control.id)}
                >
                  <div className="flex items-start gap-3">
                    <Checkbox 
                      checked={selectedControls.includes(control.id)}
                      onCheckedChange={() => toggleControl(control.id)}
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge variant="outline" className="font-mono text-xs">
                          {control.id}
                        </Badge>
                        <Badge className="bg-slate-100 text-slate-600 text-xs">
                          +{control.impact}%
                        </Badge>
                      </div>
                      <p className="text-sm font-medium">{control.name}</p>
                      <p className="text-xs text-slate-500">{control.framework}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 pt-4 border-t border-slate-200">
              <p className="text-sm text-slate-500 mb-3">
                {selectedControls.length} controls selected
              </p>
              <div className="flex gap-2">
                <Button 
                  onClick={runSimulation}
                  disabled={selectedControls.length === 0}
                  className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                >
                  <Play className="w-4 h-4 mr-2" />
                  Run Simulation
                </Button>
                <Button 
                  variant="outline" 
                  onClick={resetSimulation}
                  disabled={selectedControls.length === 0}
                >
                  <RotateCcw className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        <Card className="lg:col-span-2 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-emerald-600" />
              Simulation Results
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!simulationRun ? (
              <div className="h-80 flex flex-col items-center justify-center text-center">
                <FlaskConical className="w-16 h-16 text-slate-200 mb-4" />
                <h3 className="text-lg font-semibold text-slate-900 mb-1">No simulation run yet</h3>
                <p className="text-sm text-slate-500 max-w-md">
                  Select the controls you want to implement from the list on the left, 
                  then click "Run Simulation" to see the predicted impact.
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Impact Summary */}
                <div className="grid grid-cols-3 gap-4">
                  <Card className="bg-emerald-50 border-emerald-200">
                    <CardContent className="p-4 text-center">
                      <TrendingUp className="w-6 h-6 text-emerald-600 mx-auto mb-2" />
                      <p className="text-2xl font-bold text-emerald-700">+{Math.round(totalImpact / 3)}%</p>
                      <p className="text-xs text-emerald-600">Avg. Score Increase</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-blue-50 border-blue-200">
                    <CardContent className="p-4 text-center">
                      <CheckCircle2 className="w-6 h-6 text-blue-600 mx-auto mb-2" />
                      <p className="text-2xl font-bold text-blue-700">{simulationResults.controlsImplemented}</p>
                      <p className="text-xs text-blue-600">Controls Implemented</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-amber-50 border-amber-200">
                    <CardContent className="p-4 text-center">
                      <AlertTriangle className="w-6 h-6 text-amber-600 mx-auto mb-2" />
                      <p className="text-2xl font-bold text-amber-700">{simulationResults.gapsResolved}</p>
                      <p className="text-xs text-amber-600">Gaps Resolved</p>
                    </CardContent>
                  </Card>
                </div>

                {/* Comparison Chart */}
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 12 }} />
                      <YAxis dataKey="framework" type="category" tick={{ fontSize: 12 }} width={100} />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: '#fff', 
                          border: '1px solid #e2e8f0',
                          borderRadius: '8px'
                        }}
                        formatter={(value) => [`${value}%`]}
                      />
                      <Legend />
                      <Bar dataKey="current" name="Current Score" fill="#94a3b8" radius={[0, 4, 4, 0]} />
                      <Bar dataKey="projected" name="Projected Score" fill="#10b981" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Detailed Breakdown */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-slate-700">Score Breakdown</h4>
                  {Object.keys(simulationResults.projectedScores).map(framework => {
                    const current = simulationResults.currentScores[framework];
                    const projected = simulationResults.projectedScores[framework];
                    const improvement = projected - current;
                    
                    return (
                      <div key={framework} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="font-medium">{framework}</span>
                          <span>
                            <span className="text-slate-500">{current}%</span>
                            <span className="mx-2">→</span>
                            <span className="text-emerald-600 font-medium">{projected}%</span>
                            <span className="text-emerald-600 text-xs ml-1">(+{improvement}%)</span>
                          </span>
                        </div>
                        <div className="relative h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div 
                            className="absolute h-full bg-slate-300 rounded-full"
                            style={{ width: `${current}%` }}
                          />
                          <div 
                            className="absolute h-full bg-emerald-500 rounded-full transition-all"
                            style={{ width: `${projected}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}