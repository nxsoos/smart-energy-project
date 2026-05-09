import type { SiteContent } from "../../../types/site";
import { Icon, type IconName } from "../ui/Icon";
import { SectionHeader } from "../ui/SectionHeader";

function ArchitectureNetwork({ content }: { content: SiteContent["architectureNetwork"] }) {
  return (
    <div className="architecture-network">
      <svg className="network-lines" viewBox="0 0 1000 560" preserveAspectRatio="none" aria-hidden="true">
        <ellipse className="network-orbit" cx="500" cy="280" rx="335" ry="210" />
        <path className="network-path p-top-left" d="M500 280 C430 245 330 170 210 92" />
        <path className="network-path p-top" d="M500 280 C500 220 500 150 500 82" />
        <path className="network-path p-top-right" d="M500 280 C570 245 670 170 790 92" />
        <path className="network-path p-left" d="M500 280 C405 280 300 280 180 280" />
        <path className="network-path p-right" d="M500 280 C595 280 700 280 820 280" />
        <path className="network-path p-bottom-left" d="M500 280 C425 328 328 385 220 430" />
        <path className="network-path p-bottom" d="M500 280 C500 350 500 430 500 505" />
        <path className="network-path p-bottom-right" d="M500 280 C575 328 672 385 780 430" />
        <path className="network-path p-lower" d="M500 280 C560 342 650 388 735 430" />
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
