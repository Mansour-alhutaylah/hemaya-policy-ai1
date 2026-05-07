import React from 'react';
import { cn } from '@/lib/utils';

export default function PageContainer({
  children,
  title,
  subtitle,
  actions = null,
  className = ''
}) {
  return (
    <div className={cn("p-6 lg:p-8", className)}>
      {(title || actions) && (
        // Page header — lighter weight, tighter line-height, and slightly
        // tighter rhythm (mb-6) for a premium SaaS feel. The title is
        // semibold rather than bold so it stops competing with section
        // headers inside cards.
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            {title && (
              <h1 className="text-2xl lg:text-[28px] font-semibold text-foreground tracking-tight leading-tight">
                {title}
              </h1>
            )}
            {subtitle && (
              <p className="text-muted-foreground mt-1.5 text-sm">
                {subtitle}
              </p>
            )}
          </div>
          {actions && (
            <div className="flex items-center gap-2.5 flex-shrink-0">
              {actions}
            </div>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
