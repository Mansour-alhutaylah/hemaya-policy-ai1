import React from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

export default function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  actionLabel,
  secondaryAction,
  secondaryLabel,
  className
}) {
  return (
    <div className={cn(
      "flex flex-col items-center justify-center py-16 px-6 text-center",
      className
    )}>
      {Icon && (
        <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
          <Icon className="w-8 h-8 text-slate-400" />
        </div>
      )}
      <h3 className="text-lg font-semibold text-slate-900 mb-1">{title}</h3>
      <p className="text-sm text-slate-500 max-w-md mb-6">{description}</p>
      <div className="flex items-center gap-3">
        {action && actionLabel && (
          <Button onClick={action} className="bg-emerald-600 hover:bg-emerald-700">
            {actionLabel}
          </Button>
        )}
        {secondaryAction && secondaryLabel && (
          <Button onClick={secondaryAction} variant="outline">
            {secondaryLabel}
          </Button>
        )}
      </div>
    </div>
  );
}