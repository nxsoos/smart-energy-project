import type React from "react";
import type { SiteContent } from "../../../types/site";
import { SectionHeader } from "../ui/SectionHeader";

function Frame({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return (
    <article className={`mockup-frame ${className}`}>
      <div className="frame-bar"><span /><span /><span /></div>
      <div className="frame-body">{children}</div>
    </article>
  );
}

function DashboardMockup({ content }: { content: SiteContent }) {
  return (
    <Frame className="dashboard-frame">
      <div className="dash-top"><span>{content.mockup.live}</span><strong>{content.mockup.safe}</strong></div>
      <div className="metric-row">{content.mockup.metrics.map(({ label, value }) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <div className="dash-main">
        <div className="chart" aria-label={content.accessibility.chart}>{content.mockup.chartBars.map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div>
        <div className="device-list">{content.mockup.devices.map((device) => <div key={device.name}><span>{device.name}</span><b className={device.tone === "warn" ? "warn" : ""}>{device.state}</b></div>)}</div>
      </div>
    </Frame>
  );
}

function MobileMockup({ content }: { content: SiteContent }) {
  return (
    <Frame className="phone-frame">
      <div className="phone-shell">
        <div className="phone-notch" />
        <span className="phone-label">{content.mockup.phoneLabel}</span>
        <strong>{content.mockup.phoneStatus}</strong>
        <div className="ring-meter" style={{ "--phone-score": content.mockup.phoneScore } as React.CSSProperties}><span>{content.mockup.phoneScore}</span></div>
        <div className="phone-list">{content.mockup.phoneItems.map((item) => <p key={item.label}>{item.label} <b>{item.value}</b></p>)}</div>
      </div>
    </Frame>
  );
}

function HardwareMockup({ label, chip }: { label: string; chip: string }) {
  return (
    <Frame className="hardware-frame">
      <div className="board">
        <span className="chip">{chip}</span>
        <i className="trace t1" /><i className="trace t2" /><i className="trace t3" />
        <span className="relay r1" /><span className="relay r2" /><span className="sensor-dot s1" /><span className="sensor-dot s2" />
        <strong>{label}</strong>
      </div>
    </Frame>
  );
}

export function DemoSection({ content }: { content: SiteContent }) {
  return (
    <section id="demo" className="section showcase" aria-labelledby="demo-title">
      <div className="container">
        <SectionHeader {...content.sections.demo} id="demo-title" />
        <div className="showcase-grid">
          <DashboardMockup content={content} />
          <MobileMockup content={content} />
          <HardwareMockup label={content.mockup.hardwareLabel} chip={content.mockup.hardwareChip} />
        </div>
      </div>
    </section>
  );
}
