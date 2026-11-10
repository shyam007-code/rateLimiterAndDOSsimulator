export default function StatCard({ label, value, tone = "default", sub }) {
  const toneClass =
    {
      default: "text-[var(--text)]",
      good: "text-[var(--good)]",
      bad: "text-[var(--bad)]",
      warn: "text-[var(--warn)]",
    }[tone] || "text-[var(--text)]";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4">
      <div className="text-xs uppercase tracking-wide text-[var(--text-dim)]">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${toneClass}`}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-[var(--text-dim)]">{sub}</div>}
    </div>
  );
}
