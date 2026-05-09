# KAHRABAIQ Website

Professional bilingual marketing website for **KAHRABAIQ**, an AI-driven smart energy and electrical safety system built as a University of Bahrain senior project.

The website presents the project identity, system capabilities, architecture, technology stack, showcase mockups, team profiles, and contact information in English and Arabic.

## Overview

KAHRABAIQ combines energy optimization, occupancy awareness, overload protection, fire and emergency logic, real-time monitoring, and predictive safety into one intelligent electrical safety platform.

This package contains the public-facing website built with Next.js App Router, TypeScript, localized JSON content, and responsive custom styling.

## Features

- Bilingual routes: `/en` and `/ar`
- Root redirect from `/` to `/en`
- English left-to-right layout and Arabic right-to-left layout
- Localized website content in JSON files
- Project identity assets, wordmark, favicon, and team member images
- Smooth section navigation without hash routing
- Responsive desktop and mobile layouts
- Animated hero, section transitions, and interface mockups
- Team member cards with outbound GitHub and LinkedIn links
- Footer placeholder for the full project repository link
- Production lint and build workflow support

## Tech Stack

| Area | Technology |
| --- | --- |
| Framework | Next.js 15 App Router |
| Language | TypeScript |
| UI | React 19 |
| Animation | GSAP |
| Styling | CSS custom properties and responsive CSS |
| Quality | ESLint, TypeScript checks, Next production build |

## Project Structure

```text
KahrabaIQ-website/
  app/
    [locale]/page.tsx        Localized English and Arabic page route
    components/
      HomePage.tsx           Page shell, navigation, animation, language transition state
      sections/              Page sections: hero, capabilities, architecture, demo, team, contact, footer
      ui/                    Reusable UI: icons, terminal, particles, section headers
    favicon.ico              App Router favicon
    globals.css              Global theme, layout, and responsive styling
    layout.tsx               Metadata, fonts, and root HTML shell
    page.tsx                 Redirects / to /en
  data/
    site.en.json             English localized content
    site.ar.json             Arabic localized content
  public/
    *.png, *.jpg             Brand identity and team image assets
  package.json               Scripts and dependencies
```

## Getting Started

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Open one of the localized routes:

```text
http://localhost:3000/en
http://localhost:3000/ar
```

If port `3000` is busy, Next.js may automatically use another port.

## Available Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the local Next.js development server |
| `npm run lint` | Run ESLint checks |
| `npm run build` | Create a production build and run type validation |
| `npm run start` | Start the production server after building |

## Content Editing

All visible copy and structured page data live in JSON files:

- English: `data/site.en.json`
- Arabic: `data/site.ar.json`

Use these files to update navigation labels, hero copy, feature descriptions, architecture items, technology lists, team data, contact details, footer text, and social links.

## Assets

Production assets are stored in `public/` and referenced from the localized JSON files.

Current brand assets include:

- `public/kahrabaiq-brand-identity.png`
- `public/kahrabaiq-emblem.png`
- `public/kahrabaiq-wordmark.png`

Team member images are also stored in `public/` and referenced from each member object in the locale JSON files.

## Project Repository Link

The footer includes a placeholder for the full project repository link.

To enable it later, update this field in both locale files:

```json
"projectRepo": {
  "label": "Full project repository",
  "placeholder": "Link coming soon",
  "url": "https://github.com/your-org/your-repo"
}
```

When `url` is empty, the website shows a non-clickable placeholder. When `url` is filled, it automatically renders as an outbound link.

## Localization Notes

- `/en` uses English content and left-to-right layout.
- `/ar` uses Arabic content and right-to-left layout.
- Language switching uses button-triggered terminal transitions, then routes between `/en` and `/ar` without resetting scroll.
- Internal section navigation uses buttons and smooth scrolling.

## Terminal Behavior

The website has two terminal modes:

- Initial page load uses the localized system boot terminal from `terminal` in the locale JSON file.
- Language switching uses the faster localized interface reconfiguration terminal from `languageTerminal` in the locale JSON file.

When adding or editing terminal lines, keep both English and Arabic JSON structures aligned.

## Quality Checks

Run these before deployment or handoff:

```bash
npm run lint
npm run build
```

If the local development server shows stale Next.js errors such as missing chunks or favicon route failures, clear the generated cache and restart:

```bash
rm -rf .next
npm run dev
```

## Deployment

The app is a standard Next.js application and can be deployed to Vercel, Netlify, Docker, or any Node.js hosting environment that supports Next.js.

Recommended production check:

```bash
npm run build
```

Then start the production server:

```bash
npm run start
```

## Project Context

KAHRABAIQ is part of the Smart Energy Project repository, alongside backend, mobile, Raspberry Pi, and ESP32 components. This website focuses on public presentation and project communication, while the operational platform components live in the rest of the repository.
