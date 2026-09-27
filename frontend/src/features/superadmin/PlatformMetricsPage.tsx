import { useQuery } from "@tanstack/react-query";
import { apiGet, type PlatformMetrics } from "../../lib/api";
import { ErrorState } from "../../components/ui/ErrorState";
import { Spinner } from "../../components/ui/Spinner";

function CounterList({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data);
  return (
    <article className="rounded-lg border border-border bg-surface p-4">
      <h2 className="font-semibold">{title}</h2>
      {entries.length === 0 ? (
        <p className="mt-2 text-sm text-muted">Sin datos todavía.</p>
      ) : (
        <dl className="mt-2 space-y-1 text-sm">
          {entries.map(([key, value]) => (
            <div key={key} className="flex justify-between gap-3">
              <dt className="text-muted">{key}</dt>
              <dd className="font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </article>
  );
}

export function PlatformMetricsPage() {
  const metrics = useQuery({
    queryKey: ["superadmin-metrics"],
    queryFn: ({ signal }) => apiGet<PlatformMetrics>("/superadmin/metrics", signal),
  });

  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Métricas de la plataforma</h1>
        <p className="mt-1 text-sm text-muted">
          Agregados de negocio. Sin datos académicos de ningún cliente (compromiso de producto).
        </p>
      </div>

      {metrics.isPending ? <Spinner label="Cargando métricas" /> : null}
      {metrics.isError ? (
        <ErrorState
          message="No se pudieron cargar las métricas."
          onRetry={() => void metrics.refetch()}
        />
      ) : null}

      {metrics.isSuccess ? (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <article className="rounded-lg border border-border bg-surface p-4">
              <p className="text-xs uppercase tracking-wide text-muted">Cursos totales</p>
              <p className="mt-1 text-3xl font-bold">{metrics.data.total_courses}</p>
            </article>
            <article className="rounded-lg border border-border bg-surface p-4">
              <p className="text-xs uppercase tracking-wide text-muted">
                Trials que acaban en 7 días
              </p>
              <p className="mt-1 text-3xl font-bold">{metrics.data.trials_ending_soon}</p>
            </article>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <CounterList title="Organizaciones por estado" data={metrics.data.orgs_by_status} />
            <CounterList title="Organizaciones por plan" data={metrics.data.orgs_by_plan} />
            <CounterList title="Usuarios por rol" data={metrics.data.users_by_role} />
          </div>
        </>
      ) : null}
    </section>
  );
}
