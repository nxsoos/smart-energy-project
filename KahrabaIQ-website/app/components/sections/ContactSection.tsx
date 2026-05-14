"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import type { SiteContent } from "../../../types/site";
import { Icon } from "../ui/Icon";
import { SectionHeader } from "../ui/SectionHeader";

export function ContactSection({ content }: { content: SiteContent }) {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (loading) return;

    setStatus(null);
    setError(null);
    setLoading(true);

    const form = event.currentTarget;
    const formData = new FormData(form);
    const payload = {
      name: formData.get("name")?.toString().trim() ?? "",
      email: formData.get("email")?.toString().trim() ?? "",
      message: formData.get("message")?.toString().trim() ?? ""
    };

    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(content.contact.error);
      }

      setStatus(content.contact.success);
      form.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : content.contact.error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section id="contact" className="section contact" aria-labelledby="contact-title">
      <div className="container">
        <SectionHeader {...content.sections.contact} id="contact-title" />
        <div className="contact-layout">
          <article className="contact-card">
            <Icon name="mail" />
            <div><span>{content.contact.emailLabel}</span><strong>{content.contact.emailValue}</strong></div>
          </article>
          <form className="contact-form magic-card" onSubmit={handleSubmit}>
            <label htmlFor="name">{content.contact.nameLabel}</label>
            <input id="name" name="name" type="text" placeholder={content.contact.namePlaceholder} autoComplete="name" required />
            <label htmlFor="email">{content.contact.emailInputLabel}</label>
            <input id="email" name="email" type="email" placeholder={content.contact.emailPlaceholder} autoComplete="email" required />
            <label htmlFor="message">{content.contact.messageLabel}</label>
            <textarea id="message" name="message" placeholder={content.contact.messagePlaceholder} rows={6} required />
            <button className="button primary full" type="submit" disabled={loading}>
              {loading ? content.contact.sending : content.contact.submit}
            </button>
            {status && <p className="form-status success">{status}</p>}
            {error && <p className="form-status error">{error}</p>}
          </form>
        </div>
      </div>
    </section>
  );
}
