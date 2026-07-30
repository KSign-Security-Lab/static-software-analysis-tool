import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "F2-A 테스트 웹 — CPG / AST / CG / DFG / CFG",
  description: "CPG 그래프 뷰를 추출·시각화하고 F2-A 근거 파이프라인을 실행합니다.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
