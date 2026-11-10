export default function StatusPill({ ok, trueLabel, falseLabel }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium ${
        ok
          ? "border-[var(--good)]/40 bg-[var(--good)]/10 text-[var(--good)]"
          : "border-[var(--bad)]/40 bg-[var(--bad)]/10 text-[var(--bad)]"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-[var(--good)]" : "bg-[var(--bad)]"}`}
      />
      {ok ? trueLabel : falseLabel}
    </span>
  );
}
