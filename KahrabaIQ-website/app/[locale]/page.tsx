import { notFound } from "next/navigation";
import type { Metadata } from "next";
import HomePage from "../components/HomePage";
import en from "../../data/site.en.json";
import ar from "../../data/site.ar.json";

type Locale = "en" | "ar";

const content = { en, ar } satisfies Record<Locale, typeof en>;

export function generateStaticParams() {
  return [{ locale: "en" }, { locale: "ar" }];
}

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  if (locale !== "en" && locale !== "ar") notFound();
  return content[locale].metadata;
}

export default async function LocalePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (locale !== "en" && locale !== "ar") notFound();

  return <HomePage key={locale} content={content[locale]} allContent={content} locale={locale} />;
}
