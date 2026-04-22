import React, { useState } from 'react';
import Sidebar from '@/components/layout/Sidebar';
import Topbar from '@/components/layout/Topbar';
import { cn } from '@/lib/utils';
import { Toaster } from '@/components/ui/toaster';

export default function Layout({ children }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      <style>{`
        :root {
          --color-primary: #10b981;
          --color-primary-dark: #059669;
          --color-secondary: #0d9488;
          --color-background: #f8fafc;
          --color-surface: #ffffff;
          --color-text-primary: #0f172a;
          --color-text-secondary: #64748b;
          --color-border: #e2e8f0;
        }

        * {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }

        .scrollbar-thin::-webkit-scrollbar {
          width: 6px;
        }

        .scrollbar-thin::-webkit-scrollbar-track {
          background: transparent;
        }

        .scrollbar-thin::-webkit-scrollbar-thumb {
          background: #cbd5e1;
          border-radius: 3px;
        }

        .scrollbar-thin::-webkit-scrollbar-thumb:hover {
          background: #94a3b8;
        }
      `}</style>

      <Sidebar collapsed={sidebarCollapsed} setCollapsed={setSidebarCollapsed} />

      <div className={cn(
        "transition-all duration-300",
        sidebarCollapsed ? "ml-20" : "ml-64"
      )}>
        <Topbar />
        <main className="min-h-[calc(100vh-4rem)]">
          {children}
        </main>
      </div>

      <Toaster />
    </div>
  );
}
