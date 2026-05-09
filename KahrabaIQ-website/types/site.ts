import type en from "../data/site.en.json";

export type SiteContent = typeof en;
export type Locale = "en" | "ar";
export type TerminalContent = SiteContent["terminal"];
