import { HashRouter, Route, Routes } from "react-router-dom";
import Nav from "./components/Nav";
import Dashboard from "./pages/Dashboard";
import RateLimiterConfig from "./pages/RateLimiterConfig";
import DosSimulator from "./pages/DosSimulator";

export default function App() {
  return (
    <HashRouter>
      <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
        <Nav />
        <main className="mx-auto max-w-6xl px-6 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/config" element={<RateLimiterConfig />} />
            <Route path="/simulator" element={<DosSimulator />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  );
}
