import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}

export async function getAuthHeaders(): Promise<Record<string, string>> {
  try {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    let token = data.session?.access_token;

    if (!token) {
      const { data: refreshData } = await supabase.auth.refreshSession();
      token = refreshData.session?.access_token;
    }

    if (!token && typeof window !== "undefined") {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key.includes("auth-token") || key.includes("supabase"))) {
          try {
            const raw = localStorage.getItem(key);
            if (raw) {
              const parsed = JSON.parse(raw);
              if (parsed?.access_token) {
                token = parsed.access_token;
                break;
              } else if (parsed?.currentSession?.access_token) {
                token = parsed.currentSession.access_token;
                break;
              }
            }
          } catch {
            // Ignore non-JSON items
          }
        }
      }
    }

    if (token) {
      return {
        Authorization: `Bearer ${token}`,
      };
    }
  } catch (err) {
    console.warn("Could not retrieve Supabase session access token:", err);
  }
  return {};
}


