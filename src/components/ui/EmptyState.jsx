import React from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

/**
 * Phase UI-2: EmptyState gains an `urgency` prop so the visual weight
 * matches the situation:
 *   - 'info'     (default): neutral muted icon, no tint
 *   - 'success': emerald-tinted ("all clear, no gaps")
 *   - 'warning': amber-tinted ("you should do something here")
 * The icon container picks up the matching tint; the surrounding
 * background stays neutral so the empty state never overwhelms the
 * page.
 */
const URGENCY_CLASSES = {
  info: {
    iconBg: 'bg-muted',
    iconColor: 'text-muted-foreground',
  },
  success: {
    iconBg: 'bg-emerald-500/15',
    iconColor: 'text-emerald-600 dark:text-emerald-400',
  },
  warning: {
    iconBg: 'bg-amber-500/15',
    iconColor: 'text-amber-600 dark:text-amber-400',
  },
};

export default function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  actionLabel,
  secondaryAction,
  secondaryLabel,
  urgency = 'info',
  className,
}) {
  const u = URGENCY_CLASSES[urgency] || URGENCY_CLASSES.info;
  return (
    <div className={cn(
      "flex flex-col items-center justify-center py-16 px-6 text-center",
      className
    )}>
      {Icon && (
        <div className={cn(
          "w-16 h-16 rounded-2xl flex items-center justify-center mb-4",
          u.iconBg
        )}>
          <Icon className={cn("w-8 h-8", u.iconColor)} />
        </div>
      )}
      <h3 className="text-lg font-semibold text-foreground mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-md mb-6">{description}</p>
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
