// Phase D-5: null/invalid-safe date formatters.
//
// Many pages render `format(new Date(row.x), 'MMM d, yyyy')` directly,
// which crashes (or renders "Invalid Date") when `row.x` is null/undefined
// or an unparseable string. These wrappers absorb that case and return a
// neutral fallback ("—" by default).
//
// Usage:
//   import { formatDate, formatDateTime } from '@/lib/format';
//   formatDate(row.created_at)                     // "Apr 5, 2026"
//   formatDate(row.created_at, 'yyyy-MM-dd', 'n/a')// "2026-04-05" or "n/a"
//   formatDateTime(row.analyzed_at)                // "Apr 5, 2026 14:23"

import { format as dfFormat } from 'date-fns';

const DEFAULT_DATE_PATTERN = 'MMM d, yyyy';
const DEFAULT_DATETIME_PATTERN = 'MMM d, yyyy HH:mm';
const DEFAULT_FALLBACK = '—';

function _format(value, pattern, fallback) {
  if (value === null || value === undefined || value === '') return fallback;
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return fallback;
  try {
    return dfFormat(d, pattern);
  } catch {
    return fallback;
  }
}

export function formatDate(value, pattern = DEFAULT_DATE_PATTERN, fallback = DEFAULT_FALLBACK) {
  return _format(value, pattern, fallback);
}

export function formatDateTime(value, fallback = DEFAULT_FALLBACK) {
  return _format(value, DEFAULT_DATETIME_PATTERN, fallback);
}
