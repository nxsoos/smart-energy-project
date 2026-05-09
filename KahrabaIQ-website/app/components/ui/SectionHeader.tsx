export function SectionHeader({ label, title, subtitle, id }: { label: string; title: string; subtitle?: string; id: string }) {
  return (
    <header className="section-header">
      <p className="label">{label}</p>
      <h2 id={id}>{title}</h2>
      {subtitle && <p>{subtitle}</p>}
    </header>
  );
}
