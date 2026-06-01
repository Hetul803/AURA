import { AppShell, Badge, Card, PageHeader } from "../../components/ui";
import { backendGet, type RiskReportsResponse } from "../../lib/api";

export default async function DashboardPage() {
  const data = await backendGet<RiskReportsResponse>("/risk-reports", { reports: [] });
  const latest = data.reports[0];
  return (
    <AppShell>
      <PageHeader eyebrow="Hero screen" title="Risk Report">
        Aegisure turns AI-generated diffs into a plain-English decision: pass, caution, require review, or block.
      </PageHeader>
      <div className="grid gap-6 p-6 md:grid-cols-[1fr_360px] md:p-10">
        <Card>
          <div className="flex items-start justify-between gap-6">
            <div>
              <Badge tone={latest ? "warn" : "neutral"}>{latest?.verdict || "No reports yet"}</Badge>
              <h2 className="mt-4 text-2xl font-semibold">{latest?.summary || "Connect GitHub and open a pull request to see the first live risk report."}</h2>
              <p className="mt-2 text-muted-foreground">Aegisure reads live PR analyses from the authenticated backend. No sample reports are shown.</p>
            </div>
            <div className="rounded-lg border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-center">
              <div className="text-4xl font-semibold text-rose-100">{latest?.score ?? 0}</div>
              <div className="text-xs text-rose-200">risk score</div>
            </div>
          </div>
          <div className="mt-8 space-y-3">
            {latest ? <p className="text-sm text-muted-foreground">Open the PR detail view to inspect severity-tiered findings.</p> : <p className="rounded-md border border-white/10 p-4 text-sm text-muted-foreground">No live findings yet. Install the GitHub App, open a PR, and Aegisure will post a check run and report here.</p>}
          </div>
        </Card>
        <div className="space-y-6">
          <Card>
            <h3 className="font-medium">Repair prompt</h3>
            <pre className="mt-3 whitespace-pre-wrap rounded-md border border-white/10 bg-black p-3 text-xs leading-5 text-zinc-300">{latest ? "Repair prompt available on the live risk report." : "No repair prompt yet."}</pre>
            <button className="mt-3 rounded-md bg-white px-3 py-2 text-sm font-medium text-black">Copy prompt</button>
          </Card>
          <Card>
            <h3 className="font-medium">Second opinion</h3>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Claude reviewing Codex output: disagreement. Human review required before merge.</p>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
