import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AppRoutes } from "../../app/routes";
import { ThemeProvider } from "../../app/theme";
import { AuthProvider } from "../auth/AuthContext";
import { homePathAfterLogin } from "../auth/homePath";

function renderRoutes(initialEntries: string[]) {
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

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function authAs(role: "teacher" | "student" | "org_admin", pending = 2) {
  const name = role === "teacher" ? "Profe" : role === "org_admin" ? "Admin" : "Ana";
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes("/auth/me"))
        return Promise.resolve(
          json({
            id: 1,
            name,
            email: `${role}@aula.test`,
            username: role === "student" ? "ana" : null,
            role,
            is_active: true,
            must_change_credentials: false,
            created_at: new Date().toISOString(),
          }),
        );
      if (url.includes("/student/dashboard"))
        return Promise.resolve(
          json({
            totals: {
              courses_count: 1,
              pending_submissions: 2,
              due_this_week: 1,
              graded_submissions: 1,
            },
            courses: [
              {
                id: 1,
                name: "Java",
                code: "JAVA",
                status: "active",
                pending: 2,
                next_due_at: "2026-10-01T10:00:00Z",
              },
            ],
            upcoming: [
              {
                course_id: 1,
                course_name: "Java",
                assignment_id: 9,
                title: "Tarea 9",
                due_at: "2026-10-01T10:00:00Z",
              },
            ],
            recent: [
              {
                course_id: 1,
                course_name: "Java",
                assignment_id: 9,
                assignment_title: "Tarea 9",
                score: 87.5,
                evaluated_at: "2026-09-24T10:00:00Z",
              },
            ],
            pending_items: [
              {
                course_id: 1,
                course_name: "Java",
                assignment_id: 9,
                title: "Tarea 9",
                due_at: "2026-10-01T10:00:00Z",
              },
            ],
          }),
        );
      if (url.includes("/student/pending-count")) return Promise.resolve(json({ pending }));
      return Promise.resolve(json({ total: 0 }));
    }),
  );
}

function tokenWithRole(role: string): string {
  return `header.${btoa(JSON.stringify({ role }))}.signature`;
}

describe("Fase S0 — estructura del panel del alumno", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem("aula.access_token", "session-token");
    localStorage.setItem("aula.must_change", "0");
  });

  it("el student ve el layout con sus secciones", async () => {
    authAs("student");
    renderRoutes(["/student"]);

    expect(await screen.findByRole("heading", { name: /panel del alumno/i })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: /panel del alumno/i });
    expect(within(nav).getByRole("link", { name: /inicio/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /mis cursos/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /calendario/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /mensajes/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /mi cuenta/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cerrar sesión/i })).toBeInTheDocument();
  });

  it("un teacher es redirigido fuera del panel del alumno", async () => {
    authAs("teacher");
    renderRoutes(["/student"]);

    expect(
      await screen.findByRole("heading", { name: /plataforma de aula virtual/i }),
    ).toBeInTheDocument();
  });

  it("un admin supera el guard", async () => {
    authAs("org_admin");
    renderRoutes(["/student"]);

    expect(await screen.findByRole("heading", { name: /panel del alumno/i })).toBeInTheDocument();
  });

  it("el enlace Panel del alumno aparece en la nav global", async () => {
    authAs("student");
    renderRoutes(["/student"]);

    expect(await screen.findByRole("link", { name: "Panel" })).toBeInTheDocument();
  });
});

describe("Fase S1 — dashboard del alumno", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem("aula.access_token", "session-token");
    localStorage.setItem("aula.must_change", "0");
  });

  it("muestra KPIs, cursos, próximas entregas y evaluaciones", async () => {
    authAs("student");
    renderRoutes(["/student"]);

    expect(await screen.findByRole("heading", { name: /panel del alumno/i })).toBeInTheDocument();
    expect(screen.getByText("Fechas esta semana")).toBeInTheDocument();
    expect(screen.getByText("Evaluadas")).toBeInTheDocument();
    expect(screen.getAllByText("Mis cursos").length).toBeGreaterThan(1);
    expect(screen.getAllByText("Por entregar").length).toBeGreaterThan(1);
    expect(screen.getByText("Evaluaciones recientes")).toBeInTheDocument();
    expect(screen.getAllByText("Tarea 9").length).toBeGreaterThan(1);
    expect(screen.getByText("87.5")).toBeInTheDocument();
    expect((await screen.findAllByText("Java")).length).toBeGreaterThan(0);
    const courseLink = screen.getByRole("link", { name: /2 por entregar/i });
    expect(courseLink).toHaveAttribute("href", "/student/courses/1");
  });

  it("muestra estado vacío si no hay cursos matriculados", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/auth/me"))
          return Promise.resolve(
            json({
              id: 1,
              name: "Ana",
              email: "student@aula.test",
              username: "ana",
              role: "student",
              is_active: true,
              must_change_credentials: false,
              created_at: new Date().toISOString(),
            }),
          );
        if (url.includes("/student/dashboard"))
          return Promise.resolve(
            json({
              totals: {
                courses_count: 0,
                pending_submissions: 0,
                due_this_week: 0,
                graded_submissions: 0,
              },
              courses: [],
              upcoming: [],
              recent: [],
              pending_items: [],
            }),
          );
        if (url.includes("/student/pending-count")) return Promise.resolve(json({ pending: 0 }));
        return Promise.resolve(json({ total: 0 }));
      }),
    );
    renderRoutes(["/student"]);

    expect(await screen.findByText("Sin cursos matriculados")).toBeInTheDocument();
    expect(screen.getByText("Nada por entregar")).toBeInTheDocument();
    expect(screen.getByText("Sin evaluaciones")).toBeInTheDocument();
  });
});

describe("Fase S2 — badge y pendientes", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem("aula.access_token", "session-token");
    localStorage.setItem("aula.must_change", "0");
  });

  it("muestra el badge de entregas por entregar en la navegación", async () => {
    authAs("student");
    renderRoutes(["/student"]);

    expect(await screen.findByLabelText("2 entregas por entregar")).toBeInTheDocument();
  });

  it("la sección Por entregar enlaza a cada tarea", async () => {
    authAs("student");
    renderRoutes(["/student"]);

    const link = await screen.findByRole("link", { name: /tarea 9/i });
    expect(link).toHaveAttribute("href", "/courses/1/work/9");
  });

  it("no muestra badge cuando no hay pendientes", async () => {
    authAs("student", 0);
    renderRoutes(["/student"]);

    expect(await screen.findByRole("heading", { name: /panel del alumno/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/entregas por entregar/i)).not.toBeInTheDocument();
  });
});

describe("Fase S3 — mi progreso por curso", () => {
  const progress = {
    course_id: 1,
    course_name: "Java",
    assignment_stats: [
      {
        assignment_id: 9,
        title: "Tarea 9",
        due_at: "2026-09-01T10:00:00Z",
        status: "reviewed",
        score: 87.5,
        submitted_at: "2026-08-30T10:00:00Z",
      },
      {
        assignment_id: 10,
        title: "Tarea 10",
        due_at: "2026-10-01T10:00:00Z",
        status: "draft",
        score: null,
        submitted_at: null,
      },
    ],
    summary: { total: 2, delivered: 1, pending: 1, average_score: 87.5, delivery_pct: 50 },
    attendance: { present: 5, late: 1, absent: 0, excused: 1, pct: 85.7 },
  };

  const courseList = [
    {
      id: 1,
      name: "Java",
      code: "JAVA",
      description: "Curso de Java",
      status: "active",
      layout_rows: 3,
      layout_cols: 5,
    },
  ];

  function authMe(role: string) {
    return json({
      id: 1,
      name: role === "student" ? "Ana" : "Profe",
      email: `${role}@aula.test`,
      username: role === "student" ? "ana" : null,
      role,
      is_active: true,
      must_change_credentials: false,
      created_at: new Date().toISOString(),
    });
  }

  function mockFetch(options: { progressStatus?: number; role?: string } = {}) {
    const { progressStatus = 200, role = "student" } = options;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/auth/me")) return Promise.resolve(authMe(role));
        if (url.includes("/student/pending-count")) return Promise.resolve(json({ pending: 1 }));
        if (url.includes("/my-progress"))
          return Promise.resolve(
            progressStatus === 200
              ? json(progress)
              : new Response("boom", { status: progressStatus }),
          );
        if (url.includes("/courses")) return Promise.resolve(json(courseList));
        return Promise.resolve(json({ total: 0 }));
      }),
    );
  }

  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem("aula.access_token", "session-token");
    localStorage.setItem("aula.must_change", "0");
  });

  it("muestra resumen, asistencia y estado por tarea", async () => {
    mockFetch();
    renderRoutes(["/student/courses/1"]);

    expect(await screen.findByRole("heading", { level: 1, name: "Java" })).toBeInTheDocument();
    expect(screen.getByText("Mi progreso")).toBeInTheDocument();

    expect(screen.getByText("Entregadas")).toBeInTheDocument();
    expect(screen.getByText("1/2")).toBeInTheDocument();
    expect(screen.getByText("50% de entrega")).toBeInTheDocument();
    expect(screen.getByText("87.5")).toBeInTheDocument();
    expect(screen.getByText("85.7%")).toBeInTheDocument();

    expect(screen.getByText("Evaluada")).toBeInTheDocument();
    expect(screen.getByText("87.5 pts")).toBeInTheDocument();
    expect(screen.getByText("Borrador")).toBeInTheDocument();
    expect(
      screen.getByText(/5 presentes .*1 tardes .*0 faltas .*1 justificadas/),
    ).toBeInTheDocument();

    const taskLink = screen.getByRole("link", { name: "Tarea 9" });
    expect(taskLink).toHaveAttribute("href", "/courses/1/work/9");
    expect(screen.getByRole("link", { name: /ir al aula/i })).toHaveAttribute("href", "/courses/1");
    expect(screen.getByRole("link", { name: /ver tareas/i })).toHaveAttribute(
      "href",
      "/courses/1/work",
    );
  });

  it("muestra error si no se puede cargar el progreso", async () => {
    mockFetch({ progressStatus: 500 });
    renderRoutes(["/student/courses/1"]);

    expect(await screen.findByText("No se pudo cargar tu progreso")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
  });

  it("enlaza Mi progreso desde Mis cursos solo para students", async () => {
    mockFetch({ role: "student" });
    renderRoutes(["/courses"]);

    const link = await screen.findByRole("link", { name: /mi progreso/i });
    expect(link).toHaveAttribute("href", "/student/courses/1");
  });

  it("no muestra Mi progreso en Mis cursos para teachers", async () => {
    mockFetch({ role: "teacher" });
    renderRoutes(["/courses"]);

    expect(await screen.findByRole("heading", { name: "Mis cursos" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /mi progreso/i })).not.toBeInTheDocument();
  });
});

describe("Fase S4 — guards de rutas staff", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem("aula.access_token", "session-token");
    localStorage.setItem("aula.must_change", "0");
  });

  const staffPaths = [
    "/courses/1/evaluate",
    "/courses/1/attendance",
    "/courses/1/rubrics",
    "/courses/1/gradebook",
  ];

  it.each(staffPaths)("redirige al panel cuando un student visita %s", async (path) => {
    authAs("student");
    renderRoutes([path]);

    expect(await screen.findByRole("heading", { name: /panel del alumno/i })).toBeInTheDocument();
  });

  it("permite al teacher abrir Evaluar entregas", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/auth/me"))
          return Promise.resolve(
            json({
              id: 2,
              name: "Profe",
              email: "teacher@aula.test",
              username: null,
              role: "teacher",
              is_active: true,
              must_change_credentials: false,
              created_at: new Date().toISOString(),
            }),
          );
        if (url.includes("/submissions")) return Promise.resolve(json([]));
        if (url.includes("/rubrics")) return Promise.resolve(json([]));
        return Promise.resolve(json({ total: 0 }));
      }),
    );
    renderRoutes(["/courses/1/evaluate"]);

    expect(await screen.findByRole("heading", { name: "Evaluar entregas" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /panel del alumno/i })).not.toBeInTheDocument();
  });

  function mockClassroom(role: string) {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/auth/me"))
          return Promise.resolve(
            json({
              id: 1,
              name: role === "student" ? "Ana" : "Profe",
              email: `${role}@aula.test`,
              username: role === "student" ? "ana" : null,
              role,
              is_active: true,
              must_change_credentials: false,
              created_at: new Date().toISOString(),
            }),
          );
        if (url.includes("/classroom"))
          return Promise.resolve(
            json({
              course: {
                id: 1,
                name: "Java",
                code: "JAVA",
                description: "",
                status: "active",
                layout_rows: 2,
                layout_cols: 2,
              },
              seats: [],
              rows: 2,
              cols: 2,
              teachers: [{ id: 2, name: "Profe" }],
            }),
          );
        return Promise.resolve(json({ total: 0 }));
      }),
    );
  }

  it("oculta Asistencia y Rúbricas en el aula para students", async () => {
    mockClassroom("student");
    renderRoutes(["/courses/1"]);

    expect(await screen.findByRole("heading", { level: 1, name: /Java/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir a entregas" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Asistencia" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Rúbricas" })).not.toBeInTheDocument();
  });

  it("muestra Asistencia y Rúbricas en el aula para teachers", async () => {
    mockClassroom("teacher");
    renderRoutes(["/courses/1"]);

    expect(await screen.findByRole("heading", { level: 1, name: /Java/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Asistencia" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Rúbricas" })).toBeInTheDocument();
  });
});

describe("homePathAfterLogin (D-S2)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("redirige a /student cuando el rol es student", () => {
    localStorage.setItem("aula.access_token", tokenWithRole("student"));
    expect(homePathAfterLogin()).toBe("/student");
  });

  it("redirige a /teacher cuando el rol es teacher", () => {
    localStorage.setItem("aula.access_token", tokenWithRole("teacher"));
    expect(homePathAfterLogin()).toBe("/teacher");
  });

  it("redirige a / cuando no hay token y a /admin con el rol org_admin", () => {
    expect(homePathAfterLogin()).toBe("/");
    localStorage.setItem("aula.access_token", tokenWithRole("org_admin"));
    expect(homePathAfterLogin()).toBe("/admin");
  });

  it("redirige a /plataforma con el rol super_admin (Fase D SaaS)", () => {
    localStorage.setItem("aula.access_token", tokenWithRole("super_admin"));
    expect(homePathAfterLogin()).toBe("/plataforma");
  });
});
