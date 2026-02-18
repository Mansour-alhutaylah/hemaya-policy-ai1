import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { base44 } from "@/api/base44Client";
import { pagesConfig } from "@/pages.config";

export default function NavigationTracker() {
  const location = useLocation();
  const { isAuthenticated } = useAuth();

  const Pages = pagesConfig?.Pages ?? {};
  const mainPageKey = pagesConfig?.mainPage ?? Object.keys(Pages)[0] ?? null;

  useEffect(() => {
    if (!mainPageKey) return;

    const pathname = location?.pathname ?? "/";
    let pageName = null;

    if (pathname === "/" || pathname === "") {
      pageName = mainPageKey;
    } else {
      const pathSegment = pathname.replace(/^\//, "").split("/")[0] || "";

      const pageKeys = Object.keys(Pages);
      const matchedKey = pageKeys.find(
        (key) => key.toLowerCase() === pathSegment.toLowerCase()
      );

      pageName = matchedKey || null;
    }

    const logFn = base44?.appLogs?.logUserInApp;

    if (isAuthenticated && pageName && typeof logFn === "function") {
      Promise.resolve(logFn(pageName)).catch(() => {
      });
    }
  }, [location?.pathname, isAuthenticated, Pages, mainPageKey]);

  return null;
}
