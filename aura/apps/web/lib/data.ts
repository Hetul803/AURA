import { ShieldCheck, GitPullRequestArrow, ScrollText, BrainCircuit, GitBranch, Wrench, History, Settings } from "lucide-react";

export const navItems = [
  { href: "/dashboard", label: "Risk Reports", icon: GitPullRequestArrow },
  { href: "/repos", label: "Repos", icon: GitBranch },
  { href: "/memory-export", label: "Memory Export", icon: BrainCircuit },
  { href: "/attribution", label: "Attribution", icon: History },
  { href: "/provenance", label: "Provenance", icon: ScrollText },
  { href: "/policies", label: "Policies", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

export const sampleFindings = [
  { severity: "blocked", category: "secret_in_diff", file: "apps/api/auth/session.ts", text: "Added token-like value in an auth file." },
  { severity: "high", category: "auth_change", file: "apps/api/auth/session.ts", text: "Session logic changed and needs a human review." },
  { severity: "medium", category: "deploy_config_change", file: ".github/workflows/release.yml", text: "CI/deploy behavior changed." },
];

export const sampleRepos = [
  { name: "Hetul803/AURA", status: "Needs review", risk: 82, prs: 3 },
  { name: "founder/demo-api", status: "Passing", risk: 12, prs: 1 },
  { name: "team/checkout", status: "Blocked", risk: 100, prs: 2 },
];

export const agentExports = ["AURA.md", "AGENTS.md", "CLAUDE.md", ".cursorrules", ".clinerules", ".github/copilot-instructions.md"];

export const pledgeOptions = ["$19/mo", "$49/mo", "$99/mo", "Team pilot"];

export const heroActions = [
  { title: "Analyze a risky PR", detail: "Secret, auth, deploy, payment, dependency, and Constitution checks." },
  { title: "Generate AURA.md", detail: "One canonical project Constitution for every coding agent." },
  { title: "Export agent memory", detail: "Codex, Claude Code, Cursor, Copilot, Cline, and Roo stay aligned." },
  { title: "Request a repair", detail: "Copy a constrained prompt that fixes only the violated rule." },
];

export { Wrench };
