/**
 * RemediationExplainability
 *
 * Explainable-AI panel that surfaces the reasoning behind a remediation draft.
 * Designed to answer: "Why was this addition suggested, and which control does it satisfy?"
 *
 * Props:
 *   data — the object returned by GET /api/remediation/drafts/{draft_id}
 *          Expected keys: control_code, control_title, framework_name,
 *                         missing_requirements, section_headers, ai_rationale
 */
import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Brain, Shield, AlertTriangle, CheckCircle2, ArrowRight,
  ChevronDown, Lightbulb, GitMerge, ListChecks,
} from 'lucide-react';

// ── Helpers ───────────────────────────────────────────────────────────────────

function Chip({ children, className = '' }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${className}`}>
      {children}
    </span>
  );
}

function CollapsibleSection({ icon: Icon, title, iconClass, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border/60 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-muted/20 hover:bg-muted/40 transition-colors text-left"
      >
        <span className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
          <Icon className={`w-3.5 h-3.5 ${iconClass}`} />
          {title}
        </span>
        <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-4 pb-4 pt-3">{children}</div>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function RemediationExplainability({ data }) {
  if (!data) return null;

  const {
    control_code      = '',
    control_title     = '',
    framework_name    = '',
    missing_requirements = [],
    section_headers   = [],
    ai_rationale      = '',
  } = data;

  const hasContent = control_code || missing_requirements.length || section_headers.length || ai_rationale;
  if (!hasContent) return null;

  return (
    <Card className="border-purple-500/20 bg-purple-500/[.03] dark:bg-purple-500/[.05]">
      <CardHeader className="pb-2 pt-4 px-5">
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-semibold text-purple-700 dark:text-purple-300">
            <Brain className="w-4 h-4" />
            Why This Remediation Was Suggested
          </span>
          <Badge className="text-[10px] bg-purple-100 text-purple-700 border border-purple-200 dark:bg-purple-500/20 dark:text-purple-300 dark:border-purple-500/30 gap-1">
            <Lightbulb className="w-2.5 h-2.5" />
            XAI
          </Badge>
        </CardTitle>
      </CardHeader>

      <CardContent className="px-5 pb-5 space-y-4">

        {/* Compliance gap chain ──────────────────────────────────────────── */}
        {(control_code || framework_name) && (
          <div className="flex items-center gap-2 flex-wrap text-xs">
            <span className="text-muted-foreground font-medium">Gap traced to:</span>
            {control_code && (
              <Chip className="bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-300 gap-1">
                <AlertTriangle className="w-2.5 h-2.5" />
                {control_code}
              </Chip>
            )}
            {framework_name && (
              <>
                <ArrowRight className="w-3 h-3 text-muted-foreground shrink-0" />
                <Chip className="bg-blue-500/10 border-blue-500/30 text-blue-700 dark:text-blue-300 gap-1">
                  <Shield className="w-2.5 h-2.5" />
                  {framework_name}
                </Chip>
              </>
            )}
            {control_title && (
              <>
                <ArrowRight className="w-3 h-3 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground italic">{control_title}</span>
              </>
            )}
          </div>
        )}

        {/* AI reasoning ──────────────────────────────────────────────────── */}
        {ai_rationale && (
          <CollapsibleSection
            icon={Brain}
            title="AI Reasoning"
            iconClass="text-purple-500"
            defaultOpen
          >
            <p className="text-xs text-purple-800 dark:text-purple-200/90 leading-relaxed">
              {ai_rationale}
            </p>
          </CollapsibleSection>
        )}

        {/* Missing requirements ───────────────────────────────────────────── */}
        {missing_requirements.length > 0 && (
          <CollapsibleSection
            icon={ListChecks}
            title={`Requirements That Triggered This Draft (${missing_requirements.length})`}
            iconClass="text-amber-500"
            defaultOpen
          >
            <ol className="space-y-2">
              {missing_requirements.map((req, i) => (
                <li key={i} className="flex items-start gap-2 text-xs">
                  <span className="shrink-0 w-4 h-4 mt-0.5 rounded-full bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-[10px] font-bold text-amber-700 dark:text-amber-300">
                    {i + 1}
                  </span>
                  <span className="text-amber-800 dark:text-amber-200/90">{req}</span>
                </li>
              ))}
            </ol>
          </CollapsibleSection>
        )}

        {/* Control satisfaction mapping ───────────────────────────────────── */}
        {section_headers.length > 0 && control_code && (
          <CollapsibleSection
            icon={GitMerge}
            title="Control Satisfaction Mapping"
            iconClass="text-emerald-500"
            defaultOpen
          >
            <p className="text-xs text-muted-foreground mb-3">
              Each generated section directly satisfies the compliance requirement:
            </p>
            <div className="space-y-2">
              {section_headers.map((header, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2.5 p-2.5 rounded-lg bg-emerald-500/8 border border-emerald-500/20"
                >
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-medium text-emerald-800 dark:text-emerald-200">
                      &ldquo;{header}&rdquo;
                    </span>
                    <div className="flex items-center gap-1 mt-0.5 flex-wrap">
                      <span className="text-[10px] text-muted-foreground">satisfies</span>
                      <Chip className="text-[10px] bg-emerald-500/10 border-emerald-500/25 text-emerald-700 dark:text-emerald-300">
                        {control_code}
                      </Chip>
                      {framework_name && (
                        <span className="text-[10px] text-muted-foreground">{framework_name}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

      </CardContent>
    </Card>
  );
}
