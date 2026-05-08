import React, { useMemo, useState, useRef, useEffect } from 'react';
import { Copy, Check, Plus, Minus, Equal } from 'lucide-react';
import { Button } from '@/components/ui/button';

// ── Diff algorithm ────────────────────────────────────────────────────────────
// Returns rows of { type: 'equal'|'add'|'remove', oldLine, newLine, oldNum, newNum }

const MAX_LINES = 500; // cap for O(m×n) LCS performance

function computeDiff(oldText, newText) {
  const oldLines = (oldText || '').split('\n').slice(0, MAX_LINES);
  const newLines = (newText || '').split('\n').slice(0, MAX_LINES);

  // Fast path: old is a prefix of new (additive-only case — no LCS needed)
  let prefix = 0;
  const minLen = Math.min(oldLines.length, newLines.length);
  while (prefix < minLen && oldLines[prefix] === newLines[prefix]) prefix++;

  if (prefix === oldLines.length) {
    const rows = oldLines.map((l, i) => ({
      type: 'equal', oldLine: l, newLine: newLines[i], oldNum: i + 1, newNum: i + 1,
    }));
    newLines.slice(prefix).forEach((l, i) => {
      rows.push({ type: 'add', oldLine: null, newLine: l, oldNum: null, newNum: prefix + i + 1 });
    });
    return rows;
  }

  // General LCS
  const A = oldLines, B = newLines;
  const m = A.length, n = B.length;
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = A[i - 1] === B[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const rows = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && A[i - 1] === B[j - 1]) {
      rows.unshift({ type: 'equal', oldLine: A[i - 1], newLine: B[j - 1] });
      i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      rows.unshift({ type: 'add', oldLine: null, newLine: B[j - 1] });
      j--;
    } else {
      rows.unshift({ type: 'remove', oldLine: A[i - 1], newLine: null });
      i--;
    }
  }

  let oNum = 0, nNum = 0;
  return rows.map(r => {
    if (r.type !== 'add')    oNum++;
    if (r.type !== 'remove') nNum++;
    return { ...r, oldNum: r.type !== 'add' ? oNum : null, newNum: r.type !== 'remove' ? nNum : null };
  });
}

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try { await navigator.clipboard.writeText(text); } catch { return; }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 px-2 py-0.5 rounded text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
    >
      {copied
        ? <><Check className="w-3 h-3 text-emerald-500" /><span className="text-emerald-500">Copied</span></>
        : <><Copy className="w-3 h-3" /><span>{label || 'Copy'}</span></>
      }
    </button>
  );
}

// ── Single diff row ───────────────────────────────────────────────────────────

const SIDE_STYLES = {
  equal:  { bg: '',                                                          num: 'text-muted-foreground/40', text: 'text-foreground/75',              marker: ' '  },
  add:    { bg: 'bg-emerald-500/[.08] dark:bg-emerald-500/[.12]',           num: 'text-emerald-600 dark:text-emerald-400', text: 'text-emerald-900 dark:text-emerald-200', marker: '+' },
  remove: { bg: 'bg-red-500/[.08] dark:bg-red-500/[.12]',                  num: 'text-red-600 dark:text-red-400',          text: 'text-red-900 dark:text-red-200',          marker: '−' },
};

function DiffCell({ row, side }) {
  const line = side === 'old' ? row.oldLine : row.newLine;
  const num  = side === 'old' ? row.oldNum  : row.newNum;
  const s    = SIDE_STYLES[row.type];

  if (line === null) {
    return <div className="h-[22px] bg-muted/10 border-b border-border/20" />;
  }
  return (
    <div className={`flex items-start gap-0 border-b border-border/20 ${s.bg}`} style={{ minHeight: 22 }}>
      <span className={`select-none w-10 shrink-0 text-right pr-2 text-[11px] font-mono leading-[22px] ${s.num}`}>
        {num ?? ''}
      </span>
      <span className={`select-none w-4 shrink-0 text-[11px] font-mono leading-[22px] ${s.num}`}>
        {s.marker}
      </span>
      <span className={`flex-1 text-[11px] font-mono leading-[22px] whitespace-pre-wrap break-all pr-2 ${s.text}`}>
        {line || ' '}
      </span>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function DiffViewer({
  oldText = '',
  newText = '',
  oldLabel = 'Original',
  newLabel = 'Modified',
  height = 480,
}) {
  const rows = useMemo(() => computeDiff(oldText, newText), [oldText, newText]);

  const addCount    = rows.filter(r => r.type === 'add').length;
  const removeCount = rows.filter(r => r.type === 'remove').length;

  // Sync-scroll: when user scrolls one pane the other follows
  const oldRef = useRef(null);
  const newRef = useRef(null);
  const syncing = useRef(false);

  const syncScroll = (src, dst) => (e) => {
    if (syncing.current) return;
    syncing.current = true;
    if (dst.current) dst.current.scrollTop = e.target.scrollTop;
    requestAnimationFrame(() => { syncing.current = false; });
  };

  return (
    <div className="flex flex-col border border-border rounded-xl overflow-hidden bg-card shadow-sm" style={{ height }}>
      {/* Stats bar */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-muted/30 border-b border-border shrink-0">
        <div className="flex items-center gap-4 text-xs">
          {addCount > 0 && (
            <span className="flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-400">
              <Plus className="w-3 h-3" />{addCount} added
            </span>
          )}
          {removeCount > 0 && (
            <span className="flex items-center gap-1 font-medium text-red-600 dark:text-red-400">
              <Minus className="w-3 h-3" />{removeCount} removed
            </span>
          )}
          {addCount === 0 && removeCount === 0 && (
            <span className="flex items-center gap-1 text-muted-foreground">
              <Equal className="w-3 h-3" />No changes detected
            </span>
          )}
        </div>
        <span className="text-[10px] text-muted-foreground/60">
          {rows.length} lines compared
        </span>
      </div>

      {/* Column headers */}
      <div className="flex shrink-0 border-b border-border bg-muted/20">
        <div className="flex-1 flex items-center justify-between px-3 py-1.5 border-r border-border">
          <span className="text-xs font-semibold text-muted-foreground truncate">{oldLabel}</span>
          <CopyButton text={oldText} label="Copy" />
        </div>
        <div className="flex-1 flex items-center justify-between px-3 py-1.5">
          <span className="text-xs font-semibold text-muted-foreground truncate">{newLabel}</span>
          <CopyButton text={newText} label="Copy" />
        </div>
      </div>

      {/* Side-by-side panes — sync-scrolled */}
      <div className="flex flex-1 min-h-0">
        <div
          ref={oldRef}
          onScroll={syncScroll(oldRef, newRef)}
          className="flex-1 overflow-y-auto border-r border-border"
        >
          {rows.map((row, idx) => <DiffCell key={idx} row={row} side="old" />)}
        </div>
        <div
          ref={newRef}
          onScroll={syncScroll(newRef, oldRef)}
          className="flex-1 overflow-y-auto"
        >
          {rows.map((row, idx) => <DiffCell key={idx} row={row} side="new" />)}
        </div>
      </div>
    </div>
  );
}
