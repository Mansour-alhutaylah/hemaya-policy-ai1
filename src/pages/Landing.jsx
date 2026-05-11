import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import ThemeToggle from '@/components/ThemeToggle';
import { useTheme } from '@/lib/ThemeContext';
import {
  ShieldCheck,
  ArrowRight,
  Upload,
  Brain,
  GitCompare,
  AlertTriangle,
  FileBarChart,
  Sparkles,
  CheckCircle2,
  LineChart,
  TrendingUp,
  FileText,
  ChevronRight,
  Mail,
} from 'lucide-react';

function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
}

const features = [
  {
    icon: Brain,
    title: 'Intelligent policy parsing',
    description:
      'Upload PDFs, DOCX, or text. Himaya structures every clause and prepares it for control mapping — no manual tagging required.',
    accent: 'from-emerald-500 to-teal-600',
  },
  {
    icon: GitCompare,
    title: 'Automated control mapping',
    description:
      'Each clause is matched to NCA ECC, ISO 27001, and NIST 800-53 controls with traceable evidence and confidence scores.',
    accent: 'from-blue-500 to-indigo-600',
  },
  {
    icon: AlertTriangle,
    title: 'Real-time gap detection',
    description:
      'Spot unmet controls, partial coverage, and high-risk areas the moment they appear — prioritized so your team focuses on what matters.',
    accent: 'from-amber-500 to-orange-600',
  },
  {
    icon: FileBarChart,
    title: 'Audit-ready reporting',
    description:
      'Export branded PDF or CSV reports for executives and auditors, with full explainability behind every score.',
    accent: 'from-violet-500 to-purple-600',
  },
];

const workflow = [
  {
    step: '01',
    icon: Upload,
    title: 'Upload your policy',
    description:
      'Drop in a security policy as PDF, DOCX, or plain text. Himaya parses it in seconds.',
  },
  {
    step: '02',
    icon: Sparkles,
    title: 'Map controls automatically',
    description:
      'Clauses are classified, mandatory evidence is highlighted, and controls are mapped to your selected framework.',
  },
  {
    step: '03',
    icon: LineChart,
    title: 'Review gaps and scores',
    description:
      'Coverage, gaps, and risk levels appear on a live dashboard — drill into any clause for full explainability.',
  },
  {
    step: '04',
    icon: FileBarChart,
    title: 'Export and share',
    description:
      'Generate a branded report for leadership or auditors, with complete traceability for every finding.',
  },
];

const benefits = [
  'Reduce compliance review time from weeks to minutes',
  'Map one policy to multiple frameworks simultaneously',
  'Every score is fully explainable — no black-box decisions',
  'Purpose-built for NCA ECC, ISO 27001, and NIST 800-53',
];

function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-teal-600 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
        <ShieldCheck className="w-6 h-6 text-white" />
      </div>
      <div className="flex flex-col leading-none">
        <span className="font-bold text-lg tracking-tight text-foreground">Himaya</span>
        <span className="text-[10px] text-muted-foreground uppercase tracking-widest mt-0.5">
          AI Compliance
        </span>
      </div>
    </div>
  );
}

function PublicNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-40 transition-all duration-300 ${
        scrolled
          ? 'bg-background/80 backdrop-blur border-b border-border shadow-sm'
          : 'bg-transparent border-b border-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link to="/" className="shrink-0">
          <Logo />
        </Link>

        <nav className="hidden md:flex items-center gap-8">
          <a
            href="#features"
            onClick={(e) => { e.preventDefault(); scrollTo('features'); }}
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Features
          </a>
          <a
            href="#how"
            onClick={(e) => { e.preventDefault(); scrollTo('how'); }}
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            How it works
          </a>
          <a
            href="#frameworks"
            onClick={(e) => { e.preventDefault(); scrollTo('frameworks'); }}
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Frameworks
          </a>
          <a
            href="#contact"
            onClick={(e) => { e.preventDefault(); scrollTo('contact'); }}
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Contact Us
          </a>
        </nav>

        <div className="flex items-center gap-2">
          {/* Inline toggle inside the navbar so it doesn't overlap the floating one */}
          <ThemeToggle variant="inline" className="mr-1" />
          <Link to="/login">
            <Button
              variant="ghost"
              className="text-foreground/80 hover:text-foreground hover:bg-accent"
            >
              Log in
            </Button>
          </Link>
          <Link to="/signup">
            <Button className="bg-emerald-500 hover:bg-emerald-600 text-white shadow-md shadow-emerald-500/20">
              Sign up
              <ArrowRight className="w-4 h-4 ml-1.5" />
            </Button>
          </Link>
        </div>
      </div>
    </header>
  );
}

// Mock dashboard preview that mirrors the real product Dashboard. Pulls colors
// from CSS variables so it adapts to dark mode along with the rest of the page.
function DashboardPreview() {
  const { resolved } = useTheme();
  const isDark = resolved === 'dark';

  const frameworks = [
    { label: 'NCA ECC', score: 96 },
    { label: 'ISO 27001', score: 89 },
    { label: 'NIST 800-53', score: 91 },
  ];

  const severity = [
    { label: 'Critical', value: 2, color: '#ef4444' },
    { label: 'High', value: 4, color: '#f59e0b' },
    { label: 'Medium', value: 3, color: '#3b82f6' },
    { label: 'Low', value: 2, color: '#10b981' },
  ];

  // Donut math
  const sevTotal = severity.reduce((s, x) => s + x.value, 0);
  const radius = 32;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const donutSegments = severity.map((s) => {
    const length = (s.value / sevTotal) * circumference;
    const seg = { ...s, length, offset };
    offset += length;
    return seg;
  });

  // Bar chart math
  const barChartW = 320;
  const barChartH = 132;
  const barPad = { top: 8, right: 6, bottom: 22, left: 6 };
  const innerW = barChartW - barPad.left - barPad.right;
  const innerH = barChartH - barPad.top - barPad.bottom;
  const barW = 32;
  const slot = innerW / frameworks.length;

  // Theme-aware swatches for the inline SVG mock
  const gridStroke = isDark ? '#334155' : '#e2e8f0';
  const labelMuted = isDark ? '#94a3b8' : '#64748b';
  const labelStrong = isDark ? '#f1f5f9' : '#0f172a';
  const donutTrack = isDark ? '#1e293b' : '#f1f5f9';

  return (
    <div className="relative">
      <div className="absolute -inset-6 bg-gradient-to-br from-emerald-300/40 via-teal-300/30 to-transparent blur-2xl rounded-3xl -z-10" />

      <div className="relative rounded-2xl bg-card ring-1 ring-border shadow-2xl shadow-black/10 overflow-hidden">
        {/* Faux topbar */}
        <div className="flex items-center justify-between h-10 px-4 border-b border-border bg-card">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-300" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-300" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-300" />
          </div>
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Executive Dashboard
          </span>
          <div className="flex items-center gap-1.5">
            <span className="w-5 h-5 rounded-md bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center">
              <ShieldCheck className="w-3 h-3 text-white" />
            </span>
          </div>
        </div>

        <div className="p-4 bg-muted/30">
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl border border-transparent bg-gradient-to-br from-emerald-500 to-teal-600 p-3 shadow-sm">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-white/80 font-medium">
                    Security Score
                  </p>
                  <p className="mt-1.5 text-2xl font-bold text-white tracking-tight leading-none">
                    92%
                  </p>
                  <p className="text-[10px] text-white/70 mt-1 inline-flex items-center gap-1">
                    <TrendingUp className="w-3 h-3" />
                    +5% vs last month
                  </p>
                </div>
                <div className="w-7 h-7 rounded-md bg-white/20 flex items-center justify-center">
                  <ShieldCheck className="w-3.5 h-3.5 text-white" />
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-border bg-card p-3 shadow-sm">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                    Controls Mapped
                  </p>
                  <p className="mt-1.5 text-2xl font-bold text-foreground tracking-tight leading-none">
                    418
                  </p>
                  <p className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1 inline-flex items-center gap-1">
                    <TrendingUp className="w-3 h-3" />
                    +12 this week
                  </p>
                </div>
                <div className="w-7 h-7 rounded-md bg-muted flex items-center justify-center">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-border bg-card p-3 shadow-sm">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                    Open Gaps
                  </p>
                  <p className="mt-1.5 text-2xl font-bold text-foreground tracking-tight leading-none">
                    11
                  </p>
                  <p className="text-[10px] text-rose-600 dark:text-rose-400 mt-1 inline-flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />2 critical
                  </p>
                </div>
                <div className="w-7 h-7 rounded-md bg-amber-50 dark:bg-amber-500/10 flex items-center justify-center">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                </div>
              </div>
            </div>
          </div>

          {/* Charts row */}
          <div className="mt-3 grid grid-cols-5 gap-3">
            <div className="col-span-3 rounded-xl border border-border bg-card p-3 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-foreground inline-flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                  Compliance by framework
                </p>
                <span className="text-[10px] text-muted-foreground">Last 30 days</span>
              </div>

              <svg
                viewBox={`0 0 ${barChartW} ${barChartH}`}
                width="100%"
                height={barChartH}
                className="mt-2"
              >
                {[0.25, 0.5, 0.75, 1].map((t) => (
                  <line
                    key={t}
                    x1={barPad.left}
                    x2={barChartW - barPad.right}
                    y1={barPad.top + innerH * (1 - t)}
                    y2={barPad.top + innerH * (1 - t)}
                    stroke={gridStroke}
                    strokeWidth="1"
                    strokeDasharray="3 3"
                  />
                ))}
                {frameworks.map((f, i) => {
                  const h = (f.score / 100) * innerH;
                  const x = barPad.left + i * slot + (slot - barW) / 2;
                  const y = barPad.top + (innerH - h);
                  return (
                    <g key={f.label}>
                      <defs>
                        <linearGradient id={`bar-${i}`} x1="0" x2="0" y1="0" y2="1">
                          <stop offset="0%" stopColor="#34d399" />
                          <stop offset="100%" stopColor="#10b981" />
                        </linearGradient>
                      </defs>
                      <rect
                        x={x}
                        y={y}
                        width={barW}
                        height={h}
                        rx="3"
                        fill={`url(#bar-${i})`}
                      />
                      <text
                        x={x + barW / 2}
                        y={y - 4}
                        textAnchor="middle"
                        fontSize="9"
                        fontWeight="600"
                        fill={labelStrong}
                      >
                        {f.score}%
                      </text>
                      <text
                        x={x + barW / 2}
                        y={barChartH - 6}
                        textAnchor="middle"
                        fontSize="9"
                        fill={labelMuted}
                      >
                        {f.label}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>

            <div className="col-span-2 rounded-xl border border-border bg-card p-3 shadow-sm">
              <p className="text-xs font-semibold text-foreground inline-flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                Gap severity
              </p>
              <div className="mt-2 flex items-center gap-3">
                <svg width="80" height="80" viewBox="0 0 80 80">
                  <g transform="translate(40 40) rotate(-90)">
                    <circle r={radius} cx="0" cy="0" fill="none" stroke={donutTrack} strokeWidth="9" />
                    {donutSegments.map((s) => (
                      <circle
                        key={s.label}
                        r={radius}
                        cx="0"
                        cy="0"
                        fill="none"
                        stroke={s.color}
                        strokeWidth="9"
                        strokeDasharray={`${s.length} ${circumference - s.length}`}
                        strokeDashoffset={-s.offset}
                        strokeLinecap="butt"
                      />
                    ))}
                  </g>
                  <text
                    x="40"
                    y="42"
                    textAnchor="middle"
                    fontSize="13"
                    fontWeight="700"
                    fill={labelStrong}
                  >
                    {sevTotal}
                  </text>
                </svg>
                <ul className="flex-1 space-y-1">
                  {severity.map((s) => (
                    <li key={s.label} className="flex items-center gap-2 text-[10px]">
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: s.color }}
                      />
                      <span className="text-muted-foreground flex-1">{s.label}</span>
                      <span className="font-semibold text-foreground">{s.value}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="mt-3 rounded-xl border border-border bg-card px-3 py-2.5 flex items-center gap-3 shadow-sm">
            <div className="w-7 h-7 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
              <FileText className="w-3.5 h-3.5 text-blue-500" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-semibold text-foreground truncate">
                Analysis Complete · Access Control Policy v2.1
              </p>
              <p className="text-[10px] text-muted-foreground truncate">
                89 mappings · 3 critical gaps detected
              </p>
            </div>
            <span className="text-[10px] text-muted-foreground flex-shrink-0">2m ago</span>
          </div>
        </div>
      </div>

      <div className="hidden sm:flex absolute -bottom-5 -left-5 items-center gap-2 rounded-xl bg-card shadow-lg shadow-black/10 ring-1 ring-border px-3 py-2">
        <div className="w-7 h-7 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
        </div>
        <div className="leading-tight">
          <div className="text-[11px] font-semibold text-foreground">Audit-ready</div>
          <div className="text-[10px] text-muted-foreground">Explainable scoring</div>
        </div>
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative">
      {/* soft background gradient — emerald glow tints work in both themes */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-emerald-50/60 via-background to-background dark:from-emerald-500/5" />
      <div className="absolute inset-x-0 top-0 -z-10 h-[600px] bg-[radial-gradient(ellipse_at_top,_rgba(16,185,129,0.18),_transparent_60%)]" />

      <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-16 lg:pt-24 pb-12 lg:pb-20">
        <div className="grid lg:grid-cols-12 gap-10 lg:gap-12 items-center">
          <div className="lg:col-span-7">
            <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-100 dark:border-emerald-500/20 px-3 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-300">
              <ShieldCheck className="w-3.5 h-3.5" />
              Himaya · AI Compliance Platform
            </div>

            <h1 className="mt-5 text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-foreground leading-[1.05]">
              Compliance that runs
              <br />
              <span className="bg-gradient-to-r from-emerald-500 to-teal-600 bg-clip-text text-transparent">
                at the speed of AI.
              </span>
            </h1>

            <p className="mt-6 text-lg text-muted-foreground leading-relaxed max-w-xl">
              Himaya transforms dense security documentation into structured, mapped, and
              scored compliance evidence. Analyze policies against NCA ECC, ISO 27001, and
              NIST 800-53 in minutes — not months — with full traceability behind every
              decision.
            </p>

            <ul className="mt-8 grid sm:grid-cols-2 gap-y-2 gap-x-6 max-w-xl">
              {benefits.map((b) => (
                <li key={b} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="lg:col-span-5">
            <DashboardPreview />
          </div>
        </div>
      </div>
    </section>
  );
}

function Frameworks() {
  const items = ['NCA ECC', 'ISO 27001', 'NIST 800-53'];
  return (
    <section id="frameworks" className="border-y border-border bg-card">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Aligned with the standards that matter most
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {items.map((f) => (
              <span
                key={f}
                className="inline-flex items-center gap-2 rounded-full border border-border bg-muted/50 px-3 py-1 text-xs font-medium text-foreground"
              >
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                {f}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function Features() {
  return (
    <section id="features" className="py-20 lg:py-24">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
            Capabilities
          </p>
          <h2 className="mt-3 text-3xl lg:text-4xl font-bold tracking-tight text-foreground">
            From raw policy to audit-ready evidence.
          </h2>
          <p className="mt-4 text-muted-foreground text-base lg:text-lg leading-relaxed">
            Replace fragmented spreadsheets and manual review cycles with a single
            intelligent compliance workspace.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {features.map((f) => (
            <Card
              key={f.title}
              className="h-full border-border shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 hover:border-emerald-200 dark:hover:border-emerald-500/30"
            >
              <CardContent className="p-6">
                <div
                  className={`w-11 h-11 rounded-xl bg-gradient-to-br ${f.accent} flex items-center justify-center shadow-sm mb-4`}
                >
                  <f.icon className="w-5 h-5 text-white" />
                </div>
                <p className="font-semibold text-foreground tracking-tight">{f.title}</p>
                <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                  {f.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section id="how" className="py-20 lg:py-24 bg-muted/30 border-y border-border">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
            How it works
          </p>
          <h2 className="mt-3 text-3xl lg:text-4xl font-bold tracking-tight text-foreground">
            From upload to audit in four steps.
          </h2>
          <p className="mt-4 text-muted-foreground text-base lg:text-lg leading-relaxed">
            A streamlined workflow your compliance team can adopt from day one.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {workflow.map((w, idx) => (
            <div key={w.step} className="relative">
              <Card className="h-full border-border shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    <div className="w-11 h-11 rounded-xl bg-card border border-border flex items-center justify-center shadow-sm">
                      <w.icon className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                    </div>
                    <span className="text-xs font-bold tracking-widest text-muted-foreground">
                      {w.step}
                    </span>
                  </div>
                  <p className="mt-4 font-semibold text-foreground tracking-tight">{w.title}</p>
                  <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{w.description}</p>
                </CardContent>
              </Card>

              {idx < workflow.length - 1 && (
                <div className="hidden lg:flex absolute top-1/2 -right-2 -translate-y-1/2 w-4 h-4 items-center justify-center pointer-events-none">
                  <ChevronRight className="w-4 h-4 text-muted-foreground/60" />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ContactUs() {
  return (
    <section id="contact" className="py-20 lg:py-24 bg-muted/30 border-y border-border">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl mx-auto text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
            Get in touch
          </p>
          <h2 className="mt-3 text-3xl lg:text-4xl font-bold tracking-tight text-foreground">
            Contact Us
          </h2>
          <p className="mt-4 text-muted-foreground text-base lg:text-lg leading-relaxed">
            For inquiries, partnerships, or support regarding Himaya AI Compliance Platform.
          </p>
        </div>

        <div className="mt-10 flex justify-center">
          <a
            href="mailto:info@ai-himaya.site"
            className="group flex items-center gap-4 rounded-2xl border border-border bg-card px-8 py-6 shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 hover:border-emerald-200 dark:hover:border-emerald-500/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          >
            <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-sm shadow-emerald-500/20 flex-shrink-0">
              <Mail className="w-5 h-5 text-white" />
            </div>
            <div className="text-left">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Email
              </p>
              <p className="mt-0.5 font-semibold text-foreground group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                info@ai-himaya.site
              </p>
            </div>
          </a>
        </div>
      </div>
    </section>
  );
}

function FinalCTA() {
  return (
    <section className="py-20 lg:py-24">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        {/* Intentionally dark in both themes — this is a marketing CTA panel */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-emerald-900 to-teal-900 p-8 lg:p-12 shadow-xl">
          <div className="absolute inset-0 opacity-25 bg-[radial-gradient(circle_at_top_right,_rgba(16,185,129,0.45),_transparent_60%)]" />
          <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_bottom_left,_rgba(45,212,191,0.35),_transparent_60%)]" />

          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-8">
            <div className="max-w-2xl">
              <h2 className="text-3xl lg:text-4xl font-bold text-white tracking-tight">
                Ready to make compliance effortless?
              </h2>
              <p className="mt-3 text-slate-300 max-w-xl">
                Start your free account and analyze your first policy in minutes — no credit
                card, no setup required.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Link to="/signup">
                <Button
                  size="lg"
                  className="bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/25 h-11 px-6"
                >
                  Create your account
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </Link>
              <Link to="/login">
                <Button
                  size="lg"
                  variant="outline"
                  className="h-11 px-6 bg-white/5 border-white/20 text-white hover:bg-white/10 hover:text-white"
                >
                  Log in
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-border bg-card">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <Logo />
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-6">
          <a
            href="mailto:info@ai-himaya.site"
            className="text-xs text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-1.5"
          >
            <Mail className="w-3 h-3" />
            info@ai-himaya.site
          </a>
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} Himaya · AI Compliance
          </p>
        </div>
      </div>
    </footer>
  );
}

export default function Landing() {
  // Surface a one-time notice when the user lands here because of inactivity logout.
  const [inactivityNotice, setInactivityNotice] = useState(false);
  useEffect(() => {
    try {
      if (sessionStorage.getItem('logout_reason') === 'inactivity') {
        sessionStorage.removeItem('logout_reason');
        setInactivityNotice(true);
      }
    } catch {
      // storage may be unavailable
    }
  }, []);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = 'Himaya · AI Compliance Platform';
    return () => {
      document.title = previousTitle;
    };
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground antialiased">
      <PublicNav />
      {inactivityNotice && (
        <div className="bg-amber-50 dark:bg-amber-500/10 border-b border-amber-200 dark:border-amber-500/30 text-amber-800 dark:text-amber-200">
          <div className="max-w-7xl mx-auto px-6 lg:px-8 py-2 flex items-center justify-between gap-4 text-xs">
            <span>You were signed out after 15 minutes of inactivity.</span>
            <button
              onClick={() => setInactivityNotice(false)}
              className="text-amber-700 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-100 font-medium"
              aria-label="Dismiss notice"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
      <main>
        <Hero />
        <Frameworks />
        <Features />
        <HowItWorks />
        <ContactUs />
        <FinalCTA />
      </main>
      <Footer />
    </div>
  );
}
