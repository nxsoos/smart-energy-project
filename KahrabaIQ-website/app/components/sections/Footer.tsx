import Image from "next/image";
import type { SiteContent } from "../../../types/site";
import { Icon } from "../ui/Icon";

export function Footer({ content }: { content: SiteContent }) {
  return (
    <footer className="footer">
      <div className="footer-shell">
        <div className="footer-grid">
          <div className="footer-brand-panel">
            <button type="button" className="brand image-brand footer-brand" onClick={() => document.getElementById("home")?.scrollIntoView({ behavior: "smooth", block: "start" })}>
              <Image src={content.assets.wordmark} alt={content.assets.wordmarkAlt} width={180} height={120} className="brand-wordmark" />
            </button>
            <p>{content.footer.university}</p>
          </div>
          <nav className="footer-nav" aria-label={content.accessibility.navLinks}>
            {content.nav.map(({ label, id }) => <button key={id} type="button" onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })}>{label}</button>)}
          </nav>
          <div className="footer-action-panel">
            {content.footer.projectRepo.url ? (
              <a className="repo-link" href={content.footer.projectRepo.url} target="_blank" rel="noopener noreferrer">
                <Icon name="github" />
                <span>{content.footer.projectRepo.label}</span>
              </a>
            ) : (
              <span className="repo-link repo-placeholder">
                <Icon name="github" />
                <span>{content.footer.projectRepo.label}: {content.footer.projectRepo.placeholder}</span>
              </span>
            )}
          </div>
        </div>
        <div className="footer-bottom">
          <span>{content.footer.copyright}</span>
          <span className="footer-status">{content.footer.status}</span>
        </div>
      </div>
    </footer>
  );
}
