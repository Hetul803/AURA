import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AURA — Trust layer for AI coding agents",
  description: "AURA builds project Constitutions, analyzes AI-generated diffs, scores risk, exports cross-agent memory, and generates repair prompts.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
