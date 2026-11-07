"use client";

import * as React from "react";
import { apiClient, clearAccessToken, requestTokenRefresh, setAccessToken } from "@/lib/api";

export interface UserProfile {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
  last_login_at?: string | null;
}

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthContextValue {
  status: AuthStatus;
  user: UserProfile | null;
  loginSuccess: (token: string, user?: UserProfile) => Promise<void>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | undefined>(undefined);

const AUTH_CHANNEL_NAME = "foliopilot_auth";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = React.useState<AuthStatus>("loading");
  const [user, setUser] = React.useState<UserProfile | null>(null);

  // Initialize and bootstrap authentication state on mount
  React.useEffect(() => {
    let isMounted = true;

    async function bootstrap() {
      try {
        const token = await requestTokenRefresh();
        if (!token) {
          if (isMounted) {
            setUser(null);
            setStatus("unauthenticated");
          }
          return;
        }

        const profile = await apiClient<UserProfile>("/api/v1/users/me");
        if (isMounted) {
          setUser(profile);
          setStatus("authenticated");
        }
      } catch {
        if (isMounted) {
          clearAccessToken();
          setUser(null);
          setStatus("unauthenticated");
        }
      }
    }

    bootstrap();

    // Cross-tab logout synchronization via BroadcastChannel
    let channel: BroadcastChannel | null = null;
    if (typeof window !== "undefined" && "BroadcastChannel" in window) {
      channel = new BroadcastChannel(AUTH_CHANNEL_NAME);
      channel.onmessage = (event) => {
        if (event.data === "logout") {
          clearAccessToken();
          setUser(null);
          setStatus("unauthenticated");
        }
      };
    }

    return () => {
      isMounted = false;
      if (channel) {
        channel.close();
      }
    };
  }, []);

  const loginSuccess = React.useCallback(async (token: string, directUser?: UserProfile) => {
    setAccessToken(token);
    if (directUser) {
      setUser(directUser);
      setStatus("authenticated");
    } else {
      try {
        const profile = await apiClient<UserProfile>("/api/v1/users/me");
        setUser(profile);
        setStatus("authenticated");
      } catch {
        clearAccessToken();
        setUser(null);
        setStatus("unauthenticated");
      }
    }
  }, []);

  const logout = React.useCallback(async () => {
    try {
      await apiClient<{ status: string }>("/api/v1/auth/logout", {
        method: "POST",
      });
    } catch {
      // Ignore network failures on logout
    } finally {
      clearAccessToken();
      setUser(null);
      setStatus("unauthenticated");

      if (typeof window !== "undefined" && "BroadcastChannel" in window) {
        const channel = new BroadcastChannel(AUTH_CHANNEL_NAME);
        channel.postMessage("logout");
        channel.close();
      }
    }
  }, []);

  const logoutAll = React.useCallback(async () => {
    try {
      await apiClient<{ status: string }>("/api/v1/auth/logout-all", {
        method: "POST",
      });
    } catch {
      // Ignore errors
    } finally {
      clearAccessToken();
      setUser(null);
      setStatus("unauthenticated");

      if (typeof window !== "undefined" && "BroadcastChannel" in window) {
        const channel = new BroadcastChannel(AUTH_CHANNEL_NAME);
        channel.postMessage("logout");
        channel.close();
      }
    }
  }, []);

  const value = React.useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      loginSuccess,
      logout,
      logoutAll,
    }),
    [status, user, loginSuccess, logout, logoutAll],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

