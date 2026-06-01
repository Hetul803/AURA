import { AppShell, Badge, Card, PageHeader } from "../../components/ui";
import { backendGet, type AuditResponse } from "../../lib/api";

export default async function AuditPage() {
  const data = await backendGet<AuditResponse>("/audit", { events: [] });
  return (
    <AppShell>
      <PageHeader eyebrow="Audit" title="Every approval, block, repair, and export." />
      <div className="p-6 md:p-10">
        <Card>
          {data.events.length === 0 ? <p className="text-sm text-muted-foreground">No live audit events yet.</p> : <div className="space-y-3 text-sm text-muted-foreground">{data.events.map((event) => <p key={event.id || event.created_at}><Badge>{event.event_type || "event"}</Badge> {event.message}</p>)}</div>}
        </Card>
        <Card className="mt-6">
          <Badge>Audit chatbot</Badge>
          <h2 className="mt-3 font-medium">Ask grounded questions over your audit data</h2>
          <p className="mt-2 text-sm text-muted-foreground">Examples: “what did Codex change today?”, “which agent touched auth this week?”, “show risky PRs still open.” Answers are grounded only in your workspace records and follow LLM caps/BYOK settings.</p>
        </Card>
      </div>
    </AppShell>
  );
}
