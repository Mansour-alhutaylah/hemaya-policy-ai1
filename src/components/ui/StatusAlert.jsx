import React from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

const VARIANTS = {
  success: {
    wrapper:
      "border-emerald-200 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10",
    iconClass: "text-emerald-500 dark:text-emerald-400",
    textClass: "text-emerald-700 dark:text-emerald-300",
    Icon: CheckCircle2,
  },
  error: {
    wrapper:
      "border-red-200 bg-red-50 dark:border-red-500/30 dark:bg-red-500/10",
    iconClass: "text-red-500 dark:text-red-400",
    textClass: "text-red-700 dark:text-red-300",
    Icon: XCircle,
  },
  warning: {
    wrapper:
      "border-amber-200 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10",
    iconClass: "text-amber-500 dark:text-amber-400",
    textClass: "text-amber-800 dark:text-amber-200",
    Icon: AlertTriangle,
  },
  info: {
    wrapper:
      "border-blue-200 bg-blue-50 dark:border-blue-500/30 dark:bg-blue-500/10",
    iconClass: "text-blue-400 dark:text-blue-300",
    textClass: "text-blue-700 dark:text-blue-300",
    Icon: Info,
  },
};

/**
 * StatusAlert — drop-in alert banner with icon.
 *
 * Props:
 *   type     "success" | "error" | "warning" | "info"  (default: "info")
 *   message  string — renders nothing when falsy
 *   className  extra Tailwind classes (e.g. "mt-4")
 */
export default function StatusAlert({ type = "info", message, className = "" }) {
  if (!message) return null;

  const v = VARIANTS[type] ?? VARIANTS.info;
  const { Icon } = v;

  return (
    <div
      role="alert"
      className={`flex items-start gap-2.5 rounded-xl border p-3 text-sm ${v.wrapper} ${className}`}
    >
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${v.iconClass}`} aria-hidden="true" />
      <span className={v.textClass}>{message}</span>
    </div>
  );
}
