import type { SiteContent } from "../../../types/site";
import { Icon, type IconName } from "../ui/Icon";
import { SectionHeader } from "../ui/SectionHeader";

function ArchitectureNetwork({ content }: { content: SiteContent["architectureNetwork"] }) {
  return (
    <div className="architecture-network">
      <div className="network-stage">
        <svg className="network-lines" viewBox="0 0 1000 560" preserveAspectRatio="none" aria-hidden="true">
          <ellipse className="network-orbit orbit-outer" cx="500" cy="280" rx="340" ry="198" />
          <path className="network-path p-top-left" d="M200 130 L395 210" />
          <path className="network-path p-top" d="M500 95 L500 200" />
          <path className="network-path p-top-right" d="M800 130 L605 210" />
          <path className="network-path p-left" d="M250 280 L380 280" />
          <path className="network-path p-right" d="M620 280 L750 280" />
          <path className="network-path p-bottom-left" d="M405 350 L140 430" />
          <path className="network-path p-bottom" d="M470 360 L380 430" />
          <path className="network-path p-lower" d="M530 360 L620 430" />
          <path className="network-path p-bottom-right" d="M595 350 L860 430" />
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
