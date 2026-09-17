import localFont from "next/font/local";

export const inter = localFont({
  src: "./fonts/InterVariable-latin.woff2",
  variable: "--font-inter",
  display: "swap",
  weight: "100 900",
  adjustFontFallback: "Arial",
});

export const jetbrainsMono = localFont({
  src: "./fonts/JetBrainsMonoVariable-latin.woff2",
  variable: "--font-jetbrains",
  display: "swap",
  weight: "100 800",
});
