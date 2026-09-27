import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiGet, type PlanPublic } from "../../lib/api";
import { ErrorState } from "../../components/ui/ErrorState";
import { Spinner } from "../../components/ui/Spinner";

export function PreciosPage() {
  const plans = useQuery({
    queryKey: ["plans"],
    queryFn: ({ signal }) => apiGet<PlanPublic[]>("/public/plans", signal),
  });

  return (
    <section className="mx-auto max-w-5xl space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold">Planes para tu centro</h1>
        <p className="mt-2 text-muted">
          Elige un plan y registra tu empresa. 14 días de prueba con tarjeta; no se cobra hasta que
          termine el trial.
        </p>
      </div>

      {plans.isPending ? <Spinner label="Cargando planes" /> : null}
      {plans.isError ? (
        <ErrorState
          message="No se pudieron cargar los planes."
          onRetry={() => void plans.refetch()}
        />
      ) : null}

      {plans.isSuccess ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {plans.data.map((plan) => (
            <article
              key={plan.id}
              className="flex flex-col rounded-lg border border-border bg-surface p-5"
            >
              <h2 className="text-lg font-semibold">{plan.name}</h2>
              <p className="mt-2 text-3xl font-bold">
                {plan.price_eur}€
                <span className="text-sm font-normal text-muted">/{plan.interval}</span>
              </p>
              <p className="mt-3 flex-1 text-sm text-muted">{plan.description}</p>
              <p className="mt-2 text-xs text-muted">
                {plan.max_courses === null
                  ? "Cursos ilimitados"
                  : `Hasta ${plan.max_courses} cursos activos`}
              </p>
              <Link
                to={`/registro-empresa?plan=${plan.id}`}
                className="mt-4 rounded-md bg-primary px-4 py-2 text-center text-sm font-medium text-white"
              >
                Registra tu empresa
              </Link>
            </article>
          ))}
        </div>
      ) : null}

      <p className="text-center text-sm text-muted">
        ¿Ya tienes cuenta?{" "}
        <Link to="/login" className="text-primary hover:underline">
          Inicia sesión
        </Link>
      </p>
    </section>
  );
}
