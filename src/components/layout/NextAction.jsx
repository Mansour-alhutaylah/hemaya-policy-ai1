import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Sparkles, ArrowRight } from 'lucide-react';

/**
 * Phase UI-1: Next-action banner.
 *
 * Renders a compact "Recommended next step" card directly under a page's
 * PageContainer header. Pages compute their own state, then pass:
 *
 *   <NextAction
 *     primary={{ label, helper, to OR onClick, icon }}
 *     secondary={[{ label, to } ...]}     // optional, max ~2
 *     tone="info" | "success" | "warning"  // optional
 *   />
 *
 * The component is purely presentational — all state logic lives on the
 * page so the recommendation is computed from the same data the page
 * already has loaded.
 *
 * Render nothing when `primary` is falsy, so a page can drop the banner
 * silently while data is loading.
 */
export default function NextAction({ primary, secondary = [], tone = 'info' }) {
  if (!primary || !primary.label) return null;

  const toneClasses = {
    info: 'border-emerald-500/30 bg-emerald-500/5 dark:bg-emerald-500/8',
    success: 'border-emerald-500/30 bg-emerald-500/5 dark:bg-emerald-500/8',
    warning: 'border-amber-500/30 bg-amber-500/5 dark:bg-amber-500/8',
  }[tone] || '';

  const eyebrowToneClasses = {
    info: 'text-emerald-700 dark:text-emerald-400',
    success: 'text-emerald-700 dark:text-emerald-400',
    warning: 'text-amber-700 dark:text-amber-400',
  }[tone] || '';

  const PrimaryIcon = primary.icon;

  const primaryButton = (
    <Button
      onClick={primary.onClick}
      className="bg-emerald-600 hover:bg-emerald-700 shadow-sm"
    >
      {PrimaryIcon ? <PrimaryIcon className="w-4 h-4 mr-2" /> : null}
      {primary.label}
      {!PrimaryIcon ? <ArrowRight className="w-4 h-4 ml-2" /> : null}
    </Button>
  );

  return (
    <div
      className={`rounded-xl border ${toneClasses} px-5 py-4 mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4`}
    >
      <div className="min-w-0 flex-1">
        <div className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider ${eyebrowToneClasses}`}>
          <Sparkles className="w-3.5 h-3.5" />
          Recommended next step
        </div>
        <p className="mt-1 text-foreground font-semibold">
          {primary.label}
        </p>
        {primary.helper && (
          <p className="text-muted-foreground text-sm mt-0.5">
            {primary.helper}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 flex-wrap shrink-0">
        {secondary.map((s, i) =>
          s.to ? (
            <Link key={i} to={s.to}>
              <Button variant="ghost" className="text-muted-foreground hover:text-foreground">
                {s.label}
              </Button>
            </Link>
          ) : (
            <Button
              key={i}
              variant="ghost"
              onClick={s.onClick}
              className="text-muted-foreground hover:text-foreground"
            >
              {s.label}
            </Button>
          )
        )}
        {primary.to ? <Link to={primary.to}>{primaryButton}</Link> : primaryButton}
      </div>
    </div>
  );
}
