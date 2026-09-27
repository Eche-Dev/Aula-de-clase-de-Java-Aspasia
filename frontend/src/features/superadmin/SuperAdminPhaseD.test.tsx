import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import { ThemeProvider } from "../../app/theme";
import { AuthProvider } from "../auth/AuthContext";
import { AppRoutes } from "../../app/routes";
import { PlatformAccessPage } from "./PlatformAccessPage";
import { MfaSettingsPage } from "./MfaSettingsPage";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function superAdminUser(mfaEnabled = true) {
  return {
    id: 1,
    name: "Dueña Plataforma",
    email: "root@aspasia.test",
    username: null,
    role: "super_admin",
    is_active: true,
    must_change_credentials: false,
    mfa_enabled: mfaEnabled,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function renderPage(ui: ReactNode, path = "/plataforma/acceso") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <AuthProvider>
            <Routes>
              <Route path="/plataforma/acceso" element={ui} />
              <Route path="/plataforma/2fa" element={ui} />
              <Route path="/plataforma" element={<h1>Panel de la plataforma</h1>} />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

function renderAppRoutes(initialEntries: string[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

type AccessFetchOptions = { enrolled: boolean; verifyOk?: boolean };

function accessFetch(options: AccessFetchOptions) {
  return vi.fn((url: string) => {
    if (url.includes("/auth/login/staff"))
      return Promise.resolve(
        json({
          access_token: "",
          token_type: "bearer",
          must_change_credentials: false,
          mfa_required: true,
          mfa_token: "mfa-token-1",
          mfa_enrolled: options.enrolled,
        }),
      );
    if (url.includes("/auth/mfa/setup"))
      return Promise.resolve(
        json({
          secret: "JBSWY3DPEHPK3PXP",
          otpauth_url: "otpauth://totp/Aspasia:root?secret=JBSWY3DPEHPK3PXP&issuer=Aspasia",
          mfa_enabled: false,
        }),
      );
    if (url.includes("/auth/mfa/verify")) {
      if (options.verifyOk === false)
        return Promise.resolve(json({ detail: "Invalid authentication code" }, 401));
      return Promise.resolve(
        json({
          mfa_enabled: true,
          access_token: "real-token",
          token_type: "bearer",
          must_change_credentials: false,
        }),
      );
    }
    if (url.includes("/auth/me")) return Promise.resolve(json(superAdminUser()));
    return Promise.resolve(json({}));
  });
}

async function fillPassword(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/email/i), "root@aspasia.test");
  await user.type(screen.getByLabelText(/contraseña/i), "fuerte-pass-1");
  await user.click(screen.getByRole("button", { name: "Continuar" }));
}

describe("Fase D — acceso 2FA de la plataforma", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("con 2FA ya activo exige el código y entra sin montar el setup", async () => {
    const user = userEvent.setup();
    const fetchMock = accessFetch({ enrolled: true });
    vi.stubGlobal("fetch", fetchMock);

    renderPage(<PlatformAccessPage />);

    await fillPassword(user);
    expect(await screen.findByText(/aplicación authenticator/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/auth/mfa/setup"),
      expect.anything(),
    );

    await user.type(screen.getByLabelText(/código de 6 dígitos/i), "123456");
    await user.click(screen.getByRole("button", { name: /verificar y entrar/i }));

    expect(
      await screen.findByRole("heading", { name: /panel de la plataforma/i }),
    ).toBeInTheDocument();
    expect(localStorage.getItem("aula.access_token")).toBe("real-token");
  });

  it("la primera vez muestra el secreto y lo activa con el primer código", async () => {
    const user = userEvent.setup();
    const fetchMock = accessFetch({ enrolled: false });
    vi.stubGlobal("fetch", fetchMock);

    renderPage(<PlatformAccessPage />);

    await fillPassword(user);

    expect(await screen.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    expect(screen.getByText(/otpauth:\/\/totp\//)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/auth/mfa/setup"),
      expect.objectContaining({ method: "POST" }),
    );

    await user.type(screen.getByLabelText(/código de 6 dígitos/i), "123456");
    await user.click(screen.getByRole("button", { name: /verificar y entrar/i }));

    expect(
      await screen.findByRole("heading", { name: /panel de la plataforma/i }),
    ).toBeInTheDocument();
    expect(localStorage.getItem("aula.access_token")).toBe("real-token");
  });

  it("un código incorrecto no abre sesión", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", accessFetch({ enrolled: true, verifyOk: false }));

    renderPage(<PlatformAccessPage />);

    await fillPassword(user);
    await user.type(screen.getByLabelText(/código de 6 dígitos/i), "000000");
    await user.click(screen.getByRole("button", { name: /verificar y entrar/i }));

    expect(await screen.findByText("Invalid authentication code")).toBeInTheDocument();
    expect(localStorage.getItem("aula.access_token")).toBeNull();
    expect(screen.getByRole("heading", { name: /acceso de la plataforma/i })).toBeInTheDocument();
  });
});

describe("Fase D — panel de la plataforma", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem("aula.access_token", "sa-token");
    localStorage.setItem("aula.must_change", "0");
  });

  it("muestra las métricas a la dueña de la plataforma", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/auth/me")) return Promise.resolve(json(superAdminUser()));
        if (url.includes("/superadmin/metrics"))
          return Promise.resolve(
            json({
              orgs_by_status: { active: 4, trialing: 2 },
              orgs_by_plan: { growth: 3, basic: 3 },
              users_by_role: { super_admin: 1, org_admin: 5, teacher: 8, student: 40 },
              total_courses: 12,
              trials_ending_soon: 1,
            }),
          );
        if (url.includes("/messages/unread-count"))
          return Promise.resolve(json({ private: 0, courses: {}, total: 0 }));
        return Promise.resolve(json({}));
      }),
    );

    renderAppRoutes(["/plataforma"]);

    expect(
      await screen.findByRole("heading", { name: /métricas de la plataforma/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Cursos totales")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Trials que acaban en 7 días")).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: /secciones de la plataforma/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Cursos")).not.toBeInTheDocument();
  });

  it("protege /plataforma: un org_admin redirige al inicio", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/auth/me"))
          return Promise.resolve(json({ ...superAdminUser(), role: "org_admin" }));
        if (url.includes("/superadmin/metrics"))
          return Promise.resolve(
            json({
              orgs_by_status: {},
              orgs_by_plan: {},
              users_by_role: {},
              total_courses: 0,
              trials_ending_soon: 0,
            }),
          );
        if (url.includes("/health"))
          return Promise.resolve(
            json({
              status: "ok",
              app: "AulaVirtual",
              version: "0.1.0",
              time: "2026-09-28T00:00:00Z",
            }),
          );
        if (url.includes("/messages/unread-count"))
          return Promise.resolve(json({ private: 0, courses: {}, total: 0 }));
        return Promise.resolve(json({}));
      }),
    );

    renderAppRoutes(["/plataforma"]);

    expect(
      await screen.findByRole("heading", { name: /plataforma de aula virtual/i }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText("Métricas de la plataforma")).not.toBeInTheDocument();
    });
  });

  it("lista las organizaciones y borra con confirmación en dos pasos", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/auth/me")) return Promise.resolve(json(superAdminUser()));
      if (url.includes("/superadmin/organizations"))
        return Promise.resolve(
          json([
            {
              id: 3,
              name: "Dicampus S.L.",
              tax_id: "B12345678",
              billing_email: "fact@dicampus.test",
              status: "active",
              plan_id: "growth",
              stripe_customer_id: "cus_1",
              stripe_subscription_id: "sub_1",
              trial_ends_at: null,
              created_at: "2026-09-01T00:00:00Z",
              user_count: 6,
              course_count: 2,
            },
          ]),
        );
      if (url.includes("/messages/unread-count"))
        return Promise.resolve(json({ private: 0, courses: {}, total: 0 }));
      return Promise.resolve(json({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAppRoutes(["/plataforma/organizaciones"]);

    expect(await screen.findByText("Dicampus S.L.")).toBeInTheDocument();
    expect(screen.getByText("fact@dicampus.test")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Borrar" }));
    await user.click(screen.getByRole("button", { name: /¿seguro\?/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/superadmin/organizations/3"),
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("permite gestionar el 2FA desde su sección", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/auth/me")) return Promise.resolve(json(superAdminUser(true)));
      if (url.includes("/auth/mfa/setup"))
        return Promise.resolve(
          json({
            secret: "KRSXG5CTMVRXEZLU",
            otpauth_url: "otpauth://totp/Aspasia:root?secret=KRSXG5CTMVRXEZLU",
            mfa_enabled: false,
          }),
        );
      if (url.includes("/auth/mfa/verify"))
        return Promise.resolve(
          json({
            mfa_enabled: true,
            access_token: null,
            token_type: "bearer",
            must_change_credentials: null,
          }),
        );
      if (url.includes("/auth/mfa/disable")) return new Response(null, { status: 204 });
      return Promise.resolve(json({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage(<MfaSettingsPage />, "/plataforma/2fa");

    expect(await screen.findByText(/estado:/i)).toBeInTheDocument();
    expect(screen.getByText("Activado")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/código de 6 dígitos/i), "654321");
    await user.click(screen.getByRole("button", { name: /desactivar 2fa/i }));

    expect(await screen.findByText(/segundo factor desactivado/i)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/auth/mfa/disable"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});
