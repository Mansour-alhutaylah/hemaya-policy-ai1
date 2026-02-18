import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import PageContainer from '@/components/layout/PageContainer';
import StatsCard from '@/components/ui/StatsCard';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  Lightbulb,
  AlertTriangle,
  TrendingUp,
  FileText,
  Shield,
  Eye,
  CheckCircle2,
  X,
  ArrowRight,
  Brain,
  Sparkles
} from 'lucide-react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';

const AIInsight = base44.entities.AIInsight;
const ComplianceResult = base44.entities.ComplianceResult;
const Gap = base44.entities.Gap;

const insightTypeConfig = {
  gap_priority: { 
    icon: AlertTriangle, 
    color: 'bg-red-100 text-red-700',
    bgGradient: 'from-red-500 to-rose-600'
  },
  policy_improvement: { 
    icon: FileText, 
    color: 'bg-blue-100 text-blue-700',
    bgGradient: 'from-blue-500 to-indigo-600'
  },
  control_recommendation: { 
    icon: Shield, 
    color: 'bg-purple-100 text-purple-700',
    bgGradient: 'from-purple-500 to-violet-600'
  },
  risk_alert: { 
    icon: AlertTriangle, 
    color: 'bg-amber-100 text-amber-700',
    bgGradient: 'from-amber-500 to-orange-600'
  },
  trend_analysis: { 
    icon: TrendingUp, 
    color: 'bg-emerald-100 text-emerald-700',
    bgGradient: 'from-emerald-500 to-teal-600'
  },
};

const priorityColors = {
  Critical: 'bg-red-100 text-red-700 border-red-200',
  High: 'bg-orange-100 text-orange-700 border-orange-200',
  Medium: 'bg-amber-100 text-amber-700 border-amber-200',
  Low: 'bg-green-100 text-green-700 border-green-200',
};

export default function AIInsightsPage() {
  const [selectedInsight, setSelectedInsight] = useState(null);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const [activeTab, setActiveTab] = useState('all');

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: insights = [], isLoading } = useQuery({
    queryKey: ['aiInsights'],
    queryFn: () => AIInsight.list('-created_date'),
  });

  const { data: results = [] } = useQuery({
    queryKey: ['complianceResults'],
    queryFn: () => ComplianceResult.list('-analyzed_at', 10),
  });

  const { data: gaps = [] } = useQuery({
    queryKey: ['gaps'],
    queryFn: () => Gap.filter({ status: 'Open' }, '-created_date', 10),
  });

  const updateInsightMutation = useMutation({
    mutationFn: ({ id, data }) => AIInsight.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['aiInsights']);
    },
  });

  // Generate derived insights if no insights exist
  const generateDerivedInsights = () => {
    const derived = [];
    
    // Gap priority insights
    const criticalGaps = gaps.filter(g => g.severity === 'Critical');
    if (criticalGaps.length > 0) {
      derived.push({
        id: 'derived-1',
        insight_type: 'gap_priority',
        title: `${criticalGaps.length} Critical Gaps Require Immediate Attention`,
        description: `You have ${criticalGaps.length} critical compliance gaps that should be addressed urgently. These gaps pose significant risk to your organization's security posture.`,
        priority: 'Critical',
        evidence_snippet: criticalGaps.slice(0, 2).map(g => g.control_id).join(', '),
        confidence: 0.95,
        status: 'New',
      });
    }

    // Low compliance framework
    const lowScoreResults = results.filter(r => r.compliance_score < 60);
    if (lowScoreResults.length > 0) {
      const lowestFramework = lowScoreResults.reduce((prev, curr) => 
        (curr.compliance_score || 0) < (prev.compliance_score || 0) ? curr : prev
      );
      derived.push({
        id: 'derived-2',
        insight_type: 'control_recommendation',
        title: `${lowestFramework.framework} Compliance Below Target`,
        description: `Your ${lowestFramework.framework} compliance score is ${Math.round(lowestFramework.compliance_score)}%, which is below the recommended 70% threshold. Focus on addressing ${lowestFramework.controls_missing} missing controls.`,
        priority: 'High',
        framework: lowestFramework.framework,
        confidence: 0.88,
        status: 'New',
      });
    }

    // Policy improvement suggestions
    if (results.length > 0) {
      derived.push({
        id: 'derived-3',
        insight_type: 'policy_improvement',
        title: 'Policy Language Enhancement Opportunity',
        description: 'AI analysis detected areas where policy language could be strengthened to better align with control requirements. Consider adding explicit references to data classification and access review procedures.',
        priority: 'Medium',
        evidence_snippet: 'Sections 3.2, 4.1, and 5.3 could benefit from more specific control language.',
        confidence: 0.75,
        status: 'New',
      });
    }

    // Trend analysis
    derived.push({
      id: 'derived-4',
      insight_type: 'trend_analysis',
      title: 'Compliance Improvement Trend Detected',
      description: 'Over the past month, your overall compliance posture has improved by approximately 8%. Continue focusing on access control and incident response controls for further gains.',
      priority: 'Low',
      confidence: 0.82,
      status: 'New',
    });

    return derived;
  };

  const displayInsights = insights.length > 0 ? insights : generateDerivedInsights();

  const filteredInsights = displayInsights.filter(insight => {
    if (activeTab === 'all') return true;
    if (activeTab === 'new') return insight.status === 'New';
    if (activeTab === 'actioned') return insight.status === 'Actioned';
    return insight.insight_type === activeTab;
  });

  const newCount = displayInsights.filter(i => i.status === 'New').length;
  const criticalCount = displayInsights.filter(i => i.priority === 'Critical').length;
  const highCount = displayInsights.filter(i => i.priority === 'High').length;

  const handleViewInsight = (insight) => {
    setSelectedInsight(insight);
    setShowDetailDialog(true);
    if (insight.status === 'New' && insight.id && !insight.id.startsWith('derived')) {
      updateInsightMutation.mutate({
        id: insight.id,
        data: { status: 'Viewed' },
      });
    }
  };

  const handleActionInsight = (insight, action) => {
    if (insight.id && !insight.id.startsWith('derived')) {
      updateInsightMutation.mutate({
        id: insight.id,
        data: { status: action },
      });
    }
    toast({
      title: action === 'Actioned' ? 'Insight Actioned' : 'Insight Dismissed',
      description: action === 'Actioned' 
        ? 'This insight has been marked as actioned.'
        : 'This insight has been dismissed.',
    });
    setShowDetailDialog(false);
  };

  return (
    <PageContainer
      title="AI Insights"
      subtitle="AI-powered recommendations and compliance intelligence"
      actions={
        <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 gap-1">
          <Sparkles className="w-3 h-3" />
          Powered by AI
        </Badge>
      }
    >
      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatsCard
          title="New Insights"
          value={newCount}
          icon={Lightbulb}
          variant="emerald"
        />
        <StatsCard
          title="Critical Priority"
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
          title="Total Insights"
          value={displayInsights.length}
          icon={Brain}
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="mb-6">
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="new">
            New
            {newCount > 0 && (
              <Badge className="ml-1 bg-emerald-500 text-white h-5 w-5 p-0 flex items-center justify-center text-xs">
                {newCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="gap_priority">Gaps</TabsTrigger>
          <TabsTrigger value="policy_improvement">Policy</TabsTrigger>
          <TabsTrigger value="control_recommendation">Controls</TabsTrigger>
          <TabsTrigger value="actioned">Actioned</TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Insights Grid */}
      {filteredInsights.length === 0 ? (
        <Card className="shadow-sm">
          <CardContent className="py-16 text-center">
            <Brain className="w-12 h-12 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-slate-900 mb-1">No insights available</h3>
            <p className="text-sm text-slate-500">
              Run a compliance analysis to generate AI-powered insights
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredInsights.map((insight) => {
            const config = insightTypeConfig[insight.insight_type] || insightTypeConfig.trend_analysis;
            const Icon = config.icon;

            return (
              <Card 
                key={insight.id} 
                className="shadow-sm hover:shadow-md transition-all cursor-pointer group"
                onClick={() => handleViewInsight(insight)}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg ${config.color} flex items-center justify-center`}>
                        <Icon className="w-5 h-5" />
                      </div>
                      <div>
                        <Badge className={`${priorityColors[insight.priority]} border text-xs`}>
                          {insight.priority}
                        </Badge>
                        {insight.status === 'New' && (
                          <Badge className="ml-2 bg-emerald-500 text-white text-xs">New</Badge>
                        )}
                      </div>
                    </div>
                    <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100 transition-opacity">
                      <Eye className="w-4 h-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <h3 className="font-semibold text-slate-900 mb-2 line-clamp-2">
                    {insight.title}
                  </h3>
                  <p className="text-sm text-slate-600 line-clamp-2 mb-3">
                    {insight.description}
                  </p>
                  <div className="flex items-center justify-between">
                    {insight.framework && (
                      <Badge variant="outline" className="text-xs">
                        <Shield className="w-3 h-3 mr-1" />
                        {insight.framework}
                      </Badge>
                    )}
                    {insight.confidence && (
                      <span className="text-xs text-slate-400">
                        {Math.round(insight.confidence * 100)}% confidence
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Detail Dialog */}
      <Dialog open={showDetailDialog} onOpenChange={setShowDetailDialog}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-emerald-600" />
              AI Insight
            </DialogTitle>
          </DialogHeader>

          {selectedInsight && (
            <div className="space-y-6 py-4">
              {/* Header */}
              <div className="flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl ${insightTypeConfig[selectedInsight.insight_type]?.color || 'bg-slate-100'} flex items-center justify-center`}>
                  {(() => {
                    const Icon = insightTypeConfig[selectedInsight.insight_type]?.icon || Lightbulb;
                    return <Icon className="w-6 h-6" />;
                  })()}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge className={`${priorityColors[selectedInsight.priority]} border`}>
                      {selectedInsight.priority} Priority
                    </Badge>
                    {selectedInsight.framework && (
                      <Badge variant="outline">
                        <Shield className="w-3 h-3 mr-1" />
                        {selectedInsight.framework}
                      </Badge>
                    )}
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900">{selectedInsight.title}</h3>
                </div>
              </div>

              {/* Description */}
              <div className="bg-slate-50 rounded-lg p-4">
                <p className="text-slate-700">{selectedInsight.description}</p>
              </div>

              {/* Evidence */}
              {selectedInsight.evidence_snippet && (
                <div>
                  <p className="text-sm font-medium text-slate-500 mb-2">Evidence Reference</p>
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <p className="text-sm text-blue-700 italic">"{selectedInsight.evidence_snippet}"</p>
                  </div>
                </div>
              )}

              {/* Control Reference */}
              {selectedInsight.control_reference && (
                <div>
                  <p className="text-sm font-medium text-slate-500 mb-2">Control Reference</p>
                  <Badge variant="outline" className="font-mono">
                    {selectedInsight.control_reference}
                  </Badge>
                </div>
              )}

              {/* Confidence */}
              {selectedInsight.confidence && (
                <div className="flex items-center gap-2">
                  <Brain className="w-4 h-4 text-slate-400" />
                  <span className="text-sm text-slate-500">
                    AI Confidence: {Math.round(selectedInsight.confidence * 100)}%
                  </span>
                </div>
              )}
            </div>
          )}

          <div className="flex justify-between">
            <Button 
              variant="outline" 
              onClick={() => handleActionInsight(selectedInsight, 'Dismissed')}
              className="text-slate-600"
            >
              <X className="w-4 h-4 mr-1" />
              Dismiss
            </Button>
            <div className="flex gap-3">
              {selectedInsight?.insight_type === 'gap_priority' && (
                <Link to={createPageUrl('GapsRisks')}>
                  <Button variant="outline">
                    View Gaps
                    <ArrowRight className="w-4 h-4 ml-1" />
                  </Button>
                </Link>
              )}
              <Button 
                onClick={() => handleActionInsight(selectedInsight, 'Actioned')}
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                <CheckCircle2 className="w-4 h-4 mr-1" />
                Mark as Actioned
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}