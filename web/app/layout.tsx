import type { Metadata } from "next";
import { inter, jetbrainsMono } from "./fonts";
import Providers from "./providers";

import "@fontsource-variable/noto-sans-kr/wght.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "SSAT",
  description: "LLM 에이전트 검사, F2-A 근거 추적, CPG·AST·DFG 추출.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="ko"
      data-theme="dark"
      suppressHydrationWarning
      className={`${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
