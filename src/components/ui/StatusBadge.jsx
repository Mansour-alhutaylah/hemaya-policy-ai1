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

const statusConfig = {
  // Policy statuses
  uploaded: { 
    label: 'Uploaded', 
    color: 'bg-blue-50 text-blue-700 border-blue-200', 
    icon: FileText 
  },
  processing: { 
    label: 'Processing', 
    color: 'bg-amber-50 text-amber-700 border-amber-200', 
    icon: Loader2,
    animate: true 
  },
  analyzed: { 
    label: 'Analyzed', 
    color: 'bg-emerald-50 text-emerald-700 border-emerald-200', 
    icon: CheckCircle2 
  },
  failed: { 
    label: 'Failed', 
    color: 'bg-red-50 text-red-700 border-red-200', 
    icon: XCircle 
  },
  archived: { 
    label: 'Archived', 
    color: 'bg-slate-50 text-slate-600 border-slate-200', 
    icon: Archive 
  },
  
  // Analysis statuses
  queued: { 
    label: 'Queued', 
    color: 'bg-slate-50 text-slate-600 border-slate-200', 
    icon: Clock 
  },
  running: { 
    label: 'Running', 
    color: 'bg-blue-50 text-blue-700 border-blue-200', 
    icon: Loader2,
    animate: true 
  },
  completed: { 
    label: 'Completed', 
    color: 'bg-emerald-50 text-emerald-700 border-emerald-200', 
    icon: CheckCircle2 
  },
  reported: { 
    label: 'Reported', 
    color: 'bg-purple-50 text-purple-700 border-purple-200', 
    icon: FileText 
  },
  
  // Compliance statuses
  'Compliant': { 
    label: 'Compliant', 
    color: 'bg-emerald-50 text-emerald-700 border-emerald-200', 
    icon: CheckCircle2 
  },
  'Partially Compliant': { 
    label: 'Partial', 
    color: 'bg-amber-50 text-amber-700 border-amber-200', 
    icon: AlertTriangle 
  },
  'Not Compliant': { 
    label: 'Non-Compliant', 
    color: 'bg-red-50 text-red-700 border-red-200', 
    icon: XCircle 
  },
  
  // Gap statuses
  'Open': { 
    label: 'Open', 
    color: 'bg-red-50 text-red-700 border-red-200', 
    icon: AlertTriangle 
  },
  'In Progress': { 
    label: 'In Progress', 
    color: 'bg-blue-50 text-blue-700 border-blue-200', 
    icon: Loader2 
  },
  'Resolved': { 
    label: 'Resolved', 
    color: 'bg-emerald-50 text-emerald-700 border-emerald-200', 
    icon: CheckCircle2 
  },
  'Deferred': { 
    label: 'Deferred', 
    color: 'bg-slate-50 text-slate-600 border-slate-200', 
    icon: Clock 
  },
  
  // Review statuses
  'Pending': { 
    label: 'Pending', 
    color: 'bg-amber-50 text-amber-700 border-amber-200', 
    icon: Clock 
  },
  'Accepted': { 
    label: 'Accepted', 
    color: 'bg-emerald-50 text-emerald-700 border-emerald-200', 
    icon: CheckCircle2 
  },
  'Rejected': { 
    label: 'Rejected', 
    color: 'bg-red-50 text-red-700 border-red-200', 
    icon: XCircle 
  },
  'Modified': { 
    label: 'Modified', 
    color: 'bg-purple-50 text-purple-700 border-purple-200', 
    icon: FileText 
  },
};

export default function StatusBadge({ status, size = 'default', showIcon = true }) {
  const config = statusConfig[status] || { 
    label: status, 
    color: 'bg-slate-50 text-slate-600 border-slate-200', 
    icon: null 
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