"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";

type SiteContent = typeof import("../../data/site.en.json");

type IconName =
  | "bolt"
  | "eye"
  | "shield"
  | "flame"
  | "cpu"
  | "activity"
  | "radar"
  | "sensor"
  | "cloud"
  | "monitor"
  | "mail"
  | "github"
  | "linkedin"
  | "stripEnergy"
  | "stripOccupancy"
  | "stripOverload"
  | "stripFire"
  | "stripAi"
  | "stripMonitor"
  | "stripPredict"
  | "stripSchedule";

function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  const isStripIcon = name.startsWith("strip");
  const common = {
    className: `icon ${className}`,
    viewBox: isStripIcon ? "0 0 44 44" : "0 0 24 24",
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg",
    "aria-hidden": true,
  };

  const paths: Record<IconName, React.ReactNode> = {
    bolt: <path d="M13 2 4 14h7l-1 8 10-13h-7l0-7Z" />,
    eye: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.7" /></>,
    shield: <><path d="M12 2.8 5 5.5v5.6c0 4.5 2.9 8.6 7 10.1 4.1-1.5 7-5.6 7-10.1V5.5l-7-2.7Z" /><path d="m13 7-4 6h3l-.5 4L16 10h-3l0-3Z" /></>,
    flame: <path d="M12.2 21c-4 0-7.2-2.8-7.2-6.8 0-2.5 1.4-4.5 3.4-6.2.2 1.7.9 2.8 2 3.5-.4-3.3 1.1-6.2 4.1-8.5.2 3.8 4.5 5.2 4.5 10.3 0 4.4-3.1 7.7-6.8 7.7Z" />,
    cpu: <><rect x="7" y="7" width="10" height="10" rx="2" /><path d="M9.5 1.8v3M14.5 1.8v3M9.5 19.2v3M14.5 19.2v3M1.8 9.5h3M1.8 14.5h3M19.2 9.5h3M19.2 14.5h3" /><path d="M10 12h4" /></>,
    activity: <path d="M3 12h4l2-6 4 12 2-6h6" />,
    radar: <><circle cx="12" cy="12" r="8" /><path d="M12 12 18 6M12 4v2M12 18v2M4 12h2M18 12h2" /><path d="M8.5 15.5a5 5 0 0 1 0-7" /></>,
    sensor: <><path d="M4 14a8 8 0 0 1 16 0" /><path d="M8 14a4 4 0 0 1 8 0" /><path d="M12 14v7" /><circle cx="12" cy="14" r="1.5" /></>,
    cloud: <path d="M7.5 18h9.2a4.2 4.2 0 0 0 .4-8.4A6 6 0 0 0 5.5 11 3.6 3.6 0 0 0 7.5 18Z" />,
    monitor: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></>,
    mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m4 7 8 6 8-6" /></>,
    github: <path d="M12 2.8a9.2 9.2 0 0 0-2.9 17.9c.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.2-3.4-1.2-.5-1.1-1.1-1.4-1.1-1.4-.9-.6.1-.6.1-.6 1 .1 1.6 1.1 1.6 1.1.9 1.5 2.4 1.1 2.9.8.1-.7.4-1.1.7-1.3-2.2-.2-4.6-1.1-4.6-4.9 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.8 1a9.6 9.6 0 0 1 5 0c1.9-1.3 2.8-1 2.8-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.8-2.3 4.7-4.6 4.9.4.3.7 1 .7 2v3c0 .3.2.6.7.5A9.2 9.2 0 0 0 12 2.8Z" />,
    linkedin: <><path d="M6.5 9.5V20" /><path d="M6.5 6.8v.1" /><path d="M11 20v-6c0-2.5 1.5-4 3.8-4 2.1 0 3.7 1.4 3.7 4.4V20" /><path d="M11 10v10" /></>,
    stripEnergy: <polygon points="26,4 10,24 20,24 18,40 34,20 24,20" />,
    stripOccupancy: <><circle cx="22" cy="16" r="5" /><path d="M10 38c0-6.627 5.373-12 12-12s12 5.373 12 12" /><rect x="4" y="4" width="36" height="36" rx="4" strokeOpacity="0.5" /><line x1="4" y1="12" x2="8" y2="12" /><line x1="36" y1="12" x2="40" y2="12" /><line x1="4" y1="32" x2="8" y2="32" /><line x1="36" y1="32" x2="40" y2="32" /></>,
    stripOverload: <><path d="M22 4L6 12v12c0 9 6.9 17.4 16 20 9.1-2.6 16-11 16-20V12L22 4z" /><polygon points="26,14 16,26 22,26 18,34 28,22 22,22" /></>,
    stripFire: <><path d="M22 40c-7 0-13-5.4-13-12.5 0-4.5 2.5-7.5 5-10C17 21 18 25 18 25c2-3 3-9 1-14 5 3 10 9 10 16.5C29 34.6 29 34.6 22 40z" /><path d="M22 40c-3 0-6-2-6-5.5 0-2 1-4 3-5 0 0 .5 2 2 3 1-1.5 1.5-4 1-6 2 1.5 4 4 4 7.5 0 3.4-1.5 6-4 6z" strokeOpacity="0.6" /></>,
    stripAi: <><rect x="12" y="12" width="20" height="20" rx="3" /><circle cx="22" cy="22" r="4" /><line x1="22" y1="4" x2="22" y2="12" /><line x1="22" y1="32" x2="22" y2="40" /><line x1="4" y1="22" x2="12" y2="22" /><line x1="32" y1="22" x2="40" y2="22" /><circle cx="22" cy="4" r="2" /><circle cx="22" cy="40" r="2" /><circle cx="4" cy="22" r="2" /><circle cx="40" cy="22" r="2" /></>,
    stripMonitor: <><polyline points="4,28 10,20 16,24 22,14 28,18 34,10 40,16" /><rect x="2" y="6" width="40" height="28" rx="3" strokeOpacity="0.4" /><line x1="16" y1="38" x2="28" y2="38" /><line x1="22" y1="34" x2="22" y2="38" /></>,
    stripPredict: <><circle cx="22" cy="22" r="18" strokeOpacity="0.3" /><circle cx="22" cy="22" r="12" strokeOpacity="0.5" /><circle cx="22" cy="22" r="5" /><line x1="22" y1="4" x2="22" y2="10" /><line x1="22" y1="34" x2="22" y2="40" /><line x1="4" y1="22" x2="10" y2="22" /><line x1="34" y1="22" x2="40" y2="22" /><line x1="26" y1="22" x2="32" y2="16" strokeWidth="2" /></>,
    stripSchedule: <><rect x="6" y="8" width="32" height="30" rx="3" strokeOpacity="0.5" /><line x1="6" y1="16" x2="38" y2="16" /><line x1="14" y1="4" x2="14" y2="12" /><line x1="30" y1="4" x2="30" y2="12" /><circle cx="22" cy="28" r="6" /><polyline points="22,24 22,28 25,30" /></>,
  };

  return <svg {...common}>{paths[name]}</svg>;
}

function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let animation = 0;
    const particles = Array.from({ length: 80 }, () => ({
      x: Math.random(),
      y: Math.random(),
      vx: (Math.random() - 0.5) * 0.12,
      vy: (Math.random() - 0.5) * 0.12,
      size: 1 + Math.random() * 1.4,
    }));

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.offsetWidth;
      height = canvas.offsetHeight;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      particles.forEach((particle, index) => {
        particle.x += particle.vx / width;
        particle.y += particle.vy / height;
        if (particle.x < 0) particle.x = 1;
        if (particle.x > 1) particle.x = 0;
        if (particle.y < 0) particle.y = 1;
        if (particle.y > 1) particle.y = 0;

        const px = particle.x * width;
        const py = particle.y * height;
        ctx.beginPath();
        ctx.arc(px, py, particle.size, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255, 45, 45, 0.42)";
        ctx.fill();

        for (let next = index + 1; next < particles.length; next += 1) {
          const other = particles[next];
          const ox = other.x * width;
          const oy = other.y * height;
          const distance = Math.hypot(px - ox, py - oy);
          if (distance < 150) {
            ctx.globalAlpha = (1 - distance / 150) * 0.12;
            ctx.beginPath();
            ctx.moveTo(px, py);
            ctx.lineTo(ox, oy);
            ctx.strokeStyle = "rgba(255, 45, 45, 1)";
            ctx.lineWidth = 1;
            ctx.stroke();
            ctx.globalAlpha = 1;
          }
        }
      });
      animation = requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animation);
    };
  }, []);

  return <canvas ref={canvasRef} className="particle-field" aria-hidden="true" />;
}

export default function HomePage({ content, locale }: { content: SiteContent; locale: "en" | "ar" }) {
  const isArabic = locale === "ar";
  const [active, setActive] = useState("");
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const sections = content.nav
      .map(({ id }) => document.getElementById(id))
      .filter(Boolean) as HTMLElement[];
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActive(entry.target.id);
        });
      },
      { rootMargin: "-40% 0px -50% 0px", threshold: 0.01 },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [content.nav]);

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  useEffect(() => {
    let cleanup = () => {};
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return cleanup;

    import("gsap").then(({ gsap }) => {
      import("gsap/ScrollTrigger").then(({ ScrollTrigger }) => {
        gsap.registerPlugin(ScrollTrigger);
        gsap.from(".hero-kicker, .hero-mark, .hero-copy, .hero-actions, .scroll-indicator", {
          y: 26,
          opacity: 0,
          duration: 0.8,
          stagger: 0.14,
          ease: "power3.out",
        });
        gsap.from(".word", {
          y: 34,
          opacity: 0,
          duration: 0.72,
          stagger: 0.05,
          delay: 0.35,
          ease: "power3.out",
        });
        gsap.utils.toArray<HTMLElement>(".section-header").forEach((header) => {
          gsap.from(header, {
            scrollTrigger: { trigger: header, start: "top 85%" },
            y: 42,
            opacity: 0,
            duration: 0.75,
            ease: "power3.out",
          });
        });
        gsap.from(".feature-card", {
          scrollTrigger: { trigger: ".features-grid", start: "top 80%" },
          y: 46,
          opacity: 0,
          duration: 0.58,
          stagger: 0.06,
          ease: "power2.out",
        });
        gsap.from(".arch-node", {
          scrollTrigger: { trigger: ".arch-diagram", start: "top 75%" },
          scale: 0.92,
          opacity: 0,
          duration: 0.52,
          stagger: 0.1,
          ease: "power3.out",
        });
        gsap.from(".tech-pill", {
          scrollTrigger: { trigger: ".tech-groups", start: "top 78%" },
          scale: 0.9,
          opacity: 0,
          duration: 0.38,
          stagger: 0.035,
          ease: "power2.out",
        });
        gsap.from(".mockup-frame, .team-card, .contact-card, .contact-form", {
          scrollTrigger: { trigger: ".showcase-grid", start: "top 80%" },
          y: 34,
          opacity: 0,
          duration: 0.62,
          stagger: 0.06,
          ease: "power3.out",
        });
        cleanup = () => ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
      });
    });
    return () => cleanup();
  }, []);

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

  return (
    <>
      <div className="cursor-dot" aria-hidden="true" />
      <div className="cursor-ring" aria-hidden="true" />
      <button className="skip-link" type="button" onClick={() => scrollToSection("home")}>{content.accessibility.skip}</button>
      <nav className={`navbar ${isArabic ? "navbar-ar" : "navbar-en"} ${scrolled ? "scrolled" : ""}`} dir={isArabic ? "rtl" : "ltr"} aria-label={content.accessibility.nav}>
        <button type="button" className="brand image-brand" aria-label={content.accessibility.home} onClick={() => scrollToSection("home")}>
          <Image src={content.assets.wordmark} alt={content.assets.wordmarkAlt} width={150} height={100} className="brand-wordmark" priority />
        </button>
        <div className="nav-links" dir={isArabic ? "rtl" : "ltr"} aria-label={content.accessibility.navLinks}>
          {content.nav.map(({ label, id }) => (
            <button key={id} type="button" onClick={() => scrollToSection(id)} className={active === id ? "active" : ""}>{label}</button>
          ))}
        </div>
        <div className="locale-tabs" aria-label={content.languages.label}>
          <Link href="/en" className={locale === "en" ? "active" : ""} hrefLang="en">{content.languages.english}</Link>
          <Link href="/ar" className={locale === "ar" ? "active" : ""} hrefLang="ar">{content.languages.arabic}</Link>
        </div>
      </nav>
      <main lang={locale} dir={isArabic ? "rtl" : "ltr"} className={isArabic ? "locale-ar" : "locale-en"}>
        <section id="home" className="hero section" aria-labelledby="hero-title">
          <ParticleField />
          <div className="hero-glow" aria-hidden="true" />
          <div className="hero-grid" aria-hidden="true" />
          <div className="hero-content">
            <p className="hero-kicker">{content.hero.kicker}</p>
            <div className="hero-mark hero-identity" aria-label={content.brand.name}>
              <span />
              <div>
                <Image src={content.assets.fullIdentity} alt={content.assets.fullIdentityAlt} width={420} height={336} className="hero-identity-img" priority />
              </div>
              <span />
            </div>
            <h1 id="hero-title" className="hero-title">
              {content.hero.headline.map((word, index) => <span key={`${word}-${index}`} className="word">{word}</span>)}
            </h1>
            <p className="hero-copy">{content.hero.subheadline}</p>
            <div className="hero-actions">
              <button className="button primary" type="button" onClick={() => scrollToSection("features")}>{content.hero.primaryCta}</button>
              <button className="button ghost" type="button" onClick={() => scrollToSection("demo")}>{content.hero.secondaryCta}</button>
            </div>
            <div className="strip-wrap" role="list" aria-label={content.accessibility.homeStrip}>
              {content.homeStrip.map((item, index) => (
                <div className={`strip-item i-${item.key}`} role="listitem" key={item.key} style={{ "--i": index } as React.CSSProperties}>
                  <div className="strip-icon">
                    <Icon name={item.icon as IconName} />
                  </div>
                  <div className="strip-label">
                    {item.labelLines.map((line) => <span key={line}>{line}</span>)}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <button type="button" onClick={() => scrollToSection("features")} className="scroll-indicator" aria-label={content.accessibility.scrollFeatures}>
            <span>{content.hero.scroll}</span>
            <i />
          </button>
        </section>

        <section id="features" className="section features" aria-labelledby="features-title">
          <div className="container">
            <SectionHeader {...content.sections.features} id="features-title" />
            <div className="features-grid">
              {content.features.map(({ title, icon, description }) => (
                <article className="feature-card" key={title}>
                  <div className="feature-icon"><Icon name={icon as IconName} /></div>
                  <h3>{title}</h3>
                  <p>{description}</p>
                  <span className="feature-line" />
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="architecture" className="section architecture" aria-labelledby="architecture-title">
          <div className="container wide">
            <SectionHeader {...content.sections.architecture} id="architecture-title" />
            <div className="arch-scroll" tabIndex={0} aria-label={content.accessibility.architectureDiagram}>
              <div className="arch-diagram">
                {content.architecture.map(({ layer, title, items, icon }, index) => (
                  <div className="arch-column" key={title}>
                    <span className="layer-label">{layer}</span>
                    <article className="arch-node">
                      <Icon name={icon as IconName} />
                      <h3>{title}</h3>
                      {items.map((item) => <p key={item}>{item}</p>)}
                    </article>
                    {index < 3 && <Connector label={index === 1 ? content.connectors.mqtt : undefined} />}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="technology" className="section technology" aria-labelledby="technology-title">
          <div className="container">
            <SectionHeader {...content.sections.technology} id="technology-title" />
            <div className="tech-groups">
              {content.technology.map(({ group, items }) => (
                <article className="tech-group" key={group}>
                  <h3>{group}</h3>
                  <div className="tech-pills">
                    {items.map((item) => <span className="tech-pill" key={item}>{item}</span>)}
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="demo" className="section showcase" aria-labelledby="demo-title">
          <div className="container">
            <SectionHeader {...content.sections.demo} id="demo-title" />
            <div className="showcase-grid">
              <DashboardMockup content={content} />
              <MobileMockup content={content} />
              <HardwareMockup label={content.mockup.hardwareLabel} chip={content.mockup.hardwareChip} />
            </div>
          </div>
        </section>

        <section id="team" className="section team" aria-labelledby="team-title">
          <div className="container">
            <SectionHeader {...content.sections.team} id="team-title" />
            <div className="team-grid">
              {content.team.map(({ name, role, id, phone, image, imagePosition, githubUrl, linkedinUrl }) => (
                <article className="team-card" key={`${name}-${role}`}>
                  <div className={`avatar avatar-image ${image ? "member-photo" : "emblem-photo"}`}>
                    <Image src={image ?? content.assets.emblem} alt={image ? name : content.assets.emblemAlt} width={320} height={384} sizes="(max-width: 28rem) 100vw, 9rem" style={imagePosition ? { objectPosition: imagePosition } : undefined} />
                  </div>
                  <div>
                    <h3>{name}</h3>
                    <p>{role}</p>
                    <div className="member-meta">
                      <span>{content.teamLabels.id}</span>
                      <strong>{id}</strong>
                    </div>
                    <div className="member-meta">
                      <span>{content.teamLabels.phone}</span>
                      <strong><a href={`tel:${phone.replace(/\s/g, "")}`}>{phone}</a></strong>
                    </div>
                    {(linkedinUrl || githubUrl) && (
                      <div className="social-row">
                        {linkedinUrl && <a href={linkedinUrl} target="_blank" rel="noopener noreferrer" aria-label={`${name} ${content.social.linkedin}`}><Icon name="linkedin" /></a>}
                        {githubUrl && <a href={githubUrl} target="_blank" rel="noopener noreferrer" aria-label={`${name} ${content.social.github}`}><Icon name="github" /></a>}
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="contact" className="section contact" aria-labelledby="contact-title">
          <div className="container">
            <SectionHeader {...content.sections.contact} id="contact-title" />
            <div className="contact-layout">
              <article className="contact-card">
                <Icon name="mail" />
                <div><span>{content.contact.emailLabel}</span><strong>{content.contact.emailValue}</strong></div>
              </article>
              <form className="contact-form" onSubmit={(event) => event.preventDefault()}>
                <label htmlFor="name">{content.contact.nameLabel}</label>
                <input id="name" name="name" type="text" placeholder={content.contact.namePlaceholder} autoComplete="name" />
                <label htmlFor="email">{content.contact.emailInputLabel}</label>
                <input id="email" name="email" type="email" placeholder={content.contact.emailPlaceholder} autoComplete="email" />
                <label htmlFor="message">{content.contact.messageLabel}</label>
                <textarea id="message" name="message" placeholder={content.contact.messagePlaceholder} rows={6} />
                <button className="button primary full" type="submit">{content.contact.submit}</button>
              </form>
            </div>
          </div>
        </section>
      </main>
      <Footer content={content} />
    </>
  );
}

function SectionHeader({ label, title, subtitle, id }: { label: string; title: string; subtitle?: string; id: string }) {
  return (
    <header className="section-header">
      <p className="label">{label}</p>
      <h2 id={id}>{title}</h2>
      {subtitle && <p>{subtitle}</p>}
    </header>
  );
}

function Connector({ label }: { label?: string }) {
  return (
    <div className="connector" aria-hidden="true">
      {label && <span>{label}</span>}
      <svg viewBox="0 0 180 32" preserveAspectRatio="none">
        <defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>
        <path d="M4 16H170" markerEnd="url(#arrow)" />
      </svg>
    </div>
  );
}

function Frame({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return (
    <article className={`mockup-frame ${className}`}>
      <div className="frame-bar"><span /><span /><span /></div>
      <div className="frame-body">{children}</div>
    </article>
  );
}

function DashboardMockup({ content }: { content: SiteContent }) {
  return (
    <Frame className="dashboard-frame">
      <div className="dash-top"><span>{content.mockup.live}</span><strong>{content.mockup.safe}</strong></div>
      <div className="metric-row">
        {content.mockup.metrics.map(({ label, value }) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </div>
      <div className="dash-main">
        <div className="chart" aria-label={content.accessibility.chart}>
          {content.mockup.chartBars.map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
        </div>
        <div className="device-list">
          {content.mockup.devices.map((device) => <div key={device.name}><span>{device.name}</span><b className={device.tone === "warn" ? "warn" : ""}>{device.state}</b></div>)}
        </div>
      </div>
    </Frame>
  );
}

function MobileMockup({ content }: { content: SiteContent }) {
  return (
    <Frame className="phone-frame">
      <div className="phone-shell">
        <div className="phone-notch" />
        <span className="phone-label">{content.mockup.phoneLabel}</span>
        <strong>{content.mockup.phoneStatus}</strong>
        <div className="ring-meter" style={{ "--phone-score": content.mockup.phoneScore } as React.CSSProperties}><span>{content.mockup.phoneScore}</span></div>
        <div className="phone-list">{content.mockup.phoneItems.map((item) => <p key={item.label}>{item.label} <b>{item.value}</b></p>)}</div>
      </div>
    </Frame>
  );
}

function HardwareMockup({ label, chip }: { label: string; chip: string }) {
  return (
    <Frame className="hardware-frame">
      <div className="board">
        <span className="chip">{chip}</span>
        <i className="trace t1" /><i className="trace t2" /><i className="trace t3" />
        <span className="relay r1" /><span className="relay r2" /><span className="sensor-dot s1" /><span className="sensor-dot s2" />
        <strong>{label}</strong>
      </div>
    </Frame>
  );
}

function Footer({ content }: { content: SiteContent }) {
  return (
    <footer className="footer">
      <div className="footer-grid">
        <div>
          <button type="button" className="brand image-brand" onClick={() => document.getElementById("home")?.scrollIntoView({ behavior: "smooth", block: "start" })}>
            <Image src={content.assets.wordmark} alt={content.assets.wordmarkAlt} width={150} height={100} className="brand-wordmark" />
          </button>
          <p>{content.footer.university}</p>
        </div>
        <div className="footer-nav">
          {content.nav.map(({ label, id }) => <button key={id} type="button" onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })}>{label}</button>)}
        </div>
      </div>
      <div className="footer-bottom">
        <span>{content.footer.copyright}</span>
        {content.footer.projectRepo.url ? (
          <a href={content.footer.projectRepo.url} target="_blank" rel="noopener noreferrer">{content.footer.projectRepo.label}</a>
        ) : (
          <span className="repo-placeholder">{content.footer.projectRepo.label}: {content.footer.projectRepo.placeholder}</span>
        )}
      </div>
    </footer>
  );
}
