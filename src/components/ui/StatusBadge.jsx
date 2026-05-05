import React from 'react';
import { cn } from '@/lib/utils';
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  FileText,
  Archive,
  AlertTriangle
} from 'lucide-react';

// Tinted, semantic colors that look good in both light & dark modes.
const TINTS = {
  blue:
    'bg-blue-50 text-blue-700 border-blue-200 ' +
    'dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-500/30',
  amber:
    'bg-amber-50 text-amber-700 border-amber-200 ' +
    'dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30',
  emerald:
    'bg-emerald-50 text-emerald-700 border-emerald-200 ' +
    'dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30',
  red:
    'bg-red-50 text-red-700 border-red-200 ' +
    'dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30',
  slate:
    'bg-slate-50 text-slate-600 border-slate-200 ' +
    'dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-500/30',
  purple:
    'bg-purple-50 text-purple-700 border-purple-200 ' +
    'dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30',
};

const statusConfig = {
  // Policy statuses
  uploaded:        { label: 'Uploaded',     color: TINTS.blue,    icon: FileText },
  processing:      { label: 'Processing',   color: TINTS.amber,   icon: Loader2, animate: true },
  analyzed:        { label: 'Analyzed',     color: TINTS.emerald, icon: CheckCircle2 },
  failed:          { label: 'Failed',       color: TINTS.red,     icon: XCircle },
  archived:        { label: 'Archived',     color: TINTS.slate,   icon: Archive },

  // Analysis statuses
  queued:          { label: 'Queued',       color: TINTS.slate,   icon: Clock },
  running:         { label: 'Running',      color: TINTS.blue,    icon: Loader2, animate: true },
  completed:       { label: 'Completed',    color: TINTS.emerald, icon: CheckCircle2 },
  reported:        { label: 'Reported',     color: TINTS.purple,  icon: FileText },

  // Compliance statuses
  'Compliant':            { label: 'Compliant',     color: TINTS.emerald, icon: CheckCircle2 },
  'Partially Compliant':  { label: 'Partial',       color: TINTS.amber,   icon: AlertTriangle },
  'Not Compliant':        { label: 'Non-Compliant', color: TINTS.red,     icon: XCircle },

  // Gap statuses
  'Open':         { label: 'Open',        color: TINTS.red,     icon: AlertTriangle },
  'In Progress':  { label: 'In Progress', color: TINTS.blue,    icon: Loader2 },
  'Resolved':     { label: 'Resolved',    color: TINTS.emerald, icon: CheckCircle2 },
  'Deferred':     { label: 'Deferred',    color: TINTS.slate,   icon: Clock },

  // Review statuses
  'Pending':      { label: 'Pending',     color: TINTS.amber,   icon: Clock },
  'Accepted':     { label: 'Accepted',    color: TINTS.emerald, icon: CheckCircle2 },
  'Rejected':     { label: 'Rejected',    color: TINTS.red,     icon: XCircle },
  'Modified':     { label: 'Modified',    color: TINTS.purple,  icon: FileText },
};

export default function StatusBadge({ status, size = 'default', showIcon = true }) {
  const config = statusConfig[status] || {
    label: status,
    color: TINTS.slate,
    icon: null,
  };

  const Icon = config.icon;

  const sizes = {
    sm: 'text-[10px] px-1.5 py-0.5',
    default: 'text-xs px-2 py-1',
    lg: 'text-sm px-2.5 py-1.5',
  };

  return (
    <span className={cn(
      "inline-flex items-center gap-1 font-medium rounded-full border",
      config.color,
      sizes[size]
    )}>
      {showIcon && Icon && (
        <Icon className={cn(
          size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5',
          config.animate && 'animate-spin'
        )} />
      )}
      {config.label}
    </span>
  );
}
