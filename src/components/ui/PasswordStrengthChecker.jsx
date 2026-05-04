import React from "react";

const RULES = [
  { label: "At least 8 characters",                   test: (v) => v.length >= 8 },
  { label: "One uppercase letter (A–Z)",               test: (v) => /[A-Z]/.test(v) },
  { label: "One lowercase letter (a–z)",               test: (v) => /[a-z]/.test(v) },
  { label: "One number (0–9)",                         test: (v) => /\d/.test(v) },
  { label: "One special character (@#$%^&*!?_-+=<>)",  test: (v) => /[@#$%^&*!?_\-+=<>]/.test(v) },
];

export default function PasswordStrengthChecker({ password }) {
  if (!password) return null;

  return (
    <ul className="mt-2 space-y-1.5">
      {RULES.map(({ label, test }) => {
        const ok = test(password);
        return (
          <li
            key={label}
            className={`flex items-center gap-2 text-xs transition-colors duration-200 ${
              ok ? "text-emerald-600" : "text-slate-400"
            }`}
          >
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold transition-colors duration-200 ${
                ok ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-400"
              }`}
            >
              {ok ? "✓" : "·"}
            </span>
            {label}
          </li>
        );
      })}
    </ul>
  );
}
