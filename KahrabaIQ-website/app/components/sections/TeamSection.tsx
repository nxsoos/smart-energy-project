import Image from "next/image";
import type { SiteContent } from "../../../types/site";
import { Icon } from "../ui/Icon";
import { SectionHeader } from "../ui/SectionHeader";

export function TeamSection({ content }: { content: SiteContent }) {
  return (
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
                <div className="member-meta"><span>{content.teamLabels.id}</span><strong>{id}</strong></div>
                <div className="member-meta"><span>{content.teamLabels.phone}</span><strong><a href={`tel:${phone.replace(/\s/g, "")}`}>{phone}</a></strong></div>
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
  );
}
