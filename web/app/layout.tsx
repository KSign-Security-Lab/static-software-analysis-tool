import type { Metadata } from "next";
import SectionRail from "@/components/shell/SectionRail";
import "./globals.css";

export const metadata: Metadata = {
  title: "SSAT",
  description: "LLM 에이전트 검사, F2-A 근거 추적, CPG·AST·DFG 추출.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" data-theme="dark">
      <body>
        <div className="app">
          <SectionRail />
          <main className="app-main">{children}</main>
        </div>
      </body>
    </html>
  );
}
