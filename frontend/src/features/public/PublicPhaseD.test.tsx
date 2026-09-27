import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import { ThemeProvider } from "../../app/theme";
import { PreciosPage } from "./PreciosPage";
import { RegistroEmpresaPage } from "./RegistroEmpresaPage";
import { ActivarCuentaPage } from "./ActivarCuentaPage";
import { redirectToCheckout } from "../../lib/checkout";

vi.mock("../../lib/checkout", () => ({ redirectToCheckout: vi.fn() }));

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(ui: ReactNode, path = "/precios") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/precios" element={ui} />
            <Route path="/registro-empresa" element={ui} />
            <Route path="/activar-cuenta/:token" element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

const PLANS = [
  {
    id: "basic",
    name: "Básico",
    description: "Para centros pequeños",
    price_eur: 19,
    max_courses: 3,
    currency: "EUR",
    interval: "month",
  },
  {
    id: "growth",
    name: "Crecimiento",
    description: "Para centros en crecimiento",
    price_eur: 49,
    max_courses: null,
    currency: "EUR",
    interval: "month",
  },
];

describe("Fase D — páginas públicas", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("lista los planes en /precios con enlace de registro", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(json(PLANS))),
    );

    renderPage(<PreciosPage />);

    expect(await screen.findByText("Básico")).toBeInTheDocument();
    expect(screen.getByText("Crecimiento")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "Registra tu empresa" });
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "/registro-empresa?plan=basic",
      "/registro-empresa?plan=growth",
    ]);
    expect(screen.getByText(/14 días de prueba/)).toBeInTheDocument();
  });

  it("muestra error y reintentos si los planes no cargan", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(json({ detail: "boom" }, 500))),
    );

    renderPage(<PreciosPage />);

    expect(await screen.findByText("No se pudieron cargar los planes.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("registra la empresa y salta al checkout de Stripe", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/public/plans")) return Promise.resolve(json(PLANS));
      if (url.includes("/public/organizations"))
        return Promise.resolve(
          json({ organization_id: 7, checkout_url: "https://checkout.stripe.test/pay/cs_1" }),
        );
      return Promise.resolve(json({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage(<RegistroEmpresaPage />, "/registro-empresa");

    await user.type(screen.getByLabelText(/nombre de la empresa/i), "Dicampus S.L.");
    await user.type(screen.getByLabelText(/nif/i), "B12345678");
    await user.type(screen.getByLabelText(/email de facturación/i), "fact@dicampus.test");
    await user.selectOptions(screen.getByLabelText(/plan/i), "growth");
    await user.click(screen.getByRole("button", { name: /continuar al pago/i }));

    expect(await screen.findByText(/Redirigiendo a Stripe/)).toBeInTheDocument();
    expect(redirectToCheckout).toHaveBeenCalledWith("https://checkout.stripe.test/pay/cs_1");
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/public/organizations"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("preselecciona el plan que viene en la URL /registro-empresa?plan=…", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/public/plans")) return Promise.resolve(json(PLANS));
        return Promise.resolve(json({}));
      }),
    );

    renderPage(<RegistroEmpresaPage />, "/registro-empresa?plan=basic");

    // la opción llega con los planes; hasta entonces el select está vacío
    await screen.findByRole("option", { name: /básico/i });
    const select = screen.getByLabelText(/plan/i) as HTMLSelectElement;
    expect(select.value).toBe("basic");
  });

  it("explica el 409 (empresa duplicada) en el registro", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/public/plans")) return Promise.resolve(json(PLANS));
        if (url.includes("/public/organizations"))
          return Promise.resolve(json({ detail: "Conflict" }, 409));
        return Promise.resolve(json({}));
      }),
    );

    renderPage(<RegistroEmpresaPage />, "/registro-empresa");

    await user.type(screen.getByLabelText(/nombre de la empresa/i), "Dicampus S.L.");
    await user.type(screen.getByLabelText(/nif/i), "B12345678");
    await user.type(screen.getByLabelText(/email de facturación/i), "fact@dicampus.test");
    await user.selectOptions(screen.getByLabelText(/plan/i), "basic");
    await user.click(screen.getByRole("button", { name: /continuar al pago/i }));

    expect(
      await screen.findByText(/ya hay una organización registrada con ese email/i),
    ).toBeInTheDocument();
    expect(redirectToCheckout).not.toHaveBeenCalled();
  });

  it("muestra la cuenta y activa con el enlace de token válido", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes("/auth/activate?token=tok-ok"))
        return Promise.resolve(json({ email: "nueva@centro.test", expires_at: null }));
      if (url.includes("/auth/activate") && init?.method === "POST")
        return Promise.resolve(json({ status: "ok", email: "nueva@centro.test" }));
      return Promise.resolve(json({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage(<ActivarCuentaPage />, "/activar-cuenta/tok-ok");

    expect(await screen.findByText(/nueva@centro.test/)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/contraseña \(mínimo/i), "secreta-123");
    await user.type(screen.getByLabelText(/repite la contraseña/i), "secreta-123");
    await user.click(screen.getByRole("button", { name: /activar cuenta/i }));

    expect(await screen.findByRole("heading", { name: /cuenta activada/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ir a iniciar sesión/i })).toBeInTheDocument();
  });

  it("rechaza un enlace de activación caducado", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(json({ detail: "Token expired" }, 410))),
    );

    renderPage(<ActivarCuentaPage />, "/activar-cuenta/tok-viejo");

    expect(
      await screen.findByText(/el enlace de activación no es válido o ha caducado/i),
    ).toBeInTheDocument();
  });
});
