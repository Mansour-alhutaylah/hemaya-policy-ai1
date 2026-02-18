import React, { createContext, useState, useContext, useEffect } from "react";
import { base44 } from "@/api/base44Client";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  // ✅ تحميل المستخدم بأمان من localStorage
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem("user");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [isAuthenticated, setIsAuthenticated] = useState(
    !!localStorage.getItem("token")
  );

  const [isLoadingAuth, setIsLoadingAuth] = useState(true);
  const [isLoadingPublicSettings] = useState(false);
  const [authError, setAuthError] = useState(null);

  useEffect(() => {
    checkAuth();
  }, []);

  // ✅ تسجيل الدخول
  const login = ({ token, user }) => {
    if (!token) return;

    localStorage.setItem("token", token);

    if (user) {
      localStorage.setItem("user", JSON.stringify(user));
      setUser(user);
    }

    setIsAuthenticated(true);
    setAuthError(null);
  };

  // ✅ التحقق من الجلسة
  const checkAuth = async () => {
    const token = localStorage.getItem("token");

    if (!token) {
      setIsAuthenticated(false);
      setUser(null);
      setIsLoadingAuth(false);
      return;
    }

    try {
      setIsLoadingAuth(true);
      setAuthError(null);

      const currentUser = await base44.auth.me();

      if (currentUser) {
        setUser(currentUser);
        localStorage.setItem("user", JSON.stringify(currentUser));
        setIsAuthenticated(true);
      } else {
        throw new Error("Invalid user");
      }
    } catch (error) {
      console.error("Auth check failed:", error);

      setIsAuthenticated(false);
      setUser(null);

      localStorage.removeItem("token");
      localStorage.removeItem("user");

      setAuthError({
        type: "auth_required",
        message: "Authentication required",
      });
    } finally {
      setIsLoadingAuth(false);
    }
  };

  // ✅ تسجيل الخروج
  const logout = () => {
    setUser(null);
    setIsAuthenticated(false);

    localStorage.removeItem("token");
    localStorage.removeItem("user");

    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isAuthed: isAuthenticated,
        isLoadingAuth,
        isLoadingPublicSettings,
        authError,
        login,
        logout,
        checkAppState: checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
