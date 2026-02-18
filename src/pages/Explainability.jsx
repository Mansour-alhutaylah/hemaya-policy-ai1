import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import PageContainer from '@/components/layout/PageContainer';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
  Sparkles,
  ExternalLink
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';

const MappingReview = base44.entities.MappingReview;
const Policy = base44.entities.Policy;

const CONFIDENCE_THRESHOLD = 0.6;

export default function Explainability() {
  const [searchQuery, setSearchQuery] = useState('');
  const [frameworkFilter, setFrameworkFilter] = useState('all');
  const [confidenceFilter, setConfidenceFilter] = useState('all');

  const { data: mappings = [], isLoading } = useQuery({
    queryKey: ['mappingReviews'],
    queryFn: () => MappingReview.list('-created_date'),
  });

  const { data: policies = [] } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list(),
  });

  const policyMap = policies.reduce((acc, p) => {
    acc[p.id] = p;
    return acc;
  }, {});

  // Generate sample explanations if no real mappings
  const generateSampleExplanations = () => {
    return [
      {
        id: 'sample-1',
        control_id: 'A.5.1.1',
        framework: 'ISO 27001',
        evidence_snippet: 'The organization shall establish and maintain an information security policy that is approved by management, published, and communicated to employees.',
        confidence_score: 0.92,
        ai_rationale: 'High confidence match. The policy text directly addresses the requirement for management-approved security policies. Key phrases matched: "security policy", "approved by management", "communicated to employees".',
        decision: 'Accepted',
        matched_keywords: ['security policy', 'management approval', 'communication'],
        similarity_score: 0.89,
      },
      {
        id: 'sample-2',
        control_id: '2-1-1',
        framework: 'NCA ECC',
        evidence_snippet: 'Access to information systems shall be restricted based on business requirements and security classification of data.',
        confidence_score: 0.78,
        ai_rationale: 'Good match for access control requirements. The policy addresses data classification-based access but could be more specific about role-based access controls.',
        decision: 'Modified',
        matched_keywords: ['access control', 'data classification', 'restricted'],
        similarity_score: 0.75,
      },
      {
        id: 'sample-3',
        control_id: 'AC-2',
        framework: 'NIST 800-53',
        evidence_snippet: 'User accounts shall be reviewed quarterly to ensure appropriate access levels are maintained.',
        confidence_score: 0.45,
        ai_rationale: 'Partial match. The policy mentions account review but does not fully address all aspects of AC-2 including: account types, group membership, privileges, and account management procedures. Recommend human review.',
        decision: 'Pending',
        matched_keywords: ['user accounts', 'review', 'access levels'],
        similarity_score: 0.42,
        uncertainty_reason: 'Missing coverage of account types, group membership management, and detailed account lifecycle procedures.',
      },
      {
        id: 'sample-4',
        control_id: 'A.12.4.1',
        framework: 'ISO 27001',
        evidence_snippet: 'All security events shall be logged and monitored. Logs shall be protected from tampering and retained for a minimum of 12 months.',
        confidence_score: 0.88,
        ai_rationale: 'Strong match for event logging requirements. Policy addresses logging, monitoring, protection, and retention. Meets all key requirements of the control.',
        decision: 'Accepted',
        matched_keywords: ['logging', 'monitoring', 'retention', 'protection'],
        similarity_score: 0.85,
      },
      {
        id: 'sample-5',
        control_id: '3-2-4',
        framework: 'NCA ECC',
        evidence_snippet: 'Employees must complete security awareness training upon hire and annually thereafter.',
        confidence_score: 0.52,
        ai_rationale: 'Weak match. The policy addresses basic awareness training but does not cover specific NCA ECC requirements including: role-based training, phishing simulations, and training effectiveness measurement.',
        decision: 'Pending',
        matched_keywords: ['security awareness', 'training'],
        similarity_score: 0.48,
        uncertainty_reason: 'Missing role-based training differentiation, simulation exercises, and effectiveness metrics.',
      },
    ];
  };

  const displayMappings = mappings.length > 0 ? mappings : generateSampleExplanations();

  const filteredMappings = displayMappings.filter(mapping => {
    const matchesSearch = mapping.control_id?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      mapping.evidence_snippet?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFramework = frameworkFilter === 'all' || mapping.framework === frameworkFilter;
    const matchesConfidence = confidenceFilter === 'all' ||
      (confidenceFilter === 'low' && (mapping.confidence_score || 0) < CONFIDENCE_THRESHOLD) ||
      (confidenceFilter === 'high' && (mapping.confidence_score || 0) >= CONFIDENCE_THRESHOLD);
    return matchesSearch && matchesFramework && matchesConfidence;
  });

  const getConfidenceColor = (score) => {
    if (score >= 0.8) return { bg: 'bg-emerald-100', text: 'text-emerald-700', bar: 'bg-emerald-500' };
    if (score >= 0.6) return { bg: 'bg-amber-100', text: 'text-amber-700', bar: 'bg-amber-500' };
    return { bg: 'bg-red-100', text: 'text-red-700', bar: 'bg-red-500' };
  };

  return (
    <PageContainer
      title="Explainability (XAI)"
      subtitle="Understand why AI made each compliance mapping decision"
      actions={
        <Badge className="bg-purple-100 text-purple-700 border-purple-200 gap-1">
          <Brain className="w-3 h-3" />
          Explainable AI
        </Badge>
      }
    >
      {/* Info Banner */}
      <Card className="mb-6 bg-gradient-to-r from-purple-50 to-indigo-50 border-purple-200">
        <CardContent className="p-4 flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center flex-shrink-0">
            <Info className="w-5 h-5 text-purple-600" />
          </div>
          <div>
            <h3 className="font-semibold text-purple-900 mb-1">Understanding AI Decisions</h3>
            <p className="text-sm text-purple-700">
              This page provides transparency into how the AI system maps policy content to compliance controls. 
              Each mapping includes the matched evidence, confidence score, and AI rationale. 
              Low confidence mappings ({`<${CONFIDENCE_THRESHOLD * 100}%`}) are flagged for human review.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search by control ID or evidence..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select value={frameworkFilter} onValueChange={setFrameworkFilter}>
          <SelectTrigger className="w-40">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Framework" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Frameworks</SelectItem>
            <SelectItem value="NCA ECC">NCA ECC</SelectItem>
            <SelectItem value="ISO 27001">ISO 27001</SelectItem>
            <SelectItem value="NIST 800-53">NIST 800-53</SelectItem>
          </SelectContent>
        </Select>
        <Select value={confidenceFilter} onValueChange={setConfidenceFilter}>
          <SelectTrigger className="w-44">
            <Brain className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Confidence" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Confidence</SelectItem>
            <SelectItem value="low">Low Confidence</SelectItem>
            <SelectItem value="high">High Confidence</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Mappings List */}
      <div className="space-y-4">
        {filteredMappings.map((mapping) => {
          const confidence = mapping.confidence_score || 0;
          const colors = getConfidenceColor(confidence);
          const isLowConfidence = confidence < CONFIDENCE_THRESHOLD;

          return (
            <Card key={mapping.id} className="shadow-sm overflow-hidden">
              {isLowConfidence && (
                <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  <span className="text-sm font-medium text-amber-700">
                    Low Confidence - Human Review Recommended
                  </span>
                </div>
              )}
              
              <CardContent className="p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <Badge variant="outline" className="font-mono text-sm">
                      {mapping.control_id}
                    </Badge>
                    <Badge className="bg-slate-100 text-slate-700">
                      <Shield className="w-3 h-3 mr-1" />
                      {mapping.framework}
                    </Badge>
                    {mapping.decision && mapping.decision !== 'Pending' && (
                      <Badge className={
                        mapping.decision === 'Accepted' ? 'bg-emerald-100 text-emerald-700' :
                        mapping.decision === 'Rejected' ? 'bg-red-100 text-red-700' :
                        'bg-purple-100 text-purple-700'
                      }>
                        {mapping.decision === 'Accepted' && <CheckCircle2 className="w-3 h-3 mr-1" />}
                        {mapping.decision}
                      </Badge>
                    )}
                  </div>
                  
                  {/* Confidence Score */}
                  <div className={`${colors.bg} ${colors.text} px-3 py-1.5 rounded-lg`}>
                    <span className="text-sm font-medium">{Math.round(confidence * 100)}% Confidence</span>
                  </div>
                </div>

                <Accordion type="single" collapsible className="w-full">
                  <AccordionItem value="evidence" className="border-0">
                    <AccordionTrigger className="hover:no-underline py-2">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <FileText className="w-4 h-4 text-slate-500" />
                        Matched Evidence
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="bg-slate-50 rounded-lg p-4 mt-2">
                        <p className="text-sm text-slate-700 italic">
                          "{mapping.evidence_snippet}"
                        </p>
                      </div>
                    </AccordionContent>
                  </AccordionItem>

                  <AccordionItem value="rationale" className="border-0">
                    <AccordionTrigger className="hover:no-underline py-2">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Brain className="w-4 h-4 text-purple-500" />
                        AI Rationale
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="bg-purple-50 rounded-lg p-4 mt-2 border border-purple-200">
                        <p className="text-sm text-purple-800">{mapping.ai_rationale}</p>
                        
                        {/* Matched Keywords */}
                        {mapping.matched_keywords && (
                          <div className="mt-3">
                            <p className="text-xs font-medium text-purple-600 mb-1">Matched Keywords:</p>
                            <div className="flex flex-wrap gap-1">
                              {mapping.matched_keywords.map((keyword, idx) => (
                                <Badge key={idx} variant="outline" className="text-xs bg-white">
                                  {keyword}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                        
                        {/* Similarity Score */}
                        {mapping.similarity_score && (
                          <div className="mt-3">
                            <p className="text-xs font-medium text-purple-600 mb-1">Semantic Similarity:</p>
                            <div className="flex items-center gap-2">
                              <Progress value={mapping.similarity_score * 100} className="h-2 flex-1" />
                              <span className="text-xs font-medium">{Math.round(mapping.similarity_score * 100)}%</span>
                            </div>
                          </div>
                        )}
                      </div>
                    </AccordionContent>
                  </AccordionItem>

                  {/* Uncertainty Section for Low Confidence */}
                  {isLowConfidence && mapping.uncertainty_reason && (
                    <AccordionItem value="uncertainty" className="border-0">
                      <AccordionTrigger className="hover:no-underline py-2">
                        <div className="flex items-center gap-2 text-sm font-medium text-amber-700">
                          <AlertTriangle className="w-4 h-4" />
                          Uncertainty Explanation
                        </div>
                      </AccordionTrigger>
                      <AccordionContent>
                        <div className="bg-amber-50 rounded-lg p-4 mt-2 border border-amber-200">
                          <p className="text-sm text-amber-800">{mapping.uncertainty_reason}</p>
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  )}
                </Accordion>

                <div className="flex justify-end mt-4">
                  <Link to={createPageUrl(`MappingReview?control=${mapping.control_id}`)}>
                    <Button variant="ghost" size="sm" className="text-emerald-600">
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

      {filteredMappings.length === 0 && (
        <Card className="shadow-sm">
          <CardContent className="py-16 text-center">
            <Brain className="w-12 h-12 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-slate-900 mb-1">No mappings found</h3>
            <p className="text-sm text-slate-500">
              Run a compliance analysis to generate AI mappings with explanations
            </p>
          </CardContent>
        </Card>
      )}
    </PageContainer>
  );
}