import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-md px-3 py-2 text-sm transition ${
    isActive
      ? "bg-primary/10 font-medium text-primary"
      : "text-muted hover:bg-surface hover:text-text"
  }`;

export function SuperAdminLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
      <aside className="space-y-1 lg:sticky lg:top-4 lg:self-start">
        <div className="mb-3 rounded-lg border border-border bg-surface p-3">
          <p className="text-xs uppercase tracking-wide text-muted">Plataforma</p>
          <p className="truncate font-semibold">{user?.name ?? "Super admin"}</p>
          <p className="truncate text-xs text-muted">{user?.email}</p>
        </div>
        <nav aria-label="Secciones de la plataforma" className="flex flex-col gap-1">
          <NavLink to="/plataforma" end className={navClass}>
            <span aria-hidden>▦</span> Métricas
          </NavLink>
          <NavLink to="/plataforma/organizaciones" className={navClass}>
            <span aria-hidden>▤</span> Organizaciones
          </NavLink>
          <NavLink to="/plataforma/suscripciones" className={navClass}>
            <span aria-hidden>◷</span> Suscripciones
          </NavLink>
          <NavLink to="/plataforma/2fa" className={navClass}>
            <span aria-hidden>◈</span> Segundo factor
          </NavLink>
        </nav>
        <button
          type="button"
          onClick={logout}
          className="mt-4 w-full rounded-md border border-border px-3 py-2 text-sm hover:bg-bg"
        >
          Cerrar sesión
        </button>
      </aside>
      <div className="min-w-0">
        <Outlet />
      </div>
    </div>
  );
}
