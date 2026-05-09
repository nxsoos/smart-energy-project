import type { SiteContent } from "../../../types/site";
import { Icon, type IconName } from "../ui/Icon";
import { SectionHeader } from "../ui/SectionHeader";

function ArchitectureNetwork({ content }: { content: SiteContent["architectureNetwork"] }) {
  return (
    <div className="architecture-network">
      <svg className="network-lines" viewBox="0 0 1000 560" preserveAspectRatio="none" aria-hidden="true">
        <path className="network-path p-top-left" d="M500 280 C390 250 300 180 190 115" />
        <path className="network-path p-top" d="M500 280 C500 220 500 165 500 98" />
        <path className="network-path p-top-right" d="M500 280 C610 250 700 180 810 115" />
        <path className="network-path p-left" d="M500 280 C390 280 295 280 170 280" />
        <path className="network-path p-right" d="M500 280 C610 280 705 280 830 280" />
        <path className="network-path p-bottom-left" d="M500 280 C390 315 305 380 205 445" />
        <path className="network-path p-bottom" d="M500 280 C500 342 500 398 500 465" />
        <path className="network-path p-bottom-right" d="M500 280 C610 315 695 380 795 445" />
        <path className="network-path p-lower" d="M500 280 C500 365 500 438 500 528" />
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
