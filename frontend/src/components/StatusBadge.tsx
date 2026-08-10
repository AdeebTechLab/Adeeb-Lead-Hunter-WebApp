export default function StatusBadge({ value }: { value?: string | number | null }) {
  const text = String(value ?? '—')
  const tone = text.toLowerCase().replace(/\s+/g, '-')
  return <span className={`status-badge status-${tone}`}>{text}</span>
}
