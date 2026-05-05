import React from 'react';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

export default function StatsCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  trendValue,
  variant = 'default',
  className
}) {
  const variants = {
    default: 'bg-card border-border text-card-foreground',
    emerald: 'bg-gradient-to-br from-emerald-500 to-teal-600 text-white border-transparent',
    blue: 'bg-gradient-to-br from-blue-500 to-indigo-600 text-white border-transparent',
    amber: 'bg-gradient-to-br from-amber-500 to-orange-600 text-white border-transparent',
    red: 'bg-gradient-to-br from-red-500 to-rose-600 text-white border-transparent',
  };

  const isColored = variant !== 'default';

  return (
    <div
      className={cn(
        "rounded-xl border p-5 shadow-sm transition-all duration-200 hover:shadow-md",
        variants[variant],
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className={cn(
            "text-sm font-medium",
            isColored ? "text-white/80" : "text-muted-foreground"
          )}>
            {title}
          </p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className={cn(
              "text-3xl font-bold tracking-tight",
              isColored ? "text-white" : "text-foreground"
            )}>
              {value}
            </span>
            {trend && (
              <span className={cn(
                "flex items-center text-xs font-medium",
                isColored ? "text-white/80" : (
                  trend === 'up' ? "text-emerald-600 dark:text-emerald-400" :
                  trend === 'down' ? "text-red-600 dark:text-red-400" :
                  "text-muted-foreground"
                )
              )}>
                {trend === 'up' && <TrendingUp className="w-3 h-3 mr-0.5" />}
                {trend === 'down' && <TrendingDown className="w-3 h-3 mr-0.5" />}
                {trend === 'neutral' && <Minus className="w-3 h-3 mr-0.5" />}
                {trendValue}
              </span>
            )}
          </div>
          {subtitle && (
            <p className={cn(
              "text-xs mt-1",
              isColored ? "text-white/70" : "text-muted-foreground"
            )}>
              {subtitle}
            </p>
          )}
        </div>
        {Icon && (
          <div className={cn(
            "w-10 h-10 rounded-lg flex items-center justify-center",
            isColored ? "bg-white/20" : "bg-muted"
          )}>
            <Icon className={cn(
              "w-5 h-5",
              isColored ? "text-white" : "text-muted-foreground"
            )} />
          </div>
        )}
      </div>
    </div>
  );
}
