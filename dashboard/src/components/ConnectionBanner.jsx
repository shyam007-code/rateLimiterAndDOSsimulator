export default function ConnectionBanner({ error, serviceName, url }) {
  if (!error) return null;
  return (
    <div className="mb-4 rounded-lg border border-[var(--bad)]/40 bg-[var(--bad)]/10 px-4 py-3 text-sm text-[var(--bad)]">
      Can't reach the {serviceName} at <code className="font-mono">{url}</code>.
      Make sure it's running (
      <code className="font-mono">uvicorn app.main:app</code>) and reachable
      from this browser.
    </div>
  );
}
