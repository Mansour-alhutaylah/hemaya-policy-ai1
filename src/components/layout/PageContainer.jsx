import React from 'react';
import { cn } from '@/lib/utils';

export default function PageContainer({ 
  children, 
  title, 
  subtitle,
  actions,
  className 
}) {
  return (
    <div className={cn("p-6 lg:p-8", className)}>
      {(title || actions) && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            {title && (
              <h1 className="text-2xl lg:text-3xl font-bold text-slate-900 tracking-tight">
                {title}
              </h1>
            )}
            {subtitle && (
              <p className="text-slate-500 mt-1 text-sm lg:text-base">
                {subtitle}
              </p>
            )}
          </div>
          {actions && (
            <div className="flex items-center gap-3 flex-shrink-0">
              {actions}
            </div>
          )}
        </div>
      )}
      {children}
    </div>
  );
}