import React, { useState, useEffect, useMemo } from "react";
import { api } from "@/api/apiClient";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Bell, FileBarChart, Search, LogOut, User, Settings, ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/AuthContext";

export default function Topbar({ onGenerateReport }) {
  const { user: ctxUser, logout: ctxLogout } = useAuth();
  const [user, setUser] = useState(ctxUser || null);

  const [notifications] = useState([
    { id: 1, title: "Analysis Complete", message: "Security Policy v2.1 analysis finished", time: "5m ago", unread: true },
    { id: 2, title: "New Gap Identified", message: "Critical gap found in NCA ECC compliance", time: "1h ago", unread: true },
    { id: 3, title: "Report Ready", message: "Q4 Compliance Report is ready to download", time: "2h ago", unread: false },
  ]);

  useEffect(() => {
    if (ctxUser) setUser(ctxUser);
  }, [ctxUser]);

  useEffect(() => {
    const loadUser = async () => {
      try {
        if (ctxUser) return;

        const stored = localStorage.getItem("user");
        if (stored) {
          setUser(JSON.parse(stored));
          return;
        }

        const userData = await api.auth.me();
        setUser(userData);
        localStorage.setItem("user", JSON.stringify(userData));
      } catch {
        // not logged in or request failed
      }
    };
    loadUser();
  }, [ctxUser]);

  const unreadCount = notifications.filter((n) => n.unread).length;

  const handleLogout = () => {
    if (typeof ctxLogout === "function") return ctxLogout();
    api.auth.logout("/login");
  };

  const displayName = useMemo(() => {
    if (!user) return "User";
    return (
      user.first_name ||
      user.full_name ||
      user.name ||
      user.email ||
      "User"
    );
  }, [user]);

  const displayRole = useMemo(() => {
    if (!user) return "Compliance Officer";
    return user.role || "Compliance Officer";
  }, [user]);

  const getInitials = (u) => {
    const name =
      u?.first_name ||
      u?.full_name ||
      u?.name ||
      u?.email ||
      "U";

    if (name.includes("@")) return name.slice(0, 2).toUpperCase();

    const parts = name.trim().split(/\s+/);
    const initials = parts.map((p) => p[0]).join("").toUpperCase();
    return initials.slice(0, 2) || "U";
  };

  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 sticky top-0 z-30">
      {/* Search */}
      <div className="flex items-center gap-4 flex-1 max-w-xl">
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search policies, frameworks, reports..."
            className="pl-10 bg-slate-50 border-slate-200 focus:bg-white"
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        {/* Generate Report Button */}
        <Button
          onClick={onGenerateReport}
          className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white shadow-md shadow-emerald-500/20"
        >
          <FileBarChart className="w-4 h-4 mr-2" />
          Generate Report
        </Button>

        {/* Notifications */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="relative">
              <Bell className="w-5 h-5 text-slate-600" />
              {unreadCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                  {unreadCount}
                </span>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80">
            <DropdownMenuLabel className="flex items-center justify-between">
              Notifications
              <Badge variant="secondary" className="text-xs">
                {unreadCount} new
              </Badge>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {notifications.map((notification) => (
              <DropdownMenuItem
                key={notification.id}
                className="flex flex-col items-start py-3 cursor-pointer"
              >
                <div className="flex items-center gap-2 w-full">
                  <span className={`font-medium text-sm ${notification.unread ? "text-slate-900" : "text-slate-600"}`}>
                    {notification.title}
                  </span>
                  {notification.unread && <span className="w-2 h-2 bg-emerald-500 rounded-full ml-auto" />}
                </div>
                <span className="text-xs text-slate-500 mt-0.5">{notification.message}</span>
                <span className="text-[10px] text-slate-400 mt-1">{notification.time}</span>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem className="justify-center text-emerald-600 font-medium">
              View all notifications
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* User Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="flex items-center gap-3 pl-2 pr-3">
              <Avatar className="h-8 w-8 bg-gradient-to-br from-emerald-400 to-teal-600">
                <AvatarFallback className="bg-transparent text-white text-xs font-medium">
                  {getInitials(user)}
                </AvatarFallback>
              </Avatar>

              <div className="flex flex-col items-start">
                <span className="text-sm font-medium text-slate-700">
                  {displayName}
                </span>
                <span className="text-[10px] text-slate-500 capitalize">
                  {displayRole}
                </span>
              </div>

              <ChevronDown className="w-4 h-4 text-slate-400" />
            </Button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>My Account</DropdownMenuLabel>
            <DropdownMenuSeparator />

            <DropdownMenuItem>
              <User className="w-4 h-4 mr-2" />
              Profile
            </DropdownMenuItem>

            <Link to={createPageUrl("Settings")}>
              <DropdownMenuItem>
                <Settings className="w-4 h-4 mr-2" />
                Settings
              </DropdownMenuItem>
            </Link>

            <DropdownMenuSeparator />

            <DropdownMenuItem onClick={handleLogout} className="text-red-600">
              <LogOut className="w-4 h-4 mr-2" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
