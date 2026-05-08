import React from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export default function DataTable({
  columns,
  data,
  isLoading,
  onRowClick,
  emptyState,
  className
}) {
  if (isLoading) {
    return (
      <div className={cn("rounded-xl border border-border bg-card overflow-hidden", className)}>
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              {columns.map((col, i) => (
                <TableHead key={i} className="font-semibold text-foreground">
                  {col.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...Array(5)].map((_, rowIndex) => (
              <TableRow key={rowIndex}>
                {columns.map((_, colIndex) => (
                  <TableCell key={colIndex}>
                    <Skeleton className="h-4 w-full max-w-[200px]" />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className={cn("rounded-xl border border-border bg-card overflow-hidden", className)}>
        {emptyState}
      </div>
    );
  }

  return (
    // Card-style container with clean rounded corners + subtle shadow. The
    // shadow lifts the table off the soft page background just enough to
    // read as a distinct surface (matches the reference look).
    <div className={cn("rounded-xl border border-border bg-card shadow-sm overflow-hidden", className)}>
      <Table>
        <TableHeader>
          {/* Header row — slightly tinted muted band with uppercase tracked
              caps for a modern SaaS data-table feel. */}
          <TableRow className="bg-muted/40 hover:bg-muted/40 border-b border-border">
            {columns.map((col, i) => (
              <TableHead
                key={i}
                className={cn(
                  "h-11 font-semibold text-muted-foreground text-[11px] uppercase tracking-wider",
                  col.className
                )}
              >
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row, rowIndex) => (
            <TableRow
              key={row.id || rowIndex}
              onClick={() => onRowClick?.(row)}
              className={cn(
                "transition-colors border-b border-border/60 last:border-0",
                onRowClick && "cursor-pointer hover:bg-muted/40"
              )}
            >
              {columns.map((col, colIndex) => (
                <TableCell
                  key={colIndex}
                  className={cn("py-3.5 text-sm", col.cellClassName)}
                >
                  {col.cell ? col.cell(row) : row[col.accessor]}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
