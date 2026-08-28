import type { Metadata } from "next";
import { inter, jetbrainsMono } from "./fonts";
import Providers from "./providers";

// Noto Sans KR comes in as a stylesheet rather than through next/font, because
// the value here is fontsource's own subsetting: ~120 @font-face rules, each
// with a unicode-range, so the browser fetches only the 20-50KB slices whose
// glyphs are actually on the page instead of a megabyte of Hangul up front.
// next/font/local cannot express that without enumerating every file.
import "@fontsource-variable/noto-sans-kr/wght.css";
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
    <html
      lang="ko"
      data-theme="dark"
      suppressHydrationWarning
      className={`${inter.variable} ${jetbrainsMono.variable}`}
    >
      {/* No chrome here: the workbench route group owns the shell, so the
          panel tree mounts once and survives navigation between perspectives.
          Routes outside it (/dev/*) get a bare page, which is what they want. */}
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
