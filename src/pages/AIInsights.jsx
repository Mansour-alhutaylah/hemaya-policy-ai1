import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
import StatsCard from '@/components/ui/StatsCard';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
  Sparkles,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';

const AIInsight = api.entities.AIInsight;
const Policy = api.entities.Policy;

const insightTypeConfig = {
  gap_priority: {
    icon: AlertTriangle,
    color: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300',
  },
  policy_improvement: {
    icon: FileText,
    color: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
  },
  control_recommendation: {
    icon: Shield,
    color: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300',
  },
  risk_alert: {
    icon: AlertTriangle,
    color: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  },
  trend_analysis: {
    icon: TrendingUp,
    color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
  },
};

const priorityColors = {
  Critical: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30',
  High:     'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-500/15 dark:text-orange-300 dark:border-orange-500/30',
  Medium:   'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30',
  Low:      'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/15 dark:text-green-300 dark:border-green-500/30',
};

export default function AIInsightsPage() {
  const [selectedInsight, setSelectedInsight] = useState(null);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const [activeTab, setActiveTab] = useState('all');
  const [policyId, setPolicyId] = useState('all');

  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: insights = [], isLoading } = useQuery({
    queryKey: ['aiInsights'],
    queryFn: () => AIInsight.list('-created_at'),
  });

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-last_analyzed_at'),
  });

  // Default selection: most recent analyzed policy. Only set once so the user
  // can switch to "All policies" without it being overridden on the next render.
  const [hasInitedSelection, setHasInitedSelection] = useState(false);
  useEffect(() => {
    if (hasInitedSelection) return;
    if (policies.length === 0) return;
    const analyzed = policies.find(p => p.status === 'analyzed');
    if (analyzed) {
      setPolicyId(analyzed.id);
    }
    setHasInitedSelection(true);
  }, [policies, hasInitedSelection]);

  const policyMap = useMemo(
    () => policies.reduce((acc, p) => { acc[p.id] = p; return acc; }, {}),
    [policies],
  );

  const selectedPolicy = useMemo(
    () => policies.find(p => p.id === policyId),
    [policies, policyId],
  );

  // Phase HOTFIX: only real backend insights are shown. The previous
  // generateDerivedInsights() helper fabricated cards including a hardcoded
  // "improved by 8%" trend and a "Policy Language Enhancement Opportunity"
  // citing fake sections "3.2, 4.1, 5.3". Per the user's spec we don't show
  // any insight unless it came from the ai_insights table.
  const scopedInsights = useMemo(() => {
    if (policyId === 'all') return insights;
    return insights.filter(i => i.policy_id === policyId);
  }, [insights, policyId]);

  const updateInsightMutation = useMutation({
    mutationFn: ({ id, data }) => AIInsight.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['aiInsights'] });
    },
  });

  const filteredInsights = scopedInsights.filter(insight => {
    if (activeTab === 'all') return true;
    if (activeTab === 'new') return insight.status === 'New';
    if (activeTab === 'actioned') return insight.status === 'Actioned';
    return insight.insight_type === activeTab;
  });

  const newCount      = scopedInsights.filter(i => i.status === 'New').length;
  const criticalCount = scopedInsights.filter(i => i.priority === 'Critical').length;
  const highCount     = scopedInsights.filter(i => i.priority === 'High').length;

  const handleViewInsight = (insight) => {
    setSelectedInsight(insight);
    setShowDetailDialog(true);
    if (insight.status === 'New' && insight.id) {
      updateInsightMutation.mutate({
        id: insight.id,
        data: { status: 'Viewed' },
      });
    }
  };

  const handleActionInsight = (insight, action) => {
    if (insight?.id) {
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

  // Empty-state copy reflects the real reason there are no insights:
  // no policies / selected policy not analysed / analysed but nothing
  // generated yet / matched filter is empty. Never claims fabricated data.
  const emptyState = (() => {
    if (policies.length === 0) {
      return {
        title: 'No policies yet',
        body: 'Upload a policy and run a compliance analysis to generate AI insights.',
      };
    }
    if (policyId !== 'all' && selectedPolicy && selectedPolicy.status !== 'analyzed') {
      return {
        title: 'This policy has not been analysed yet',
        body: 'Run an analysis from the Policies page first to generate insights.',
      };
    }
    if (filteredInsights.length === 0 && scopedInsights.length > 0) {
      return {
        title: 'No insights match the current filter',
        body: 'Switch to a different tab or change the policy selector above.',
      };
    }
    return {
      title: 'No insights generated yet',
      body: 'Once analysis writes insights for a policy they will appear here. In the meantime, review the Gaps & Risks and Mapping Review pages for actionable items.',
    };
  })();

  return (
    <PageContainer
      title="AI Insights"
      subtitle="AI-powered recommendations and compliance intelligence"
      actions={
        <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30 gap-1">
          <Sparkles className="w-3 h-3" />
          Powered by AI
        </Badge>
      }
    >
      {/* Policy selector */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <Select value={policyId} onValueChange={setPolicyId}>
          <SelectTrigger className="w-full sm:w-80">
            <FileText className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Policy" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All policies</SelectItem>
            {policies.map(p => (
              <SelectItem key={p.id} value={p.id}>
                {p.file_name || p.id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Stats — every count comes straight from the scoped insights array */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatsCard title="New Insights"      value={newCount}              icon={Lightbulb}     variant="emerald" />
        <StatsCard title="Critical Priority" value={criticalCount}         icon={AlertTriangle} variant={criticalCount > 0 ? 'red'   : 'default'} />
        <StatsCard title="High Priority"     value={highCount}             icon={AlertTriangle} variant={highCount > 0     ? 'amber' : 'default'} />
        <StatsCard title="Total Insights"    value={scopedInsights.length} icon={Brain} />
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
            <Brain className="w-12 h-12 text-muted-foreground/60 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-1">{emptyState.title}</h3>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">{emptyState.body}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredInsights.map((insight) => {
            const config = insightTypeConfig[insight.insight_type] || insightTypeConfig.trend_analysis;
            const Icon = config.icon;
            const policy = policyMap[insight.policy_id];

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
                        <Badge className={`${priorityColors[insight.priority] || ''} border text-xs`}>
                          {insight.priority || 'Medium'}
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
                  {policy && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1.5 mb-2">
                      <FileText className="w-3.5 h-3.5" />
                      <span className="truncate" title={policy.file_name}>{policy.file_name}</span>
                    </p>
                  )}
                  <h3 className="font-semibold text-foreground mb-2 line-clamp-2">
                    {insight.title}
                  </h3>
                  <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
                    {insight.description}
                  </p>
                  <div className="flex items-center justify-between">
                    {insight.framework && (
                      <Badge variant="outline" className="text-xs">
                        <Shield className="w-3 h-3 mr-1" />
                        {insight.framework}
                      </Badge>
                    )}
                    {typeof insight.confidence === 'number' && (
                      <span className="text-xs text-muted-foreground">
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
              <Lightbulb className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              AI Insight
            </DialogTitle>
          </DialogHeader>

          {selectedInsight && (
            <div className="space-y-6 py-4">
              <div className="flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl ${insightTypeConfig[selectedInsight.insight_type]?.color || 'bg-muted text-muted-foreground'} flex items-center justify-center`}>
                  {(() => {
                    const Icon = insightTypeConfig[selectedInsight.insight_type]?.icon || Lightbulb;
                    return <Icon className="w-6 h-6" />;
                  })()}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <Badge className={`${priorityColors[selectedInsight.priority] || ''} border`}>
                      {selectedInsight.priority || 'Medium'} Priority
                    </Badge>
                    {selectedInsight.framework && (
                      <Badge variant="outline">
                        <Shield className="w-3 h-3 mr-1" />
                        {selectedInsight.framework}
                      </Badge>
                    )}
                  </div>
                  <h3 className="text-lg font-semibold text-foreground">{selectedInsight.title}</h3>
                  {policyMap[selectedInsight.policy_id] && (
                    <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5" />
                      {policyMap[selectedInsight.policy_id].file_name}
                    </p>
                  )}
                </div>
              </div>

              <div className="bg-muted/50 border border-border rounded-lg p-4">
                <p className="text-foreground">{selectedInsight.description}</p>
              </div>

              {selectedInsight.evidence_snippet && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground mb-2">Evidence Reference</p>
                  <div className="bg-blue-50 border border-blue-200 dark:bg-blue-500/10 dark:border-blue-500/30 rounded-lg p-4">
                    <p className="text-sm text-blue-700 dark:text-blue-300 italic">"{selectedInsight.evidence_snippet}"</p>
                  </div>
                </div>
              )}

              {selectedInsight.control_reference && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground mb-2">Control Reference</p>
                  <Badge variant="outline" className="font-mono">
                    {selectedInsight.control_reference}
                  </Badge>
                </div>
              )}

              {typeof selectedInsight.confidence === 'number' && (
                <div className="flex items-center gap-2">
                  <Brain className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">
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
              className="text-muted-foreground"
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
