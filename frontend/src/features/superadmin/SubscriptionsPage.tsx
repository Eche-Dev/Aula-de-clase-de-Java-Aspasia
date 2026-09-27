import { useQuery } from "@tanstack/react-query";
import { apiGet, type SubscriptionRow } from "../../lib/api";
import { ErrorState } from "../../components/ui/ErrorState";
import { Spinner } from "../../components/ui/Spinner";

export function SubscriptionsPage() {
  const subs = useQuery({
    queryKey: ["superadmin-subs"],
    queryFn: ({ signal }) => apiGet<SubscriptionRow[]>("/superadmin/subscriptions", signal),
  });

  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Suscripciones</h1>
        <p className="mt-1 text-sm text-muted">
          Estado de la facturación de cada cliente (fuente de verdad: Stripe).
        </p>
      </div>

      {subs.isPending ? <Spinner label="Cargando suscripciones" /> : null}
      {subs.isError ? (
        <ErrorState
          message="No se pudieron cargar las suscripciones."
          onRetry={() => void subs.refetch()}
        />
      ) : null}

      {subs.isSuccess ? (
        subs.data.length === 0 ? (
          <p className="text-sm text-muted">Todavía no hay suscripciones.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted">
                  <th className="py-2 pr-3">Org</th>
                  <th className="py-2 pr-3">Cliente</th>
                  <th className="py-2 pr-3">Suscripción</th>
                  <th className="py-2 pr-3">Estado</th>
                  <th className="py-2 pr-3">Plan</th>
                  <th className="py-2">Trial termina</th>
                </tr>
              </thead>
              <tbody>
                {subs.data.map((row) => (
                  <tr key={row.organization_id} className="border-b border-border">
                    <td className="py-2 pr-3">
                      <span className="font-medium">{row.organization_name}</span>
                      <span className="block font-mono text-xs text-muted">
                        #{row.organization_id}
                      </span>
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{row.stripe_customer_id ?? "—"}</td>
                    <td className="py-2 pr-3 font-mono text-xs">
                      {row.stripe_subscription_id ?? "—"}
                    </td>
                    <td className="py-2 pr-3">{row.status}</td>
                    <td className="py-2 pr-3">{row.plan_id || "—"}</td>
                    <td className="py-2">
                      {row.trial_ends_at ? new Date(row.trial_ends_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}
    </section>
  );
}
