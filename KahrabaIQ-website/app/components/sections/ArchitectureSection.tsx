import type { SiteContent } from "../../../types/site";
import { Icon, type IconName } from "../ui/Icon";
import { SectionHeader } from "../ui/SectionHeader";

function ArchitectureNetwork({ content }: { content: SiteContent["architectureNetwork"] }) {
  return (
    <div className="architecture-network">
      <svg className="network-lines" viewBox="0 0 1000 560" preserveAspectRatio="none" aria-hidden="true">
        <ellipse className="network-orbit" cx="500" cy="280" rx="335" ry="210" />
        <path className="network-path p-top-left" d="M500 280 C410 250 330 178 215 112" />
        <path className="network-path p-top" d="M500 280 C500 222 500 158 500 82" />
        <path className="network-path p-top-right" d="M500 280 C590 250 670 178 785 112" />
        <path className="network-path p-left" d="M500 280 C390 272 282 255 165 238" />
        <path className="network-path p-right" d="M500 280 C610 272 718 255 835 238" />
        <path className="network-path p-bottom-left" d="M500 280 C405 322 318 390 220 462" />
        <path className="network-path p-bottom" d="M500 280 C500 348 500 416 500 490" />
        <path className="network-path p-bottom-right" d="M500 280 C595 322 682 390 780 462" />
        <path className="network-path p-lower" d="M500 280 C610 304 720 326 835 360" />
      </svg>
      <div className="network-core">
        <Icon name={content.center.icon as IconName} />
        <span>{content.center.label}</span>
        <strong>{content.center.title}</strong>
      </div>
      {content.nodes.map((node) => (
        <article className={`network-node ${node.position}`} key={node.title}>
          <Icon name={node.icon as IconName} />
          <div>
            <span>{node.label}</span>
            <strong>{node.title}</strong>
          </div>
        </article>
      ))}
    </div>
  );
}

export function ArchitectureSection({ content }: { content: SiteContent }) {
  return (
    <section id="architecture" className="section architecture" aria-labelledby="architecture-title">
      <div className="container wide">
        <SectionHeader {...content.sections.architecture} id="architecture-title" />
        <ArchitectureNetwork content={content.architectureNetwork} />
      </div>
    </section>
  );
}
