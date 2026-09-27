import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AppRoutes } from "../app/routes";
import { ThemeProvider } from "../app/theme";
import { AuthProvider } from "../features/auth/AuthContext";

function renderRoutes(initialEntries: string[] = ["/"]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("AppRoutes", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("redirige al login si no hay sesión", async () => {
    renderRoutes(["/"]);
    expect(await screen.findByRole("heading", { name: /iniciar sesión/i })).toBeInTheDocument();
  });

  it("muestra la página de inicio autenticado", async () => {
    localStorage.setItem("aula.access_token", "test-token");
    localStorage.setItem("aula.must_change", "0");
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              status: "ok",
              app: "AulaVirtual",
              version: "0.1.0",
              time: new Date().toISOString(),
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
      ),
    );

    renderRoutes(["/"]);

    expect(
      screen.getByRole("heading", { name: /plataforma de aula virtual/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText("ok")).toBeInTheDocument();
  });

  it("muestra el formulario de login con pestañas", async () => {
    renderRoutes(["/login"]);
    expect(await screen.findByRole("tab", { name: "Estudiante" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Personal" })).toBeInTheDocument();
    expect(screen.getByLabelText(/código de curso/i)).toBeInTheDocument();
  });

  it("muestra 404 en rutas desconocidas", () => {
    localStorage.setItem("aula.access_token", "test-token");
    localStorage.setItem("aula.must_change", "0");
    renderRoutes(["/no-existe"]);
    expect(screen.getByRole("heading", { name: "404" })).toBeInTheDocument();
  });

  it("sirve /precios sin sesión", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify([
              {
                id: "basic",
                name: "Básico",
                description: "Para centros pequeños",
                price_eur: 19,
                max_courses: 3,
                currency: "EUR",
                interval: "month",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
      ),
    );

    renderRoutes(["/precios"]);

    expect(
      await screen.findByRole("heading", { name: /planes para tu centro/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Básico")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Entrar" })).toBeInTheDocument();
  });

  it("sirve /plataforma/acceso como pantalla propia del 2FA", () => {
    renderRoutes(["/plataforma/acceso"]);
    expect(screen.getByRole("heading", { name: /acceso de la plataforma/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
  });

  it("sirve /activar-cuenta/:token con su enlace de un solo uso", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ email: "nueva@centro.test", expires_at: null }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      ),
    );

    renderRoutes(["/activar-cuenta/token-abc"]);

    expect(await screen.findByRole("heading", { name: /crea tu contraseña/i })).toBeInTheDocument();
    expect(await screen.findByText(/nueva@centro\.test/)).toBeInTheDocument();
  });

  it("el login de super_admin exige el reto 2FA antes de crear sesión", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: "",
              token_type: "bearer",
              must_change_credentials: false,
              mfa_required: true,
              mfa_token: "mfa-token-x",
              mfa_enrolled: true,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
      ),
    );

    renderRoutes(["/login"]);

    await user.click(screen.getByRole("tab", { name: "Personal" }));
    await user.type(screen.getByLabelText(/email/i), "root@aspasia.test");
    await user.type(screen.getByLabelText(/contraseña/i), "fuerte-pass-1");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(
      await screen.findByRole("heading", { name: /acceso de la plataforma/i }),
    ).toBeInTheDocument();
    expect(localStorage.getItem("aula.access_token")).toBeNull();
  });
});
