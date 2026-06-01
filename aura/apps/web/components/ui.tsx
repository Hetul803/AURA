import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "../lib/utils";
import { navItems } from "../lib/data";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" }) {
  const tones = {
    neutral: "border-white/10 bg-white/[0.04] text-zinc-300",
    good: "border-emerald-400/20 bg-emerald-400/10 text-emerald-200",
    warn: "border-amber-400/20 bg-amber-400/10 text-amber-200",
    bad: "border-rose-400/20 bg-rose-400/10 text-rose-200",
  };
  return <span className={cn("inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium", tones[tone])}>{children}</span>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={cn("rounded-lg border border-white/10 bg-zinc-950/70 p-5 shadow-sm", className)}>{children}</section>;
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-white/10 bg-black/40 p-5 lg:block">
        <Link href="/" className="block text-lg font-semibold tracking-tight">Aegisure</Link>
        <p className="mt-1 text-sm text-muted-foreground">Trust layer for AI coding agents.</p>
        <nav className="mt-8 space-y-1">
          {navItems.map((item) => (
            <Link key={item.href} href={item.href} className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-zinc-300 hover:bg-white/[0.06] hover:text-white">
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="lg:pl-64">{children}</main>
    </div>
  );
}

export function PageHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="border-b border-white/10 px-6 py-8 md:px-10">
      <Badge>{eyebrow}</Badge>
      <h1 className="mt-4 max-w-4xl text-3xl font-semibold tracking-tight md:text-5xl">{title}</h1>
      {children ? <div className="mt-4 max-w-3xl text-base leading-7 text-muted-foreground">{children}</div> : null}
    </div>
  );
}
