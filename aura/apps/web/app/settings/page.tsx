import { AppShell, Badge, Card, PageHeader } from "../../components/ui";
import { backendGet, type SettingsResponse } from "../../lib/api";

export default async function SettingsPage() {
  const settings = await backendGet<SettingsResponse>("/settings/llm", {});
  return (
    <AppShell>
      <PageHeader eyebrow="Settings" title="Workspace, GitHub connection, and model keys." />
      <div className="grid gap-4 p-6 md:grid-cols-2 md:p-10">
        <Card>
          <Badge tone={settings.cap_status?.reached ? "warn" : "good"}>LLM cap</Badge>
          <h2 className="mt-3 font-medium">Provided reasoning allowance</h2>
          <p className="mt-2 text-sm text-muted-foreground">Used ${settings.cap_status?.used_usd ?? 0} of ${settings.cap_status?.cap_usd ?? 0} today. BYOK calls are uncapped and run on the user account.</p>
        </Card>
        {["GitHub App installation", "OpenAI BYOK key", "Anthropic BYOK key", "Sentry", "PostHog", "Workspace members"].map((item) => (
          <Card key={item}>
            <Badge>env-gated</Badge>
            <h2 className="mt-3 font-medium">{item}</h2>
            <p className="mt-2 text-sm text-muted-foreground">Configure when ready; no secrets are hardcoded.</p>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
