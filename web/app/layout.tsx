import type { Metadata } from "next";
import SectionRail from "@/components/shell/SectionRail";
import Providers from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "SSAT",
  description: "LLM 에이전트 검사, F2-A 근거 추적, CPG·AST·DFG 추출.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // next-themes rewrites data-theme from its pre-paint script, before React
    // hydrates, so the server's attribute and the client's first read can
    // legitimately differ. Everything else under <html> must still match.
    <html lang="ko" data-theme="dark" suppressHydrationWarning>
      <body>
        <Providers>
          <div className="app">
            <SectionRail />
            <main className="app-main">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
