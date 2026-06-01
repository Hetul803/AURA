import Link from "next/link";
import { Badge, Card } from "../components/ui";
import { heroActions, pledgeOptions } from "../lib/data";

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="mx-auto flex min-h-[82vh] max-w-6xl flex-col justify-center px-6 py-20">
        <Badge tone="good">Private alpha</Badge>
        <h1 className="mt-6 max-w-5xl text-5xl font-semibold tracking-tight md:text-7xl">Aegisure — the control and audit plane for AI coding agents.</h1>
        <p className="mt-6 max-w-3xl text-lg leading-8 text-muted-foreground">
          See, govern, and remember everything every agent does, across vendors. Aegisure watches PRs, scores risky AI-generated diffs, preserves provenance, and gives teams an audit trail across Codex, Claude Code, Cursor, Copilot, Cline, and Roo. Cross-agent memory export is the free on-ramp.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/dashboard" className="rounded-md bg-white px-4 py-2 text-sm font-medium text-black">Open dashboard</Link>
          <Link href="/onboarding" className="rounded-md border border-white/15 px-4 py-2 text-sm font-medium text-white hover:bg-white/[0.06]">Connect GitHub</Link>
        </div>
        <div className="mt-14 grid gap-4 md:grid-cols-4">
          {heroActions.map((item) => (
            <Card key={item.title}>
              <h2 className="font-medium">{item.title}</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.detail}</p>
            </Card>
          ))}
        </div>
      </section>
      <section className="border-t border-white/10 px-6 py-16">
        <div className="mx-auto grid max-w-6xl gap-6 md:grid-cols-[1.2fr_.8fr]">
          <div>
            <Badge>Founding users</Badge>
            <h2 className="mt-4 text-3xl font-semibold">Pledge interest, do not pay yet.</h2>
            <p className="mt-3 max-w-2xl text-muted-foreground">This launch surface records waitlist and pledged price intent only. No card collection, no live charges.</p>
          </div>
          <Card>
            <label className="text-sm text-muted-foreground">Work email</label>
            <input className="mt-2 w-full rounded-md border border-white/10 bg-black px-3 py-2 text-sm outline-none" placeholder="founder@company.com" />
            <div className="mt-4 grid grid-cols-2 gap-2">
              {pledgeOptions.map((option) => <button key={option} className="rounded-md border border-white/10 px-3 py-2 text-sm text-zinc-200 hover:bg-white/[0.06]">{option}</button>)}
            </div>
          </Card>
        </div>
      </section>
    </main>
  );
}
