import type { Metadata } from "next";
import AppNav from "@/components/AppNav";
import "./globals.css";

export const metadata: Metadata = {
  title: "SSAT — 정적 분석 웹",
  description: "CPG 그래프 뷰, SSAT 파이프라인 산출물, F2-A 근거, LLM 에이전트 검사를 한 곳에서.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <AppNav />
          <div className="app-body">{children}</div>
        </div>
      </body>
    </html>
  );
}
