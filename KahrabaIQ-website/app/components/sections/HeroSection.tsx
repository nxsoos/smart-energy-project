import Image from "next/image";
import type React from "react";
import type { SiteContent } from "../../../types/site";
import { Icon, type IconName } from "../ui/Icon";
import { ParticleField } from "../ui/ParticleField";

export function HeroSection({ content, scrollToSection }: { content: SiteContent; scrollToSection: (id: string) => void }) {
  return (
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
              <div className="strip-icon"><Icon name={item.icon as IconName} /></div>
              <div className="strip-label">{item.labelLines.map((line) => <span key={line}>{line}</span>)}</div>
            </div>
          ))}
        </div>
      </div>
      <button type="button" onClick={() => scrollToSection("features")} className="scroll-indicator" aria-label={content.accessibility.scrollFeatures}>
        <span>{content.hero.scroll}</span>
        <i />
      </button>
    </section>
  );
}
