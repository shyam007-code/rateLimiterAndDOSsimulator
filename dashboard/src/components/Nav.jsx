import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/config", label: "Rate Limiter Config" },
  { to: "/simulator", label: "DoS Simulator" },
];

export default function Nav() {
  return (
    <nav className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="mx-auto flex max-w-6xl items-center gap-1 px-6 py-3">
        <span className="mr-6 text-sm font-semibold tracking-wide text-[var(--text)]">
          Rate Limiter Lab
        </span>
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                isActive
                  ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                  : "text-[var(--text-dim)] hover:text-[var(--text)]"
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
