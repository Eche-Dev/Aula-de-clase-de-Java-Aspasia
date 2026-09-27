/**
 * Destino tras iniciar sesión / cambiar credenciales (redirección por rol).
 * Cada rol tiene su panel: super_admin en /plataforma (Fase D SaaS),
 * org_admin en /admin, teacher en /teacher (D-T2) y student en /student (D-S2).
 */
function roleFromAccessToken(): string | null {
  const token = localStorage.getItem("aula.access_token");
  if (!token) return null;
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const json = JSON.parse(atob(base64)) as { role?: string };
    return json.role ?? null;
  } catch {
    return null;
  }
}

export function homePathAfterLogin(): string {
  const role = roleFromAccessToken();
  if (role === "super_admin") return "/plataforma";
  if (role === "teacher") return "/teacher";
  if (role === "student") return "/student";
  if (role === "org_admin") return "/admin";
  return "/";
}
