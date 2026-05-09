import type { SiteContent } from "../../../types/site";
import { Icon } from "../ui/Icon";
import { SectionHeader } from "../ui/SectionHeader";

export function ContactSection({ content }: { content: SiteContent }) {
  return (
    <section id="contact" className="section contact" aria-labelledby="contact-title">
      <div className="container">
        <SectionHeader {...content.sections.contact} id="contact-title" />
        <div className="contact-layout">
          <article className="contact-card">
            <Icon name="mail" />
            <div><span>{content.contact.emailLabel}</span><strong>{content.contact.emailValue}</strong></div>
          </article>
          <form className="contact-form magic-card" onSubmit={(event) => event.preventDefault()}>
            <label htmlFor="name">{content.contact.nameLabel}</label>
            <input id="name" name="name" type="text" placeholder={content.contact.namePlaceholder} autoComplete="name" />
            <label htmlFor="email">{content.contact.emailInputLabel}</label>
            <input id="email" name="email" type="email" placeholder={content.contact.emailPlaceholder} autoComplete="email" />
            <label htmlFor="message">{content.contact.messageLabel}</label>
            <textarea id="message" name="message" placeholder={content.contact.messagePlaceholder} rows={6} />
            <button className="button primary full" type="submit">{content.contact.submit}</button>
          </form>
        </div>
      </div>
    </section>
  );
}
