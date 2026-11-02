// Supabase browser client. Configuration comes from src/lib/env.ts only —
// never read import.meta.env here, and never put a service key in the bundle.
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { Database } from './types';
import { env, supabaseConfigured } from '@/lib/env';

/**
 * Null when VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not set. Every
 * caller must handle null by showing an honest "sign-in not configured"
 * state instead of crashing.
 */
export const supabase: SupabaseClient<Database> | null = supabaseConfigured
  ? createClient<Database>(env.supabaseUrl, env.supabaseAnonKey, {
      auth: {
        storage: localStorage,
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;

export { supabaseConfigured };
