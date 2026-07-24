import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const authConfigurationError = !supabaseUrl || !supabaseAnonKey
  ? "Brak konfiguracji VITE_SUPABASE_URL lub VITE_SUPABASE_ANON_KEY."
  : null;

export const supabase: SupabaseClient | null = authConfigurationError
  ? null
  : createClient(supabaseUrl, supabaseAnonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
