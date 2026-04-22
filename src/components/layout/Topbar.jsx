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
import { LogOut, Settings, ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import { useAuth } from "@/lib/AuthContext";

export default function Topbar() {
  const { user: ctxUser, logout: ctxLogout } = useAuth();
  const [user, setUser] = useState(ctxUser || null);

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
    <header className="h-16 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center justify-end px-6 sticky top-0 z-30">
      {/* Actions */}
      <div className="flex items-center gap-3">
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
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                  {displayName}
                </span>
                <span className="text-[10px] text-slate-500 dark:text-slate-400 capitalize">
                  {displayRole}
                </span>
              </div>

              <ChevronDown className="w-4 h-4 text-slate-400" />
            </Button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>My Account</DropdownMenuLabel>
            <DropdownMenuSeparator />

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
