import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { useLiveSocket } from "./useLiveSocket";
import { useState } from "react";

const NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/inventory", label: "Inventory" },
  { to: "/storage", label: "Storage" },
  { to: "/suppliers", label: "Suppliers" },
  { to: "/incidents", label: "Alerts" },
  { to: "/label-scanner", label: "Label Scanner" },
];

export default function Layout() {
  const { logout, role } = useAuth();
  const [toast, setToast] = useState<string | null>(null);

  const { connected } = useLiveSocket((e) => {
    if (e.type === "SCENARIO_STARTED") setToast(`Simulating "${e.scenario}"...`);
    if (e.type === "SCENARIO_COMPLETE") {
      setToast(`Scenario "${e.scenario}" complete — dashboard updated live.`);
      window.setTimeout(() => setToast(null), 4000);
      window.dispatchEvent(new CustomEvent("fg:refresh"));
    }
    if (e.type === "SCENARIO_FAILED") setToast(`Scenario failed: ${e.error?.slice(0, 100)}`);
  });

  return (
    <div className="min-h-screen bg-stone-100">
      <header className="bg-white border-b border-stone-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <span className="font-semibold text-stone-900">FoodGuard</span>
          <nav className="flex gap-4 text-sm">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `px-2 py-1 rounded ${isActive ? "bg-emerald-100 text-emerald-800" : "text-stone-600 hover:text-stone-900"}`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className={`flex items-center gap-1.5 ${connected ? "text-emerald-700" : "text-stone-400"}`}>
            <span className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-500" : "bg-stone-300"}`} />
            {connected ? "Live" : "Reconnecting…"}
          </span>
          <span className="text-stone-500">{role}</span>
          <button onClick={logout} className="text-stone-500 hover:text-stone-800">
            Sign out
          </button>
        </div>
      </header>

      {toast && (
        <div className="bg-emerald-700 text-white text-sm px-6 py-2 text-center">{toast}</div>
      )}

      <main className="p-6 max-w-7xl mx-auto">
        <Outlet />
      </main>
    </div>
  );
}
