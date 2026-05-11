import React from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import { useAuth } from '@/lib/AuthContext';
import PageContainer from '@/components/layout/PageContainer';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { createPageUrl } from '@/utils';
import {
  Upload,
  ArrowRight,
  ShieldCheck,
  FileText,
  LayoutDashboard,
  Shield,
  FileBarChart,
  Sparkles,
} from 'lucide-react';

const Policy = api.entities.Policy;

const primaryActions = [
  {
    label: 'Upload policy',
    description: 'Add a document and run compliance analysis',
    page: 'Policies',
    icon: Upload,
    accent: 'from-emerald-500 to-teal-600',
  },
  {
    label: 'Executive dashboard',
    description: 'Scores, gaps and coverage at a glance',
    page: 'Dashboard',
    icon: LayoutDashboard,
    accent: 'from-blue-500 to-indigo-600',
  },
  {
    label: 'Browse frameworks',
    description: 'NCA, SAMA, SDAIA, CST and sector-specific controls',
    page: 'Frameworks',
    icon: Shield,
    accent: 'from-violet-500 to-purple-600',
  },
  {
    label: 'Generate report',
    description: 'Branded PDF or CSV for any analyzed policy',
    page: 'Reports',
    icon: FileBarChart,
    accent: 'from-amber-500 to-orange-600',
  },
];

export default function Home() {
  const { user } = useAuth();

  const { data: policies = [], isLoading: policiesLoading } = useQuery({
    queryKey: ['policies'],
    queryFn: () => Policy.list('-created_at', 5),
  });

  const firstName = user?.first_name || (user?.email ? user.email.split('@')[0] : 'there');
  // Phase H: show a guided cold-start panel only after the policies query
  // settles — otherwise a brand-new tab flashes the panel for a beat before
  // the recent-policies card replaces it.
  const isEmptyAccount = !policiesLoading && policies.length === 0;

  return (
    <PageContainer>
      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-emerald-900 to-teal-900 p-8 lg:p-10 mb-8 shadow-sm">
        <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_top_right,_rgba(16,185,129,0.4),_transparent_60%)]" />
        <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full bg-white/10 backdrop-blur px-3 py-1 text-xs font-medium text-emerald-200 ring-1 ring-white/10">
              <ShieldCheck className="w-3.5 h-3.5" />
              Himaya · AI Compliance
            </div>
            <h1 className="mt-4 text-3xl lg:text-4xl font-bold text-white tracking-tight">
              Welcome back, {firstName}.
            </h1>
            <p className="mt-3 text-slate-300 text-sm lg:text-base max-w-xl">
              Himaya analyses your security policies against the Saudi cybersecurity
              landscape — NCA, SAMA, SDAIA/NDMO, CST and sector-specific frameworks — maps
              controls automatically and surfaces the gaps that matter, so you can act on
              compliance instead of chasing it.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to={createPageUrl('Policies')}>
                <Button className="bg-emerald-500 hover:bg-emerald-600 text-white shadow-md shadow-emerald-500/20">
                  <Upload className="w-4 h-4 mr-2" />
                  Upload a policy
                </Button>
              </Link>
              <Link to={createPageUrl('Dashboard')}>
                <Button variant="outline" className="bg-white/5 border-white/20 text-white hover:bg-white/10 hover:text-white">
                  View dashboard
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </Link>
            </div>
          </div>
          <div className="hidden lg:flex w-24 h-24 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-600 shadow-lg shadow-emerald-500/30">
            <ShieldCheck className="w-12 h-12 text-white" />
          </div>
        </div>
      </div>

      {/* Primary actions */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {primaryActions.map((item) => (
          <Link key={item.page} to={createPageUrl(item.page)} className="group">
            <Card className="h-full shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5">
              <CardContent className="p-5">
                <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${item.accent} flex items-center justify-center shadow-sm mb-4`}>
                  <item.icon className="w-5 h-5 text-white" />
                </div>
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-foreground">{item.label}</p>
                  <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                </div>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                  {item.description}
                </p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Phase H: Cold-start panel — shown only when the user has zero
          policies. Three numbered steps make the next action obvious for
          a fresh account. Auto-replaced by "Recent policies" below as
          soon as a policy exists. */}
      {isEmptyAccount && (
        <Card className="shadow-sm mb-8 overflow-hidden">
          <CardContent className="p-0">
            <div className="px-6 py-5 border-b border-border/60 flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 text-xs font-semibold uppercase tracking-wider">
                  <Sparkles className="w-3.5 h-3.5" />
                  Get started
                </div>
                <p className="mt-1.5 text-foreground font-semibold text-lg">
                  Three steps to your first compliance score
                </p>
                <p className="text-muted-foreground text-sm mt-0.5">
                  Himaya needs a policy document to analyse — once that's in,
                  the rest of the app populates automatically.
                </p>
              </div>
              <Link to={createPageUrl('Policies')} className="shrink-0">
                <Button className="bg-emerald-600 hover:bg-emerald-700 shadow-sm">
                  <Upload className="w-4 h-4 mr-2" />
                  Upload policy
                </Button>
              </Link>
            </div>
            <ol className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border">
              {[
                {
                  n: 1,
                  title: 'Upload a policy',
                  body: 'A PDF, DOCX, or TXT under 50 MB. Pick the framework you want to assess against.',
                },
                {
                  n: 2,
                  title: 'Run analysis',
                  body: 'Himaya extracts evidence, maps controls, and scores each framework deterministically.',
                },
                {
                  n: 3,
                  title: 'Review gaps',
                  body: 'Open the Gaps page to see severity-prioritised issues with cited page numbers.',
                },
              ].map((step) => (
                <li key={step.n} className="p-5 flex gap-3 items-start">
                  <div className="w-8 h-8 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 flex items-center justify-center text-sm font-semibold shrink-0">
                    {step.n}
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium text-foreground">{step.title}</p>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      {step.body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {/* Recent policies */}
      {policies.length > 0 && (
        <Card className="shadow-sm">
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="font-semibold text-foreground">Recent policies</p>
                <p className="text-xs text-muted-foreground">
                  Latest documents uploaded to Himaya
                </p>
              </div>
              <Link to={createPageUrl('Policies')}>
                <Button variant="ghost" size="sm" className="text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300">
                  View all
                  <ArrowRight className="w-4 h-4 ml-1" />
                </Button>
              </Link>
            </div>
            <ul className="divide-y divide-border">
              {policies.slice(0, 5).map((p) => (
                <li key={p.id} className="flex items-center gap-3 py-3">
                  <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center">
                    <FileText className="w-4 h-4 text-muted-foreground" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {p.file_name || 'Untitled'}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {(p.file_type || '').toUpperCase() || 'Document'} · {p.status || 'uploaded'}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </PageContainer>
  );
}
