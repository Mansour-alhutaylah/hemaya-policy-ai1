// Phase D: shared severity / status colour tokens.
// Replaces inline `const SEVERITY_COLORS = {...}` literals scattered across
// pages so charts and badges always use the same palette.
//
// If you add a new severity or status, add it here and only here.

export const SEVERITY_COLORS = {
  Critical: '#EF4444', // red-500
  High:     '#F97316', // orange-500
  Medium:   '#EAB308', // yellow-500
  Low:      '#22C55E', // green-500
};

export const STATUS_COLORS = {
  // Compliance-result statuses
  compliant:     '#22C55E', // green-500
  partial:       '#EAB308', // yellow-500
  non_compliant: '#EF4444', // red-500

  // UI-friendly aliases
  Covered: '#22C55E',
  Partial: '#EAB308',
  Missing: '#EF4444',
};

export function getSeverityColor(level, fallback = '#6B7280') {
  if (!level) return fallback;
  // Tolerate both "High" and "high"
  const key = level.charAt(0).toUpperCase() + level.slice(1).toLowerCase();
  return SEVERITY_COLORS[key] || fallback;
}

export function getStatusColor(status, fallback = '#6B7280') {
  if (!status) return fallback;
  return STATUS_COLORS[status] || STATUS_COLORS[status.toLowerCase?.()] || fallback;
}
