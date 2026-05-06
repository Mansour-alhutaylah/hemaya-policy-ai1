import React from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/ThemeContext";
import { cn } from "@/lib/utils";

/**
 * ThemeToggle — a single light/dark switcher wired to the global ThemeContext.
 *
 * Variants:
 *  - "fixed"  : floating pill in the top-right corner (used on public/auth pages
 *               that don't render the authenticated Topbar).
 *  - "inline" : flat icon button suitable for embedding in a header/topbar.
 *
 * The component reads/writes the same ThemeContext used everywhere else, so the
 * choice persists across refreshes via localStorage.
 */
export default function ThemeToggle({ variant = "fixed", className = "" }) {
  const { resolved, setTheme } = useTheme();
  const isDark = resolved === "dark";

  const toggle = () => setTheme(isDark ? "light" : "dark");
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";

  if (variant === "inline") {
    return (
      <button
        type="button"
        onClick={toggle}
        aria-label={label}
        title={label}
        className={cn(
          "inline-flex h-9 w-9 items-center justify-center rounded-md",
          "text-muted-foreground hover:text-foreground hover:bg-accent",
          "transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          className
        )}
      >
        {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={cn(
        "fixed top-4 right-4 z-50",
        "inline-flex h-10 w-10 items-center justify-center rounded-full",
        "border border-border bg-card/90 backdrop-blur",
        "text-muted-foreground hover:text-foreground hover:bg-accent",
        "shadow-sm transition-colors",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className
      )}
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}
