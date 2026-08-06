import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { apiRequest, setAccessTokenProvider } from "../api/client";
import { authConfigurationError, supabase } from "./supabase";
import { screenForAuth, type AuthIdentity, type AuthScreen, type FieldnoteRole } from "./guards";
import { changeInitialPassword } from "./passwordChange";

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
  error: string | null;
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
  const [error, setError] = useState<string | null>(null);

  const getSessionWithTimeout = async () => {
    if (!supabase) return { data: { session: null } };
    return await Promise.race([
      supabase.auth.getSession(),
      new Promise<never>((_, reject) => window.setTimeout(() => reject(new Error("Supabase Auth nie odpowiedział w wymaganym czasie.")), 8_000)),
    ]);
  };

  const clearIdentity = () => {
    setIdentity(null);
    setEmail(null);
  };

  const refreshProfile = async () => {
    if (!supabase) return;
    const { data: { session } } = await getSessionWithTimeout();
    if (!session) {
      clearIdentity();
      setError(null);
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
        setError(null);
      } catch {
        if (!active) return;
        clearIdentity();
        setError("Nie udało się sprawdzić sesji w lokalnym backendzie.");
      } finally {
        if (active) setState("configured");
      }
    };

    void getSessionWithTimeout().then(({ data }) => sync(data.session)).catch((reason) => {
      if (!active) return;
      clearIdentity();
      setError(reason instanceof Error ? reason.message : "Nie udało się wczytać sesji.");
      setState("configuration-error");
    });
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
    error,
    screen: screenForAuth(state, identity),
    signIn: async (loginEmail, password) => {
      if (!supabase) throw new Error(authConfigurationError || "Supabase Auth nie jest skonfigurowany.");
      const { error } = await supabase.auth.signInWithPassword({ email: loginEmail, password });
      if (error) throw new Error(error.message);
      await refreshProfile();
    },
    changeInitialPassword: async (password) => {
      if (!supabase) throw new Error(authConfigurationError || "Supabase Auth nie jest skonfigurowany.");
      await changeInitialPassword(password, apiRequest, refreshProfile);
    },
    signOut: async () => {
      if (supabase) await supabase.auth.signOut();
      clearIdentity();
    },
    refreshProfile,
  }), [email, error, identity, state]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider.");
  return value;
}
