import type { ReactNode } from "react";

export type IconName =
  | "bolt"
  | "eye"
  | "shield"
  | "flame"
  | "cpu"
  | "activity"
  | "radar"
  | "sensor"
  | "cloud"
  | "monitor"
  | "mail"
  | "github"
  | "linkedin"
  | "stripEnergy"
  | "stripOccupancy"
  | "stripOverload"
  | "stripFire"
  | "stripAi"
  | "stripMonitor"
  | "stripPredict"
  | "stripSchedule";

export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  const isStripIcon = name.startsWith("strip");
  const common = {
    className: `icon ${className}`,
    viewBox: isStripIcon ? "0 0 44 44" : "0 0 24 24",
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg",
    "aria-hidden": true,
  };

  const paths: Record<IconName, ReactNode> = {
    bolt: <path d="M13 2 4 14h7l-1 8 10-13h-7l0-7Z" />,
    eye: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.7" /></>,
    shield: <><path d="M12 2.8 5 5.5v5.6c0 4.5 2.9 8.6 7 10.1 4.1-1.5 7-5.6 7-10.1V5.5l-7-2.7Z" /><path d="m13 7-4 6h3l-.5 4L16 10h-3l0-3Z" /></>,
    flame: <path d="M12.2 21c-4 0-7.2-2.8-7.2-6.8 0-2.5 1.4-4.5 3.4-6.2.2 1.7.9 2.8 2 3.5-.4-3.3 1.1-6.2 4.1-8.5.2 3.8 4.5 5.2 4.5 10.3 0 4.4-3.1 7.7-6.8 7.7Z" />,
    cpu: <><rect x="7" y="7" width="10" height="10" rx="2" /><path d="M9.5 1.8v3M14.5 1.8v3M9.5 19.2v3M14.5 19.2v3M1.8 9.5h3M1.8 14.5h3M19.2 9.5h3M19.2 14.5h3" /><path d="M10 12h4" /></>,
    activity: <path d="M3 12h4l2-6 4 12 2-6h6" />,
    radar: <><circle cx="12" cy="12" r="8" /><path d="M12 12 18 6M12 4v2M12 18v2M4 12h2M18 12h2" /><path d="M8.5 15.5a5 5 0 0 1 0-7" /></>,
    sensor: <><path d="M4 14a8 8 0 0 1 16 0" /><path d="M8 14a4 4 0 0 1 8 0" /><path d="M12 14v7" /><circle cx="12" cy="14" r="1.5" /></>,
    cloud: <path d="M7.5 18h9.2a4.2 4.2 0 0 0 .4-8.4A6 6 0 0 0 5.5 11 3.6 3.6 0 0 0 7.5 18Z" />,
    monitor: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></>,
    mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m4 7 8 6 8-6" /></>,
    github: <path d="M12 2.8a9.2 9.2 0 0 0-2.9 17.9c.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.2-3.4-1.2-.5-1.1-1.1-1.4-1.1-1.4-.9-.6.1-.6.1-.6 1 .1 1.6 1.1 1.6 1.1.9 1.5 2.4 1.1 2.9.8.1-.7.4-1.1.7-1.3-2.2-.2-4.6-1.1-4.6-4.9 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.8 1a9.6 9.6 0 0 1 5 0c1.9-1.3 2.8-1 2.8-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.8-2.3 4.7-4.6 4.9.4.3.7 1 .7 2v3c0 .3.2.6.7.5A9.2 9.2 0 0 0 12 2.8Z" />,
    linkedin: <><path d="M6.5 9.5V20" /><path d="M6.5 6.8v.1" /><path d="M11 20v-6c0-2.5 1.5-4 3.8-4 2.1 0 3.7 1.4 3.7 4.4V20" /><path d="M11 10v10" /></>,
    stripEnergy: <polygon points="26,4 10,24 20,24 18,40 34,20 24,20" />,
    stripOccupancy: <><circle cx="22" cy="16" r="5" /><path d="M10 38c0-6.627 5.373-12 12-12s12 5.373 12 12" /><rect x="4" y="4" width="36" height="36" rx="4" strokeOpacity="0.5" /><line x1="4" y1="12" x2="8" y2="12" /><line x1="36" y1="12" x2="40" y2="12" /><line x1="4" y1="32" x2="8" y2="32" /><line x1="36" y1="32" x2="40" y2="32" /></>,
    stripOverload: <><path d="M22 4L6 12v12c0 9 6.9 17.4 16 20 9.1-2.6 16-11 16-20V12L22 4z" /><polygon points="26,14 16,26 22,26 18,34 28,22 22,22" /></>,
    stripFire: <><path d="M22 40c-7 0-13-5.4-13-12.5 0-4.5 2.5-7.5 5-10C17 21 18 25 18 25c2-3 3-9 1-14 5 3 10 9 10 16.5C29 34.6 29 34.6 22 40z" /><path d="M22 40c-3 0-6-2-6-5.5 0-2 1-4 3-5 0 0 .5 2 2 3 1-1.5 1.5-4 1-6 2 1.5 4 4 4 7.5 0 3.4-1.5 6-4 6z" strokeOpacity="0.6" /></>,
    stripAi: <><rect x="12" y="12" width="20" height="20" rx="3" /><circle cx="22" cy="22" r="4" /><line x1="22" y1="4" x2="22" y2="12" /><line x1="22" y1="32" x2="22" y2="40" /><line x1="4" y1="22" x2="12" y2="22" /><line x1="32" y1="22" x2="40" y2="22" /><circle cx="22" cy="4" r="2" /><circle cx="22" cy="40" r="2" /><circle cx="4" cy="22" r="2" /><circle cx="40" cy="22" r="2" /></>,
    stripMonitor: <><polyline points="4,28 10,20 16,24 22,14 28,18 34,10 40,16" /><rect x="2" y="6" width="40" height="28" rx="3" strokeOpacity="0.4" /><line x1="16" y1="38" x2="28" y2="38" /><line x1="22" y1="34" x2="22" y2="38" /></>,
    stripPredict: <><circle cx="22" cy="22" r="18" strokeOpacity="0.3" /><circle cx="22" cy="22" r="12" strokeOpacity="0.5" /><circle cx="22" cy="22" r="5" /><line x1="22" y1="4" x2="22" y2="10" /><line x1="22" y1="34" x2="22" y2="40" /><line x1="4" y1="22" x2="10" y2="22" /><line x1="34" y1="22" x2="40" y2="22" /><line x1="26" y1="22" x2="32" y2="16" strokeWidth="2" /></>,
    stripSchedule: <><rect x="6" y="8" width="32" height="30" rx="3" strokeOpacity="0.5" /><line x1="6" y1="16" x2="38" y2="16" /><line x1="14" y1="4" x2="14" y2="12" /><line x1="30" y1="4" x2="30" y2="12" /><circle cx="22" cy="28" r="6" /><polyline points="22,24 22,28 25,30" /></>,
  };

  return <svg {...common}>{paths[name]}</svg>;
}
