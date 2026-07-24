import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { apiRequest, setAccessTokenProvider } from "../api/client";
import { authConfigurationError, supabase } from "./supabase";
import { screenForAuth, type AuthIdentity, type AuthScreen, type FieldnoteRole } from "./guards";

interface ApiProfile {
  user_id: string;
  email: string;
  role: FieldnoteRole;
  must_change_password: boolean;
}

interface AuthContextValue {
  identity: AuthIdentity | null;
  email: string | null;
  screen: AuthScreen;
  signIn: (email: string, password: string) => Promise<void>;
  changeInitialPassword: (password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function loadProfile(session: Session): Promise<{ identity: AuthIdentity; email: string | null }> {
  const profile = await apiRequest<ApiProfile>("/auth/me");
  return {
    identity: { role: profile.role, mustChangePassword: profile.must_change_password },
    email: profile.email || session.user.email || null,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"loading" | "configured" | "configuration-error">(
    authConfigurationError ? "configuration-error" : "loading",
  );
  const [identity, setIdentity] = useState<AuthIdentity | null>(null);
  const [email, setEmail] = useState<string | null>(null);

  const clearIdentity = () => {
    setIdentity(null);
    setEmail(null);
  };

  const refreshProfile = async () => {
    if (!supabase) return;
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
      clearIdentity();
      return;
    }
    const profile = await loadProfile(session);
    setIdentity(profile.identity);
    setEmail(profile.email);
  };

  useEffect(() => {
    setAccessTokenProvider(async () => {
      if (!supabase) return null;
      const { data: { session } } = await supabase.auth.getSession();
      return session?.access_token || null;
    });
    if (!supabase) return undefined;

    let active = true;
    const sync = async (session: Session | null) => {
      if (!active) return;
      if (!session) {
        clearIdentity();
        setState("configured");
        return;
      }
      try {
        const profile = await loadProfile(session);
        if (!active) return;
        setIdentity(profile.identity);
        setEmail(profile.email);
      } catch {
        if (!active) return;
        clearIdentity();
      } finally {
        if (active) setState("configured");
      }
    };

    void supabase.auth.getSession().then(({ data }) => sync(data.session));
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      void sync(session);
    });
    return () => {
      active = false;
      subscription.unsubscribe();
      setAccessTokenProvider(null);
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    identity,
    email,
    screen: screenForAuth(state, identity),
    signIn: async (loginEmail, password) => {
      if (!supabase) throw new Error(authConfigurationError || "Supabase Auth nie jest skonfigurowany.");
      const { error } = await supabase.auth.signInWithPassword({ email: loginEmail, password });
      if (error) throw new Error(error.message);
      await refreshProfile();
    },
    changeInitialPassword: async (password) => {
      if (!supabase) throw new Error(authConfigurationError || "Supabase Auth nie jest skonfigurowany.");
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw new Error(error.message);
      await apiRequest("/auth/change-password", { method: "POST" });
      await refreshProfile();
    },
    signOut: async () => {
      if (supabase) await supabase.auth.signOut();
      clearIdentity();
    },
    refreshProfile,
  }), [email, identity, state]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider.");
  return value;
}
