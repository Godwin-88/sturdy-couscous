export default function MetricGrid({ items }: { items: [string, string][] }) {
  return (
    <div className="metric-grid">
      {items.map(([label, value]) => (
        <div className="metric" key={label}>
          <span className="metric-label">{label}</span>
          <span className="metric-value">{value}</span>
        </div>
      ))}
    </div>
  );
}