import type { SiteContent } from "../../../types/site";
import { Icon, type IconName } from "../ui/Icon";
import { SectionHeader } from "../ui/SectionHeader";

export function CapabilitiesSection({ content }: { content: SiteContent }) {
  return (
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
  );
}
