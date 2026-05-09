import type { Metadata } from "next";
import { Bebas_Neue, DM_Mono, JetBrains_Mono, Noto_Kufi_Arabic, Orbitron, Sora } from "next/font/google";
import "./globals.css";
import en from "../data/site.en.json";

const orbitron = Orbitron({
  subsets: ["latin"],
  weight: ["400", "600", "700", "900"],
  variable: "--font-orbitron",
  display: "swap",
});

const sora = Sora({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-sora",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

const bebas = Bebas_Neue({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-bebas",
  display: "swap",
});

const dmMono = DM_Mono({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  variable: "--font-dm-mono",
  display: "swap",
});

const arabic = Noto_Kufi_Arabic({
  subsets: ["arabic"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-arabic",
  display: "swap",
});

export const metadata: Metadata = {
  title: en.metadata.title,
  description: en.metadata.description,
  icons: {
    icon: [{ url: en.assets.favicon, type: "image/x-icon" }],
    shortcut: [en.assets.favicon],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${orbitron.variable} ${sora.variable} ${mono.variable} ${bebas.variable} ${dmMono.variable} ${arabic.variable}`}>
      <body>{children}</body>
    </html>
  );
}
