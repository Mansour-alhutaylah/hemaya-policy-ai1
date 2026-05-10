import React, { useMemo, useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import PageContainer from '@/components/layout/PageContainer';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Brain,
  Search,
  Filter,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Shield,
  Info,
  ExternalLink,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';

const MappingReview = api.entities.MappingReview;
const Policy = api.entities.Policy;

const CONFIDENCE_THRESHOLD = 0.6;

export default function Explainability() {
  const [searchQuery, setSearchQuery] = useState('');
  const [frameworkFilter, setFrameworkFilter] = useState('all');
  const [confidenceFilter, setConfidenceFilter] = useState('all');
  const [policyId, setPolicyId] = useState('all');

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-last_analyzed_at'),
  });

  // Default selection: most recent analyzed policy. Skipped if the user
  // has already picked something — including 'all'.
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

  const selectedPolicy = useMemo(
    () => policies.find(p => p.id === policyId),
    [policies, policyId],
  );

  const { data: mappings = [], isLoading } = useQuery({
    queryKey: ['mappingReviews', policyId],
    queryFn: () => MappingReview.list('-created_at'),
  });

  const policyMap = useMemo(
    () => policies.reduce((acc, p) => { acc[p.id] = p; return acc; }, {}),
    [policies],
  );

  // Mappings scoped to the selected policy (if any). 'all' shows everything.
  const scopedMappings = useMemo(() => {
    if (policyId === 'all') return mappings;
    return mappings.filter(m => m.policy_id === policyId);
  }, [mappings, policyId]);

  // Build the framework filter options dynamically from real data so the
  // dropdown matches what the user actually has — earlier this was hardcoded
  // to NCA ECC / ISO 27001 / NIST 800-53, which never matches ECC-2 or SACS-002.
  const frameworkOptions = useMemo(() => {
    const set = new Set();
    scopedMappings.forEach(m => { if (m.framework) set.add(m.framework); });
    return Array.from(set).sort();
  }, [scopedMappings]);

  const filteredMappings = scopedMappings.filter(mapping => {
    const matchesSearch =
      !searchQuery ||
      mapping.control_id?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      mapping.evidence_snippet?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFramework = frameworkFilter === 'all' || mapping.framework === frameworkFilter;
    const matchesConfidence = confidenceFilter === 'all' ||
      (confidenceFilter === 'low' && (mapping.confidence_score || 0) < CONFIDENCE_THRESHOLD) ||
      (confidenceFilter === 'high' && (mapping.confidence_score || 0) >= CONFIDENCE_THRESHOLD);
    return matchesSearch && matchesFramework && matchesConfidence;
  });

  const getConfidenceColor = (score) => {
    if (score >= 0.8) return {
      bg: 'bg-emerald-100 dark:bg-emerald-500/15',
      text: 'text-emerald-700 dark:text-emerald-300',
      bar: 'bg-emerald-500',
    };
    if (score >= 0.6) return {
      bg: 'bg-amber-100 dark:bg-amber-500/15',
      text: 'text-amber-700 dark:text-amber-300',
      bar: 'bg-amber-500',
    };
    return {
      bg: 'bg-red-100 dark:bg-red-500/15',
      text: 'text-red-700 dark:text-red-300',
      bar: 'bg-red-500',
    };
  };

  // Empty-state copy chosen based on what the user is actually looking at,
  // so they know whether to upload a policy, run an analysis, or just pick
  // a different filter.
  const emptyState = (() => {
    if (policies.length === 0) {
      return {
        title: 'No policies yet',
        body: 'Upload a policy and run a compliance analysis to generate AI mappings with explanations.',
      };
    }
    if (policyId !== 'all' && selectedPolicy && selectedPolicy.status !== 'analyzed') {
      return {
        title: 'This policy has not been analysed yet',
        body: 'Run an analysis from the Policies page first to generate explanations.',
      };
    }
    if (filteredMappings.length === 0 && scopedMappings.length > 0) {
      return {
        title: 'No mappings match the current filters',
        body: 'Clear the search box or change the framework / confidence filters above.',
      };
    }
    return {
      title: 'No mappings found',
      body: policyId === 'all'
        ? 'Run a compliance analysis on any policy to generate AI mappings with explanations.'
        : 'No mappings have been generated for this policy yet.',
    };
  })();

  return (
    <PageContainer
      title="Explainability (XAI)"
      subtitle="Understand why AI made each compliance mapping decision"
      actions={
        <Badge className="bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30 gap-1">
          <Brain className="w-3 h-3" />
          Explainable AI
        </Badge>
      }
    >
      {/* Info Banner */}
      <Card className="mb-6 bg-gradient-to-r from-purple-50 to-indigo-50 border-purple-200 dark:from-purple-500/10 dark:to-indigo-500/10 dark:border-purple-500/30">
        <CardContent className="p-4 flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-purple-100 dark:bg-purple-500/20 flex items-center justify-center flex-shrink-0">
            <Info className="w-5 h-5 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <h3 className="font-semibold text-purple-900 dark:text-purple-200 mb-1">Understanding AI Decisions</h3>
            <p className="text-sm text-purple-700 dark:text-purple-300">
              This page provides transparency into how the AI system maps policy content to compliance controls.
              Each mapping includes the matched evidence, confidence score, and AI rationale.
              Low confidence mappings ({`<${CONFIDENCE_THRESHOLD * 100}%`}) are flagged for human review.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Filters */}
      <div className="flex flex-col lg:flex-row gap-4 mb-6">
        <Select value={policyId} onValueChange={setPolicyId}>
          <SelectTrigger className="w-full lg:w-72">
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

        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by control ID or evidence..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>

        <Select value={frameworkFilter} onValueChange={setFrameworkFilter}>
          <SelectTrigger className="w-44">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Framework" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All frameworks</SelectItem>
            {frameworkOptions.map(fw => (
              <SelectItem key={fw} value={fw}>{fw}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={confidenceFilter} onValueChange={setConfidenceFilter}>
          <SelectTrigger className="w-44">
            <Brain className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Confidence" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All confidence</SelectItem>
            <SelectItem value="low">Low confidence</SelectItem>
            <SelectItem value="high">High confidence</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Mappings List */}
      <div className="space-y-4">
        {filteredMappings.map((mapping) => {
          const confidence = mapping.confidence_score || 0;
          const colors = getConfidenceColor(confidence);
          const isLowConfidence = confidence < CONFIDENCE_THRESHOLD;
          const policy = policyMap[mapping.policy_id];
          const policyName = mapping.policy_file_name || policy?.file_name || '—';
          const controlCode = mapping.control_id || '—';
          const reviewLinkParams = new URLSearchParams();
          if (mapping.policy_id) reviewLinkParams.set('policy_id', mapping.policy_id);
          if (mapping.control_id) reviewLinkParams.set('control', mapping.control_id);
          const reviewLink = createPageUrl(
            reviewLinkParams.toString()
              ? `MappingReview?${reviewLinkParams.toString()}`
              : 'MappingReview',
          );

          return (
            <Card key={mapping.id} className="shadow-sm overflow-hidden">
              {isLowConfidence && (
                <div className="bg-amber-50 border-b border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/30 px-4 py-2 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                  <span className="text-sm font-medium text-amber-700 dark:text-amber-300">
                    Low Confidence - Human Review Recommended
                  </span>
                </div>
              )}

              <CardContent className="p-6">
                {/* Policy + framework header — replaces the previous control-only badge row */}
                <div className="flex items-start justify-between mb-3 gap-3">
                  <div className="min-w-0">
                    <p className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1">
                      <FileText className="w-3.5 h-3.5" />
                      <span className="truncate" title={policyName}>{policyName}</span>
                    </p>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="outline" className="font-mono text-sm">
                        {controlCode}
                      </Badge>
                      <Badge className="bg-muted text-foreground border border-border">
                        <Shield className="w-3 h-3 mr-1" />
                        {mapping.framework || 'Unknown framework'}
                      </Badge>
                      {mapping.decision && mapping.decision !== 'Pending' && (
                        <Badge className={
                          mapping.decision === 'Accepted' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' :
                          mapping.decision === 'Rejected' ? 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' :
                          'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300'
                        }>
                          {mapping.decision === 'Accepted' && <CheckCircle2 className="w-3 h-3 mr-1" />}
                          {mapping.decision}
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Confidence score */}
                  <div className={`${colors.bg} ${colors.text} px-3 py-1.5 rounded-lg shrink-0`}>
                    <span className="text-sm font-medium">{Math.round(confidence * 100)}% Confidence</span>
                  </div>
                </div>

                <Accordion type="single" collapsible className="w-full">
                  <AccordionItem value="evidence" className="border-0">
                    <AccordionTrigger className="hover:no-underline py-2">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <FileText className="w-4 h-4 text-muted-foreground" />
                        Matched Evidence
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="bg-muted/50 border border-border rounded-lg p-4 mt-2">
                        {mapping.evidence_snippet
                          ? <p className="text-sm text-foreground italic">"{mapping.evidence_snippet}"</p>
                          : <p className="text-sm text-muted-foreground">Evidence not available.</p>}
                      </div>
                    </AccordionContent>
                  </AccordionItem>

                  <AccordionItem value="rationale" className="border-0">
                    <AccordionTrigger className="hover:no-underline py-2">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Brain className="w-4 h-4 text-purple-500 dark:text-purple-400" />
                        AI Rationale
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="bg-purple-50 rounded-lg p-4 mt-2 border border-purple-200 dark:bg-purple-500/10 dark:border-purple-500/30">
                        {mapping.ai_rationale
                          ? <p className="text-sm text-purple-800 dark:text-purple-200 whitespace-pre-wrap">{mapping.ai_rationale}</p>
                          : <p className="text-sm text-muted-foreground">Rationale not available.</p>}

                        {mapping.matched_keywords && mapping.matched_keywords.length > 0 && (
                          <div className="mt-3">
                            <p className="text-xs font-medium text-purple-600 dark:text-purple-300 mb-1">Matched Keywords:</p>
                            <div className="flex flex-wrap gap-1">
                              {mapping.matched_keywords.map((keyword, idx) => (
                                <Badge key={idx} variant="outline" className="text-xs bg-card">
                                  {keyword}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}

                        {mapping.similarity_score && (
                          <div className="mt-3">
                            <p className="text-xs font-medium text-purple-600 dark:text-purple-300 mb-1">Semantic Similarity:</p>
                            <div className="flex items-center gap-2">
                              <Progress value={mapping.similarity_score * 100} className="h-2 flex-1" />
                              <span className="text-xs font-medium text-foreground">{Math.round(mapping.similarity_score * 100)}%</span>
                            </div>
                          </div>
                        )}
                      </div>
                    </AccordionContent>
                  </AccordionItem>

                  {isLowConfidence && mapping.uncertainty_reason && (
                    <AccordionItem value="uncertainty" className="border-0">
                      <AccordionTrigger className="hover:no-underline py-2">
                        <div className="flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-300">
                          <AlertTriangle className="w-4 h-4" />
                          Uncertainty Explanation
                        </div>
                      </AccordionTrigger>
                      <AccordionContent>
                        <div className="bg-amber-50 rounded-lg p-4 mt-2 border border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/30">
                          <p className="text-sm text-amber-800 dark:text-amber-200">{mapping.uncertainty_reason}</p>
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  )}
                </Accordion>

                <div className="flex justify-end mt-4">
                  <Link to={reviewLink}>
                    <Button variant="ghost" size="sm" className="text-emerald-600 dark:text-emerald-400">
                      Review Mapping
                      <ExternalLink className="w-3 h-3 ml-1" />
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {filteredMappings.length === 0 && !isLoading && (
        <Card className="shadow-sm">
          <CardContent className="py-16 text-center">
            <Brain className="w-12 h-12 text-muted-foreground/40 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-1">{emptyState.title}</h3>
            <p className="text-sm text-muted-foreground">{emptyState.body}</p>
          </CardContent>
        </Card>
      )}
    </PageContainer>
  );
}
