import type { SiteContent } from "../../../types/site";
import { SectionHeader } from "../ui/SectionHeader";

export function TechnologySection({ content }: { content: SiteContent }) {
  return (
    <section id="technology" className="section technology" aria-labelledby="technology-title">
      <div className="container">
        <SectionHeader {...content.sections.technology} id="technology-title" />
        <div className="tech-groups">
          {content.technology.map(({ group, items }, index) => (
            <article className="tech-group" key={group}>
              <div className="tech-group-header">
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h3>{group}</h3>
                <em>{items.length}</em>
              </div>
              <div className="tech-pills">{items.map((item) => <span className="tech-pill" key={item}>{item}</span>)}</div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
