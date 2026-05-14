"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import type { Locale, SiteContent } from "../../types/site";
import { ArchitectureSection } from "./sections/ArchitectureSection";
import { CapabilitiesSection } from "./sections/CapabilitiesSection";
import { ContactSection } from "./sections/ContactSection";
import { DemoSection } from "./sections/DemoSection";
import { Footer } from "./sections/Footer";
import { HeroSection } from "./sections/HeroSection";
import { TeamSection } from "./sections/TeamSection";
import { TechnologySection } from "./sections/TechnologySection";
import { BootTerminal } from "./ui/BootTerminal";

export default function HomePage({ content, allContent, locale }: { content: SiteContent; allContent: Record<Locale, SiteContent>; locale: Locale }) {
  const isArabic = locale === "ar";
  const router = useRouter();
  const [boot, setBoot] = useState<{ visible: boolean; locale: Locale; fast: boolean; target?: Locale }>({ visible: true, locale, fast: false });
  const [active, setActive] = useState("");
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    router.prefetch("/en");
    router.prefetch("/ar");
  }, [router]);

  useEffect(() => {
    const arrivedFromSwitch = window.sessionStorage.getItem("kahrabaiq-transition-locale") === locale;
    if (!arrivedFromSwitch) return;
    const y = Number(window.sessionStorage.getItem("kahrabaiq-scroll-y") || "0");
    window.sessionStorage.removeItem("kahrabaiq-transition-locale");
    window.sessionStorage.removeItem("kahrabaiq-scroll-y");
    setBoot((current) => ({ ...current, visible: false }));
    window.requestAnimationFrame(() => window.scrollTo({ top: y }));
  }, [locale]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const sections = content.nav.map(({ id }) => document.getElementById(id)).filter(Boolean) as HTMLElement[];
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => { if (entry.isIntersecting) setActive(entry.target.id); }),
      { rootMargin: "-40% 0px -50% 0px", threshold: 0.01 },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [content.nav]);

  useEffect(() => {
    let active = true;
    let cleanup = () => {};
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return cleanup;

    import("gsap").then(({ gsap }) => {
      import("gsap/ScrollTrigger").then(({ ScrollTrigger }) => {
        if (!active) return;
        gsap.registerPlugin(ScrollTrigger);
        const context = gsap.context(() => {
          gsap.from(".hero-kicker, .hero-mark, .hero-copy, .hero-actions, .scroll-indicator", { y: 26, opacity: 0, duration: 0.8, stagger: 0.14, ease: "power3.out" });
          gsap.from(".word", { y: 34, opacity: 0, duration: 0.72, stagger: 0.05, delay: 0.35, ease: "power3.out" });
          gsap.utils.toArray<HTMLElement>(".section-header").forEach((header) => {
            gsap.from(header, { scrollTrigger: { trigger: header, start: "top 85%" }, y: 42, opacity: 0, duration: 0.75, ease: "power3.out" });
          });
          gsap.from(".feature-card", { scrollTrigger: { trigger: ".features-grid", start: "top 80%" }, y: 46, duration: 0.58, stagger: 0.06, ease: "power2.out" });
          gsap.from(".network-core, .network-node", { scrollTrigger: { trigger: ".architecture-network", start: "top 75%" }, opacity: 0, duration: 0.52, stagger: 0.06, ease: "power3.out" });
          gsap.from(".tech-pill", { scrollTrigger: { trigger: ".tech-groups", start: "top 78%" }, scale: 0.9, opacity: 0, duration: 0.38, stagger: 0.035, ease: "power2.out" });
          gsap.from(".mockup-frame, .team-card, .contact-card, .contact-form", { scrollTrigger: { trigger: ".showcase-grid", start: "top 80%" }, y: 34, opacity: 0, duration: 0.62, stagger: 0.06, ease: "power3.out" });
        });
        cleanup = () => context.revert();
      });
    });
    return () => {
      active = false;
      cleanup();
    };
  }, [locale]);

  useEffect(() => {
    if (!window.matchMedia("(pointer: fine)").matches) return;
    const dot = document.querySelector<HTMLElement>(".cursor-dot");
    const ring = document.querySelector<HTMLElement>(".cursor-ring");
    if (!dot || !ring) return;
    let x = window.innerWidth / 2;
    let y = window.innerHeight / 2;
    let rx = x;
    let ry = y;
    const move = (event: MouseEvent) => {
      x = event.clientX;
      y = event.clientY;
      dot.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    };
    const tick = () => {
      rx += (x - rx) * 0.18;
      ry += (y - ry) * 0.18;
      ring.style.transform = `translate3d(${rx}px, ${ry}px, 0)`;
      requestAnimationFrame(tick);
    };
    window.addEventListener("mousemove", move);
    tick();
    return () => window.removeEventListener("mousemove", move);
  }, []);

  useEffect(() => {
    if (!window.matchMedia("(pointer: fine)").matches) return;
    const cards = document.querySelectorAll<HTMLElement>(".magic-card");
    const move = (event: MouseEvent) => {
      const card = event.currentTarget as HTMLElement;
      const rect = card.getBoundingClientRect();
      card.style.setProperty("--mouse-x", `${((event.clientX - rect.left) / rect.width) * 100}%`);
      card.style.setProperty("--mouse-y", `${((event.clientY - rect.top) / rect.height) * 100}%`);
    };
    cards.forEach((card) => card.addEventListener("mousemove", move));
    return () => cards.forEach((card) => card.removeEventListener("mousemove", move));
  }, [locale]);

  const scrollToSection = (id: string) => {
    setMenuOpen(false);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const switchLocale = (target: Locale) => {
    if (target === locale || boot.visible) return;
    setMenuOpen(false);
    window.sessionStorage.setItem("kahrabaiq-scroll-y", String(window.scrollY));
    window.sessionStorage.setItem("kahrabaiq-transition-locale", target);
    setBoot({ visible: true, locale: target, fast: true, target });
  };

  const completeBoot = () => {
    if (boot.target) {
      router.push(`/${boot.target}`, { scroll: false });
      return;
    }
    setBoot((current) => ({ ...current, visible: false }));
  };

  return (
    <>
      {boot.visible && <BootTerminal terminal={boot.fast ? allContent[boot.locale].languageTerminal : allContent[boot.locale].terminal} locale={boot.locale} fast={boot.fast} onDone={completeBoot} />}
      <div className="site-shell">
        <div className="cursor-dot" aria-hidden="true" />
        <div className="cursor-ring" aria-hidden="true" />
        <button className="skip-link" type="button" onClick={() => scrollToSection("home")}>{content.accessibility.skip}</button>
        <nav className={`navbar ${isArabic ? "navbar-ar" : "navbar-en"} ${scrolled ? "scrolled" : ""} ${menuOpen ? "menu-open" : ""}`} dir={isArabic ? "rtl" : "ltr"} aria-label={content.accessibility.nav}>
          <button type="button" className="brand image-brand" aria-label={content.accessibility.home} onClick={() => scrollToSection("home")}>
            <Image src={content.assets.wordmark} alt={content.assets.wordmarkAlt} width={150} height={100} className="brand-wordmark" priority />
          </button>
          <button type="button" className="menu-toggle" aria-label={content.accessibility.navLinks} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
            <span />
            <span />
            <span />
          </button>
          <div className="nav-links" dir={isArabic ? "rtl" : "ltr"} aria-label={content.accessibility.navLinks}>
            {content.nav.map(({ label, id }) => <button key={id} type="button" onClick={() => scrollToSection(id)} className={active === id ? "active" : ""}>{label}</button>)}
          </div>
          <div className="locale-tabs" aria-label={content.languages.label}>
            <button type="button" className={locale === "en" ? "active" : ""} onClick={() => switchLocale("en")}>{content.languages.english}</button>
            <button type="button" className={locale === "ar" ? "active" : ""} onClick={() => switchLocale("ar")}>{content.languages.arabic}</button>
          </div>
        </nav>
        <main lang={locale} dir={isArabic ? "rtl" : "ltr"} className={isArabic ? "locale-ar" : "locale-en"}>
          <HeroSection content={content} scrollToSection={scrollToSection} />
          <CapabilitiesSection content={content} />
          <ArchitectureSection content={content} />
          <TechnologySection content={content} />
          <DemoSection content={content} />
          <TeamSection content={content} />
          <ContactSection content={content} />
        </main>
        <Footer content={content} />
      </div>
    </>
  );
}
