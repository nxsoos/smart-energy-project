import { NextResponse } from "next/server";
import nodemailer from "nodemailer";

type ContactPayload = {
  name?: string;
  email?: string;
  message?: string;
};

type RateLimitState = {
  count: number;
  expiresAt: number;
};

const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX = 5;
const DEFAULT_RECIPIENT = "admin@kahrabaiq.com";
const rateLimitCache = new Map<string, RateLimitState>();

const emailRegex = /^[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(\.[\w-]+)+$/i;

export async function POST(request: Request) {
  const clientKey = getClientKey(request);
  if (!checkRateLimit(clientKey)) {
    return NextResponse.json(
      { error: "Too many messages in a short time. Please try again later." },
      { status: 429 }
    );
  }

  let payload: ContactPayload;
  try {
    payload = (await request.json()) as ContactPayload;
  } catch {
    return NextResponse.json({ error: "Invalid JSON payload." }, { status: 400 });
  }

  const { name, email, message } = sanitizePayload(payload);
  const validationError = validatePayload({ name, email, message });
  if (validationError) {
    return NextResponse.json({ error: validationError }, { status: 400 });
  }

  const transporter = createTransport();
  if (!transporter) {
    return NextResponse.json(
      {
        error:
          "Email service is not configured. Please set the SMTP environment variables and try again."
      },
      { status: 500 }
    );
  }

  try {
    await transporter.sendMail({
      from: formatFromHeader(name, email),
      sender: getFromAddress(),
      to: getRecipientAddress(),
      envelope: {
        from: getFromAddress(),
        to: getRecipientAddress()
      },
      replyTo: email,
      subject: `KAHRABAIQ contact from ${name}`,
      text: buildTextContent({ name, email, message }),
      html: buildHtmlContent({ name, email, message })
    });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Failed to send contact email:", error);
    return NextResponse.json(
      {
        error: "The email service failed while sending your message. Please try again shortly."
      },
      { status: 502 }
    );
  }
}

function sanitizePayload({ name, email, message }: ContactPayload) {
  return {
    name: (name ?? "").trim(),
    email: (email ?? "").trim(),
    message: (message ?? "").trim()
  };
}

function validatePayload({
  name,
  email,
  message
}: Required<ContactPayload>): string | undefined {
  if (!name || !email || !message) {
    return "Name, email, and message are required.";
  }

  if (!emailRegex.test(email)) {
    return "Please enter a valid email address.";
  }

  if (name.length > 120) {
    return "Name must be under 120 characters.";
  }

  if (email.length > 160) {
    return "Email must be under 160 characters.";
  }

  if (message.length < 10) {
    return "Please provide a bit more detail in your message.";
  }

  if (message.length > 2000) {
    return "Message must be under 2000 characters.";
  }

  return undefined;
}

function getClientKey(request: Request): string {
  return (
    request.headers.get("x-forwarded-for") ||
    request.headers.get("cf-connecting-ip") ||
    request.headers.get("x-real-ip") ||
    "anonymous"
  );
}

function checkRateLimit(key: string): boolean {
  const now = Date.now();
  const entry = rateLimitCache.get(key);

  if (!entry || entry.expiresAt < now) {
    rateLimitCache.set(key, { count: 1, expiresAt: now + RATE_LIMIT_WINDOW_MS });
    return true;
  }

  if (entry.count >= RATE_LIMIT_MAX) {
    return false;
  }

  entry.count += 1;
  return true;
}

function createTransport() {
  const host = process.env.SMTP_HOST;
  const port = process.env.SMTP_PORT;
  const user = process.env.SMTP_USER;
  const pass = process.env.SMTP_PASS;

  if (!host || !port || !user || !pass) {
    return null;
  }

  const portNumber = Number(port);

  return nodemailer.createTransport({
    host,
    port: Number.isNaN(portNumber) ? 587 : portNumber,
    secure: portNumber === 465,
    auth: { user, pass }
  });
}

function getFromAddress() {
  const from = process.env.CONTACT_FROM_ADDRESS || process.env.SMTP_USER;
  if (!from) {
    throw new Error("Missing CONTACT_FROM_ADDRESS or SMTP_USER env var.");
  }
  return from;
}

function getRecipientAddress() {
  return process.env.CONTACT_TO_ADDRESS || DEFAULT_RECIPIENT;
}

function formatFromHeader(name: string, email: string) {
  if (!email) {
    return getFromAddress();
  }

  return name ? `${name} <${email}>` : email;
}

function buildTextContent({ name, email, message }: Required<ContactPayload>) {
  return [
    "New KAHRABAIQ contact submission",
    `Received: ${new Date().toISOString()}`,
    "",
    `Name: ${name}`,
    `Email: ${email}`,
    "",
    "Message:",
    message,
    "",
    "----",
    "Submitted via KAHRABAIQ contact form."
  ].join("\n");
}

function buildHtmlContent({ name, email, message }: Required<ContactPayload>) {
  return `
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a;">
      <h2 style="margin-bottom: 8px;">New KAHRABAIQ contact submission</h2>
      <p style="margin: 0 0 12px 0; color: #475569;">Received ${new Date().toLocaleString()}</p>
      <table style="border-collapse: collapse; width: 100%; max-width: 560px;">
        <tbody>
          <tr>
            <td style="padding: 6px 12px; font-weight: 600; background: #f1f5f9; width: 120px;">Name</td>
            <td style="padding: 6px 12px; border-bottom: 1px solid #e2e8f0;">${escapeHtml(name)}</td>
          </tr>
          <tr>
            <td style="padding: 6px 12px; font-weight: 600; background: #f1f5f9;">Email</td>
            <td style="padding: 6px 12px; border-bottom: 1px solid #e2e8f0;">
              <a href="mailto:${escapeHtml(email)}" style="color: #0ea5e9;">${escapeHtml(email)}</a>
            </td>
          </tr>
        </tbody>
      </table>
      <div style="margin-top: 16px; padding: 16px; border-radius: 12px; background: #f8fafc; border: 1px solid #e2e8f0;">
        <p style="margin: 0 0 8px 0; font-weight: 600;">Message</p>
        <p style="margin: 0; white-space: pre-wrap; color: #334155;">${escapeHtml(message)}</p>
      </div>
      <p style="margin-top: 24px; font-size: 12px; color: #94a3b8;">
        Sent via KAHRABAIQ contact form.
      </p>
    </div>
  `;
}

function escapeHtml(input: string) {
  return input
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
