import React, { createContext, useState, useContext, useEffect } from "react";
import { api } from "@/api/apiClient";

const AuthContext = createContext(null);

function getCachedUser() {
  try {
    const saved = localStorage.getItem("user");
    return saved ? JSON.parse(saved) : null;
  } catch {
    return null;
  }
}

export const AuthProvider = ({ children }) => {
  const hasToken = !!localStorage.getItem("token");
  const cachedUser = getCachedUser();

  // Start authenticated immediately if we have both token + cached user.
  // Only show the loading spinner when we have a token but no cached user
  // (needs backend verification). No token = no spinner, show login right away.
  const [user, setUser] = useState(cachedUser);
  const [isAuthenticated, setIsAuthenticated] = useState(hasToken && !!cachedUser);
  const [isLoadingAuth, setIsLoadingAuth] = useState(hasToken && !cachedUser);
  const [isLoadingPublicSettings] = useState(false);
  const [authError, setAuthError] = useState(null);

  useEffect(() => {
    checkAuth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = ({ token, user }) => {
    if (!token) return;

    localStorage.setItem("token", token);

    if (user) {
      localStorage.setItem("user", JSON.stringify(user));
      setUser(user);
    }

    setIsAuthenticated(true);
    setIsLoadingAuth(false);
    setAuthError(null);
  };

  const checkAuth = async () => {
    const token = localStorage.getItem("token");

    // No token — unauthenticated, show login immediately
    if (!token) {
      setIsAuthenticated(false);
      setUser(null);
      setIsLoadingAuth(false);
      return;
    }

    // Token + cached user — use the cache, skip the backend call.
    // If the token is expired, the next API call from any page will
    // return 401 and the user will be redirected to login at that point.
    const cached = getCachedUser();
    if (cached) {
      setUser(cached);
      setIsAuthenticated(true);
      setIsLoadingAuth(false);
      return;
    }

    // Token exists but no cached user — verify with the backend
    try {
      setIsLoadingAuth(true);
      setAuthError(null);

      const currentUser = await api.auth.me();

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
