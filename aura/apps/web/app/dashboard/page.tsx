import { AppShell, Badge, Card, PageHeader } from "../../components/ui";
import { sampleFindings } from "../../lib/data";

export default function DashboardPage() {
  return (
    <AppShell>
      <PageHeader eyebrow="Hero screen" title="Risk Report">
        AURA turns AI-generated diffs into a plain-English decision: pass, caution, require review, or block.
      </PageHeader>
      <div className="grid gap-6 p-6 md:grid-cols-[1fr_360px] md:p-10">
        <Card>
          <div className="flex items-start justify-between gap-6">
            <div>
              <Badge tone="bad">Blocked</Badge>
              <h2 className="mt-4 text-2xl font-semibold">PR #42: Update auth session and release workflow</h2>
              <p className="mt-2 text-muted-foreground">Risk score 100/100. AURA found a secret-like value and auth/session changes in protected paths.</p>
            </div>
            <div className="rounded-lg border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-center">
              <div className="text-4xl font-semibold text-rose-100">100</div>
              <div className="text-xs text-rose-200">risk score</div>
            </div>
          </div>
          <div className="mt-8 space-y-3">
            {sampleFindings.map((finding) => (
              <div key={finding.category} className="rounded-md border border-white/10 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={finding.severity === "blocked" ? "bad" : finding.severity === "high" ? "warn" : "neutral"}>{finding.severity}</Badge>
                  <span className="font-medium">{finding.category}</span>
                  <span className="text-sm text-muted-foreground">{finding.file}</span>
                </div>
                <p className="mt-2 text-sm text-muted-foreground">{finding.text}</p>
              </div>
            ))}
          </div>
        </Card>
        <div className="space-y-6">
          <Card>
            <h3 className="font-medium">Repair prompt</h3>
            <pre className="mt-3 whitespace-pre-wrap rounded-md border border-white/10 bg-black p-3 text-xs leading-5 text-zinc-300">Fix only the secret and auth-session risks. Do not touch billing, deploy config, or unrelated tests. Add a regression test for session validation.</pre>
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
