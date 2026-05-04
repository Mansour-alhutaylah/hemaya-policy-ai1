import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
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
  LockKeyhole,
  ChevronRight,
} from 'lucide-react';

const features = [
  {
    icon: Brain,
    title: 'AI policy understanding',
    description:
      'Ingest PDFs, DOCX or text. Himaya structures every clause and prepares it for control mapping — no manual tagging.',
    accent: 'from-emerald-500 to-teal-600',
  },
  {
    icon: GitCompare,
    title: 'Automatic control mapping',
    description:
      'Each clause is matched to NCA ECC, ISO 27001 and NIST 800-53 controls with traceable evidence and confidence scores.',
    accent: 'from-blue-500 to-indigo-600',
  },
  {
    icon: AlertTriangle,
    title: 'Gap & risk surfacing',
    description:
      'See unmet controls, partial coverage and high-risk areas instantly — prioritised so your team acts on what matters.',
    accent: 'from-amber-500 to-orange-600',
  },
  {
    icon: FileBarChart,
    title: 'Audit-ready reports',
    description:
      'Export branded PDF or CSV reports for executives and auditors — with full explainability behind every score.',
    accent: 'from-violet-500 to-purple-600',
  },
];

const workflow = [
  {
    step: '01',
    icon: Upload,
    title: 'Upload your policy',
    description:
      'Drop in a security policy in PDF, DOCX or plain text. Himaya parses it in seconds.',
  },
  {
    step: '02',
    icon: Sparkles,
    title: 'AI maps the controls',
    description:
      'Clauses are classified, mandatory evidence is boosted, and controls are mapped to your chosen frameworks.',
  },
  {
    step: '03',
    icon: LineChart,
    title: 'Review gaps & scores',
    description:
      'Coverage scores, gaps and risks appear on a live dashboard — drill into any clause for explainability.',
  },
  {
    step: '04',
    icon: FileBarChart,
    title: 'Export & share',
    description:
      'Generate a branded report for leadership or auditors, with full traceability for every decision.',
  },
];

const benefits = [
  'Cut compliance review time from weeks to minutes',
  'Map a single policy to multiple frameworks at once',
  'Every score is explainable — no black-box AI',
  'Built around NCA ECC, ISO 27001 and NIST 800-53',
];

function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-teal-600 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
        <ShieldCheck className="w-6 h-6 text-white" />
      </div>
      <div className="flex flex-col leading-none">
        <span className="font-bold text-lg tracking-tight text-slate-900">Himaya</span>
        <span className="text-[10px] text-slate-500 uppercase tracking-widest mt-0.5">
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
          ? 'bg-white/80 backdrop-blur border-b border-slate-200 shadow-sm'
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
            className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
          >
            Features
          </a>
          <a
            href="#how"
            className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
          >
            How it works
          </a>
          <a
            href="#frameworks"
            className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
          >
            Frameworks
          </a>
        </nav>

        <div className="flex items-center gap-2">
          <Link to="/login">
            <Button
              variant="ghost"
              className="text-slate-700 hover:text-slate-900 hover:bg-slate-100"
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

function Hero() {
  return (
    <section className="relative">
      {/* soft background gradient */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-emerald-50/60 via-white to-white" />
      <div className="absolute inset-x-0 top-0 -z-10 h-[600px] bg-[radial-gradient(ellipse_at_top,_rgba(16,185,129,0.18),_transparent_60%)]" />

      <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-16 lg:pt-24 pb-12 lg:pb-20">
        <div className="grid lg:grid-cols-12 gap-10 lg:gap-12 items-center">
          {/* Left: copy */}
          <div className="lg:col-span-7">
            <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 border border-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700">
              <ShieldCheck className="w-3.5 h-3.5" />
              Himaya · AI Compliance Platform
            </div>

            <h1 className="mt-5 text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-slate-900 leading-[1.05]">
              Compliance that runs
              <br />
              <span className="bg-gradient-to-r from-emerald-500 to-teal-600 bg-clip-text text-transparent">
                at the speed of AI.
              </span>
            </h1>

            <p className="mt-6 text-lg text-slate-600 leading-relaxed max-w-xl">
              Himaya analyses your security policies against NCA ECC, ISO 27001 and NIST 800-53,
              maps controls automatically and surfaces the gaps that matter — so your team can
              act on compliance instead of chasing it.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/signup">
                <Button
                  size="lg"
                  className="bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/25 h-11 px-6"
                >
                  Get started free
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </Link>
              <Link to="/login">
                <Button
                  size="lg"
                  variant="outline"
                  className="h-11 px-6 border-slate-300 text-slate-800 hover:bg-slate-50"
                >
                  Log in
                </Button>
              </Link>
            </div>

            <ul className="mt-8 grid sm:grid-cols-2 gap-y-2 gap-x-6 max-w-xl">
              {benefits.map((b) => (
                <li key={b} className="flex items-start gap-2 text-sm text-slate-600">
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Right: visual */}
          <div className="lg:col-span-5">
            <div className="relative">
              {/* glow */}
              <div className="absolute -inset-6 bg-gradient-to-br from-emerald-300/40 via-teal-300/30 to-transparent blur-2xl rounded-3xl -z-10" />

              {/* mock dashboard card */}
              <div className="relative rounded-2xl bg-gradient-to-br from-slate-900 via-emerald-950 to-teal-900 p-6 shadow-2xl shadow-emerald-900/20 ring-1 ring-white/10 overflow-hidden">
                <div className="absolute inset-0 opacity-30 bg-[radial-gradient(circle_at_top_right,_rgba(16,185,129,0.5),_transparent_60%)]" />

                <div className="relative flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center">
                      <ShieldCheck className="w-4 h-4 text-white" />
                    </div>
                    <span className="text-white text-sm font-semibold tracking-tight">
                      Compliance overview
                    </span>
                  </div>
                  <span className="text-[10px] uppercase tracking-widest text-emerald-300">
                    Live
                  </span>
                </div>

                <div className="relative mt-6 grid grid-cols-3 gap-3">
                  {[
                    { label: 'Score', value: '92%' },
                    { label: 'Controls', value: '418' },
                    { label: 'Gaps', value: '11' },
                  ].map((s) => (
                    <div
                      key={s.label}
                      className="rounded-xl bg-white/5 border border-white/10 backdrop-blur px-3 py-3"
                    >
                      <div className="text-[10px] uppercase tracking-widest text-emerald-200">
                        {s.label}
                      </div>
                      <div className="mt-1 text-xl font-bold text-white">{s.value}</div>
                    </div>
                  ))}
                </div>

                <div className="relative mt-5 space-y-2.5">
                  {[
                    { f: 'NCA ECC', v: 96 },
                    { f: 'ISO 27001', v: 89 },
                    { f: 'NIST 800-53', v: 91 },
                  ].map((row) => (
                    <div key={row.f}>
                      <div className="flex items-center justify-between text-[11px] text-slate-300">
                        <span className="font-medium">{row.f}</span>
                        <span className="text-emerald-300 font-semibold">{row.v}%</span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-emerald-400 to-teal-400 rounded-full"
                          style={{ width: `${row.v}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                <div className="relative mt-5 flex items-center justify-between rounded-xl bg-white/5 border border-white/10 px-3 py-2.5">
                  <div className="flex items-center gap-2 text-xs text-slate-200">
                    <Sparkles className="w-3.5 h-3.5 text-emerald-300" />
                    <span>3 new gaps detected in “Access Control Policy”</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-300" />
                </div>
              </div>

              {/* floating chip */}
              <div className="hidden sm:flex absolute -bottom-5 -left-5 items-center gap-2 rounded-xl bg-white shadow-lg shadow-slate-200 ring-1 ring-slate-200 px-3 py-2">
                <div className="w-7 h-7 rounded-lg bg-emerald-50 flex items-center justify-center">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                </div>
                <div className="leading-tight">
                  <div className="text-[11px] font-semibold text-slate-800">Audit-ready</div>
                  <div className="text-[10px] text-slate-500">Explainable scoring</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Frameworks() {
  const items = ['NCA ECC', 'ISO 27001', 'NIST 800-53'];
  return (
    <section id="frameworks" className="border-y border-slate-200 bg-white">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Built around the frameworks that matter
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {items.map((f) => (
              <span
                key={f}
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700"
              >
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
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
          <p className="text-xs font-semibold uppercase tracking-widest text-emerald-600">
            What Himaya does
          </p>
          <h2 className="mt-3 text-3xl lg:text-4xl font-bold tracking-tight text-slate-900">
            One platform from policy to audit-ready report.
          </h2>
          <p className="mt-4 text-slate-600 text-base lg:text-lg leading-relaxed">
            Himaya turns dense security policies into structured, mapped, scored compliance
            evidence — without the spreadsheets.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {features.map((f) => (
            <Card
              key={f.title}
              className="h-full border-slate-200 shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 hover:border-emerald-200"
            >
              <CardContent className="p-6">
                <div
                  className={`w-11 h-11 rounded-xl bg-gradient-to-br ${f.accent} flex items-center justify-center shadow-sm mb-4`}
                >
                  <f.icon className="w-5 h-5 text-white" />
                </div>
                <p className="font-semibold text-slate-900 tracking-tight">{f.title}</p>
                <p className="text-sm text-slate-500 mt-2 leading-relaxed">{f.description}</p>
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
    <section id="how" className="py-20 lg:py-24 bg-slate-50/70 border-y border-slate-200">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-emerald-600">
            How it works
          </p>
          <h2 className="mt-3 text-3xl lg:text-4xl font-bold tracking-tight text-slate-900">
            From upload to audit, in four steps.
          </h2>
          <p className="mt-4 text-slate-600 text-base lg:text-lg leading-relaxed">
            A simple workflow your compliance team can adopt on day one.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {workflow.map((w, idx) => (
            <div key={w.step} className="relative">
              <Card className="h-full border-slate-200 shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    <div className="w-11 h-11 rounded-xl bg-white border border-slate-200 flex items-center justify-center shadow-sm">
                      <w.icon className="w-5 h-5 text-emerald-600" />
                    </div>
                    <span className="text-xs font-bold tracking-widest text-slate-400">
                      {w.step}
                    </span>
                  </div>
                  <p className="mt-4 font-semibold text-slate-900 tracking-tight">{w.title}</p>
                  <p className="text-sm text-slate-500 mt-2 leading-relaxed">{w.description}</p>
                </CardContent>
              </Card>

              {/* connector arrow on large screens */}
              {idx < workflow.length - 1 && (
                <div className="hidden lg:flex absolute top-1/2 -right-2 -translate-y-1/2 w-4 h-4 items-center justify-center pointer-events-none">
                  <ChevronRight className="w-4 h-4 text-slate-300" />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCTA() {
  return (
    <section className="py-20 lg:py-24">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-emerald-900 to-teal-900 p-8 lg:p-12 shadow-xl">
          <div className="absolute inset-0 opacity-25 bg-[radial-gradient(circle_at_top_right,_rgba(16,185,129,0.45),_transparent_60%)]" />
          <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_bottom_left,_rgba(45,212,191,0.35),_transparent_60%)]" />

          <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-8">
            <div className="max-w-2xl">
              <div className="inline-flex items-center gap-2 rounded-full bg-white/10 backdrop-blur px-3 py-1 text-xs font-medium text-emerald-200 ring-1 ring-white/10">
                <LockKeyhole className="w-3.5 h-3.5" />
                Private by design
              </div>
              <h2 className="mt-4 text-3xl lg:text-4xl font-bold text-white tracking-tight">
                Ready to make compliance feel effortless?
              </h2>
              <p className="mt-3 text-slate-300 max-w-xl">
                Create a free account and analyse your first policy in minutes. No credit card,
                no setup overhead.
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
    <footer className="border-t border-slate-200 bg-white">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="flex items-center gap-3">
          <Logo />
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-slate-500">
          <a href="#features" className="hover:text-slate-900 transition-colors">
            Features
          </a>
          <a href="#how" className="hover:text-slate-900 transition-colors">
            How it works
          </a>
          <a href="#frameworks" className="hover:text-slate-900 transition-colors">
            Frameworks
          </a>
          <Link to="/login" className="hover:text-slate-900 transition-colors">
            Log in
          </Link>
          <Link to="/signup" className="hover:text-slate-900 transition-colors">
            Sign up
          </Link>
        </div>

        <p className="text-xs text-slate-400">
          © {new Date().getFullYear()} Himaya · AI Compliance
        </p>
      </div>
    </footer>
  );
}

export default function Landing() {
  // Force light mode while the public landing is mounted. ThemeContext persists
  // the user's last theme in localStorage; after logout that may still be "dark"
  // and would clash with this marketing page's intentionally light surfaces.
  useEffect(() => {
    const html = document.documentElement;
    const hadDark = html.classList.contains('dark');
    if (hadDark) html.classList.remove('dark');
    const previousTitle = document.title;
    document.title = 'Himaya · AI Compliance Platform';
    return () => {
      if (hadDark) html.classList.add('dark');
      document.title = previousTitle;
    };
  }, []);

  return (
    <div className="min-h-screen bg-white text-slate-900 antialiased">
      <PublicNav />
      <main>
        <Hero />
        <Frameworks />
        <Features />
        <HowItWorks />
        <FinalCTA />
      </main>
      <Footer />
    </div>
  );
}
