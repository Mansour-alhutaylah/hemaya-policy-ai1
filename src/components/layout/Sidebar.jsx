import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { createPageUrl } from '@/utils';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  FileText,
  BarChart3,
  Shield,
  GitCompare,
  AlertTriangle,
  FileBarChart,
  Lightbulb,
  Brain,
  History,
  FlaskConical,
  MessageSquare,
  Settings,
  ChevronLeft,
  ChevronRight,
  ShieldCheck
} from 'lucide-react';

const navigationItems = [
  { name: 'Dashboard', icon: LayoutDashboard, page: 'Dashboard' },
  { name: 'Policies', icon: FileText, page: 'Policies' },
  { name: 'Analyses', icon: BarChart3, page: 'Analyses' },
  { name: 'Frameworks', icon: Shield, page: 'Frameworks' },
  { name: 'Mapping Review', icon: GitCompare, page: 'MappingReview' },
  { name: 'Gaps & Risks', icon: AlertTriangle, page: 'GapsRisks' },
  { name: 'Reports', icon: FileBarChart, page: 'Reports' },
  { name: 'AI Insights', icon: Lightbulb, page: 'AIInsights', badge: 'NEW' },
  { name: 'Explainability', icon: Brain, page: 'Explainability' },
  { name: 'Audit Trail', icon: History, page: 'AuditTrail' },
  { name: 'Simulation', icon: FlaskConical, page: 'Simulation', badge: 'BETA' },
  { name: 'AI Assistant', icon: MessageSquare, page: 'AIAssistant' },
  { name: 'Settings', icon: Settings, page: 'Settings' },
];

export default function Sidebar({ collapsed, setCollapsed }) {
  const location = useLocation();
  const currentPath = location.pathname;

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 h-screen bg-slate-900 text-white transition-all duration-300 flex flex-col",
        collapsed ? "w-20" : "w-64"
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-700/50">
        <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-teal-600 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
          <ShieldCheck className="w-6 h-6 text-white" />
        </div>
        {!collapsed && (
          <div className="flex flex-col">
            <span className="font-bold text-lg tracking-tight">Hemaya</span>
            <span className="text-[10px] text-slate-400 uppercase tracking-widest">AI Compliance</span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-3">
        <ul className="space-y-1">
          {navigationItems.map((item) => {
            const isActive = currentPath === `/${item.page}` || 
              (item.page === 'Dashboard' && currentPath === '/');
            
            return (
              <li key={item.name}>
                <Link
                  to={createPageUrl(item.page)}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group relative",
                    isActive
                      ? "bg-gradient-to-r from-emerald-500/20 to-teal-500/10 text-emerald-400 border-l-2 border-emerald-400"
                      : "text-slate-400 hover:text-white hover:bg-slate-800/50"
                  )}
                >
                  <item.icon className={cn(
                    "w-5 h-5 flex-shrink-0 transition-colors",
                    isActive ? "text-emerald-400" : "text-slate-500 group-hover:text-emerald-400"
                  )} />
                  {!collapsed && (
                    <>
                      <span className="text-sm font-medium">{item.name}</span>
                      {item.badge && (
                        <span className={cn(
                          "ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded",
                          item.badge === 'NEW' 
                            ? "bg-emerald-500/20 text-emerald-400" 
                            : "bg-amber-500/20 text-amber-400"
                        )}>
                          {item.badge}
                        </span>
                      )}
                    </>
                  )}
                  {collapsed && item.badge && (
                    <span className={cn(
                      "absolute top-1 right-1 w-2 h-2 rounded-full",
                      item.badge === 'NEW' ? "bg-emerald-400" : "bg-amber-400"
                    )} />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Collapse Toggle */}
      <div className="p-3 border-t border-slate-700/50">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/50 transition-colors"
        >
          {collapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <>
              <ChevronLeft className="w-5 h-5" />
              <span className="text-sm">Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}