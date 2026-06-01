import { Badge, Card } from "../../components/ui";
import { githubOAuthUrl, supabaseConfig } from "../../lib/supabase";

export default function AuthPage() {
  const cfg = supabaseConfig();
  const url = githubOAuthUrl("/dashboard");
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      <Card className="w-full max-w-md">
        <Badge tone={cfg.configured ? "good" : "warn"}>{cfg.configured ? "Supabase ready" : "Supabase env missing"}</Badge>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight">Sign in with GitHub</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">Aegisure scopes every repo, PR, audit event, and memory record to your workspace.</p>
        {cfg.configured ? (
          <a href={url} className="mt-6 block rounded-md bg-white px-4 py-2 text-center text-sm font-medium text-black">Continue with GitHub</a>
        ) : (
          <p className="mt-6 rounded-md border border-amber-400/20 bg-amber-400/10 p-3 text-sm text-amber-100">Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` to enable login.</p>
        )}
      </Card>
    </main>
  );
}
