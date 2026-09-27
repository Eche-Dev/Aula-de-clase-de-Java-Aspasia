import { Outlet, Link, NavLink } from "react-router-dom";
import { useTheme } from "./theme";
import { useAuth } from "../features/auth/AuthContext";
import { useUnreadCount } from "../features/messages/useUnreadCount";

export function AppLayout() {
  const { theme, toggle } = useTheme();
  const { isAuthenticated, mustChange, logout, user } = useAuth();
  const isAdmin = user?.role === "org_admin";
  const isTeacher = user?.role === "teacher";
  const isStudent = user?.role === "student";
  const isSuperAdmin = user?.role === "super_admin";
  const unread = useUnreadCount();
  const unreadTotal = unread.data?.total ?? 0;

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="text-lg font-semibold text-primary">
            Aula Virtual
          </Link>
          <nav className="flex flex-wrap items-center gap-3 text-sm">
            {isAuthenticated && !mustChange ? (
              <>
                {isSuperAdmin ? (
                  <NavLink
                    to="/plataforma"
                    className={({ isActive }) =>
                      isActive ? "text-primary underline" : "text-muted hover:text-text"
                    }
                  >
                    Plataforma
                  </NavLink>
                ) : null}
                {isSuperAdmin ? null : (
                  <>
                    <NavLink
                      to="/courses"
                      className={({ isActive }) =>
                        isActive ? "text-primary underline" : "text-muted hover:text-text"
                      }
                    >
                      Cursos
                    </NavLink>
                    <NavLink
                      to="/calendar"
                      className={({ isActive }) =>
                        isActive ? "text-primary underline" : "text-muted hover:text-text"
                      }
                    >
                      Calendario
                    </NavLink>
                    <NavLink
                      to="/messages"
                      className={({ isActive }) =>
                        isActive ? "text-primary underline" : "text-muted hover:text-text"
                      }
                    >
                      Mensajes
                      {unreadTotal > 0 ? (
                        <span
                          className="ml-1 rounded-full bg-primary px-1.5 py-0.5 text-xs font-medium text-white"
                          aria-label={`${unreadTotal} mensajes sin leer`}
                        >
                          {unreadTotal}
                        </span>
                      ) : null}
                    </NavLink>
                  </>
                )}
                <NavLink
                  to="/account"
                  className={({ isActive }) =>
                    isActive ? "text-primary underline" : "text-muted hover:text-text"
                  }
                >
                  Mi cuenta
                </NavLink>
                <NavLink
                  to="/account/privacy"
                  className={({ isActive }) =>
                    isActive ? "text-primary underline" : "text-muted hover:text-text"
                  }
                >
                  Privacidad
                </NavLink>
                {isTeacher ? (
                  <NavLink
                    to="/teacher"
                    className={({ isActive }) =>
                      isActive ? "text-primary underline" : "text-muted hover:text-text"
                    }
                  >
                    Panel
                  </NavLink>
                ) : null}
                {isStudent ? (
                  <NavLink
                    to="/student"
                    className={({ isActive }) =>
                      isActive ? "text-primary underline" : "text-muted hover:text-text"
                    }
                  >
                    Panel
                  </NavLink>
                ) : null}
                {isAdmin ? (
                  <NavLink
                    to="/admin"
                    className={({ isActive }) =>
                      isActive ? "text-primary underline" : "text-muted hover:text-text"
                    }
                  >
                    Admin
                  </NavLink>
                ) : null}
                <button
                  type="button"
                  onClick={logout}
                  className="rounded-md border border-border px-3 py-1.5 hover:bg-bg"
                >
                  Salir
                </button>
              </>
            ) : isAuthenticated ? null : (
              <>
                <Link
                  to="/precios"
                  className="rounded-md border border-border px-3 py-1.5 hover:bg-bg"
                >
                  Precios
                </Link>
                <Link
                  to="/login"
                  className="rounded-md border border-border px-3 py-1.5 hover:bg-bg"
                >
                  Entrar
                </Link>
              </>
            )}
            <button
              type="button"
              onClick={toggle}
              className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-bg"
              aria-pressed={theme === "dark"}
            >
              {theme === "dark" ? "Modo claro" : "Modo oscuro"}
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
