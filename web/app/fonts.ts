import localFont from "next/font/local";

/**
 * The typefaces, actually loaded.
 *
 * theme.css has named "Inter var" and "JetBrains Mono" since the design system
 * landed, but nothing ever declared an @font-face and there is no next/font in
 * the tree -- so every screen has quietly been rendering in whatever the OS
 * picked. This is that bug fixed.
 *
 * `next/font/local` over `next/font/google`: Google downloads from
 * fonts.gstatic.com at build time, which makes the build non-hermetic and puts
 * a third-party CDN in the critical path of `npm run build`. The files are
 * vendored from @fontsource-variable/* instead (kept as devDependencies for
 * provenance and updates), with their OFL text beside them -- OFL-1.1 wants
 * the licence to travel with the font, and vendoring makes that visible rather
 * than buried in node_modules.
 *
 * Latin subsets only, ~48KB and ~40KB. Hangul is Noto Sans KR's job; see
 * layout.tsx for why that one is loaded a different way.
 */

export const inter = localFont({
  src: "./fonts/InterVariable-latin.woff2",
  variable: "--font-inter",
  display: "swap",
  weight: "100 900",
  // Metric overrides against Arial, so the swap from fallback to Inter does
  // not reflow the page. In a dense IDE that shift is the whole layout.
  adjustFontFallback: "Arial",
});

export const jetbrainsMono = localFont({
  src: "./fonts/JetBrainsMonoVariable-latin.woff2",
  variable: "--font-jetbrains",
  display: "swap",
  weight: "100 800",
});
