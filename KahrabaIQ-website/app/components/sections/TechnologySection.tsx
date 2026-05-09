import type { SiteContent } from "../../../types/site";
import { SectionHeader } from "../ui/SectionHeader";

export function TechnologySection({ content }: { content: SiteContent }) {
  return (
    <section id="technology" className="section technology" aria-labelledby="technology-title">
      <div className="container">
        <SectionHeader {...content.sections.technology} id="technology-title" />
        <div className="tech-groups">
          {content.technology.map(({ group, items }) => (
            <article className="tech-group" key={group}>
              <h3>{group}</h3>
              <div className="tech-pills">{items.map((item) => <span className="tech-pill" key={item}>{item}</span>)}</div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
