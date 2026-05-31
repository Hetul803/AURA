import { AppShell, Badge, Card, PageHeader } from "../../components/ui";

export default function SettingsPage() {
  return (
    <AppShell>
      <PageHeader eyebrow="Settings" title="Workspace, GitHub connection, and model keys." />
      <div className="grid gap-4 p-6 md:grid-cols-2 md:p-10">
        {["GitHub App installation", "OpenAI review key", "Anthropic review key", "Sentry", "PostHog", "Workspace members"].map((item) => (
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
