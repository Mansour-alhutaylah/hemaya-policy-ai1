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
      <div className={cn("rounded-xl border border-slate-200 bg-white overflow-hidden", className)}>
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-50">
              {columns.map((col, i) => (
                <TableHead key={i} className="font-semibold text-slate-700">
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
      <div className={cn("rounded-xl border border-slate-200 bg-white overflow-hidden", className)}>
        {emptyState}
      </div>
    );
  }

  return (
    <div className={cn("rounded-xl border border-slate-200 bg-white overflow-hidden", className)}>
      <Table>
        <TableHeader>
          <TableRow className="bg-slate-50 hover:bg-slate-50">
            {columns.map((col, i) => (
              <TableHead 
                key={i} 
                className={cn(
                  "font-semibold text-slate-700 text-xs uppercase tracking-wide",
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
                "transition-colors",
                onRowClick && "cursor-pointer hover:bg-slate-50"
              )}
            >
              {columns.map((col, colIndex) => (
                <TableCell key={colIndex} className={cn("py-4", col.cellClassName)}>
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