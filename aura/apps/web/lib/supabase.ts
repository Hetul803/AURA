export function supabaseConfig() {
  return {
    url: process.env.NEXT_PUBLIC_SUPABASE_URL || "",
    anonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "",
    configured: Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY),
  };
}

export function githubOAuthUrl(redirectTo = "/dashboard") {
  const cfg = supabaseConfig();
  if (!cfg.configured) return "";
  const params = new URLSearchParams({
    provider: "github",
    redirect_to: redirectTo,
  });
  return `${cfg.url}/auth/v1/authorize?${params.toString()}`;
}
