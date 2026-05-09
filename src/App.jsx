import { Suspense } from "react";
import { Toaster } from "@/components/ui/toaster";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClientInstance } from "@/lib/query-client";
import NavigationTracker from "@/lib/NavigationTracker";
import { pagesConfig } from "./pages.config";
import { BrowserRouter as Router, Route, Routes, Navigate } from "react-router-dom";
import PageNotFound from "./lib/PageNotFound";
import { AuthProvider, useAuth } from "@/lib/AuthContext";
import { ThemeProvider } from "@/lib/ThemeContext";
import UserNotRegisteredError from "@/components/UserNotRegisteredError";

// Phase 14: protected pages are loaded via React.lazy() in pages.config.js
// so each page becomes its own Vite chunk. Public auth pages stay
// eager-imported because (a) they ARE the initial shell on a logged-out
// visit, and (b) keeping them eager means no Suspense fallback flash on
// the very first paint. Same reasoning applies to Admin (handled outside
// the main Layout) and Landing (zero-state route).
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import VerifyOTP from "@/pages/VerifyOTP";
import ForgotPassword from "@/pages/ForgotPassword";
import Landing from "@/pages/Landing";
import Admin from "@/pages/Admin";

// Centered spinner shown by <Suspense> while a lazy-loaded page chunk
// is being fetched. Mirrors the auth-loading style used above so the
// transition feels seamless.
const RouteFallback = () => (
  <div className="fixed inset-0 flex items-center justify-center bg-background">
    <div className="w-8 h-8 border-4 border-border border-t-emerald-500 rounded-full animate-spin"></div>
  </div>
);

const { Pages, Layout, mainPage } = pagesConfig;
const mainPageKey = mainPage ?? Object.keys(Pages)[0];
const MainPage = mainPageKey ? Pages[mainPageKey] : <></>;

// Mirrors backend ADMIN_EMAIL + Sidebar admin check. Reusable when admin-only
// user-app pages are added in future (Audit Trail now lives in /admin only).
const ADMIN_EMAIL = "himayaadmin@gmail.com";
const ADMIN_ONLY_PAGES = new Set();

const LayoutWrapper = ({ children, currentPageName }) =>
  Layout ? <Layout currentPageName={currentPageName}>{children}</Layout> : <>{children}</>;

const AdminOnly = ({ children }) => {
  const { user } = useAuth();
  if (user?.email !== ADMIN_EMAIL) {
    return <Navigate to="/Dashboard" replace />;
  }
  return children;
};

const AuthenticatedApp = () => {
  const { isLoadingAuth, isLoadingPublicSettings, authError, navigateToLogin, isAuthed } = useAuth();

  // ✅ public routes (مسموح بدون تسجيل)
  // إذا كان مسجّل دخول وحاول يفتح /login حوله للداشبورد
  const publicRoutes = (
    <Routes>
      <Route path="/" element={isAuthed ? <Navigate to="/Dashboard" replace /> : <Landing />} />
      <Route path="/login" element={isAuthed ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/signup" element={isAuthed ? <Navigate to="/" replace /> : <Signup />} />
      <Route path="/verify-otp" element={<VerifyOTP />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );

  // Show loading
  if (isLoadingPublicSettings || isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-4 border-border border-t-emerald-500 rounded-full animate-spin"></div>
      </div>
    );
  }

  // إذا ما هو مسجّل دخول → ودّه لصفحات الدخول
  if (authError?.type === "auth_required" || !isAuthed) {
    // لو عندك navigateToLogin شغال خليه، بس ما نحتاجه هنا
    return publicRoutes;
  }

  // user_not_registered
  if (authError?.type === "user_not_registered") {
    return <UserNotRegisteredError />;
  }

  // ✅ Render main app (protected)
  // Phase 14: protected page components are React.lazy(); wrap Routes in
  // Suspense so the small per-page chunks fetch on demand. The fallback
  // spinner matches the auth-loading style above for a seamless feel.
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        {/* Admin panel — rendered without the main Layout, handles its own access control */}
        <Route path="/admin" element={<Admin />} />

        <Route
          path="/"
          element={
            <LayoutWrapper currentPageName={mainPageKey}>
              <MainPage />
            </LayoutWrapper>
          }
        />

        {Object.entries(Pages).map(([path, Page]) => {
          const element = (
            <LayoutWrapper currentPageName={path}>
              <Page />
            </LayoutWrapper>
          );
          return (
            <Route
              key={path}
              path={`/${path}`}
              element={
                ADMIN_ONLY_PAGES.has(path) ? <AdminOnly>{element}</AdminOnly> : element
              }
            />
          );
        })}

        <Route path="*" element={<PageNotFound />} />
      </Routes>
    </Suspense>
  );
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <QueryClientProvider client={queryClientInstance}>
          <Router>
            <NavigationTracker />
            <AuthenticatedApp />
          </Router>
          <Toaster />
        </QueryClientProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
