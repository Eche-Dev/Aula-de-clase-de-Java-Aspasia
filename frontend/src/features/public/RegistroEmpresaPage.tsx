import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ApiError,
  apiGet,
  apiSend,
  type OrganizationRegisterResponse,
  type PlanPublic,
} from "../../lib/api";
import { redirectToCheckout } from "../../lib/checkout";
import { ErrorState } from "../../components/ui/ErrorState";
import { Spinner } from "../../components/ui/Spinner";

const MESSAGES: Record<number, string> = {
  404: "El plan elegido no existe.",
  409: "Ya hay una organización registrada con ese email de facturación.",
  502: "Stripe no está disponible ahora mismo. Inténtalo de nuevo en unos minutos.",
  503: "La facturación con Stripe aún no está configurada en este entorno.",
};

export function RegistroEmpresaPage() {
  const [params] = useSearchParams();
  const plans = useQuery({
    queryKey: ["plans"],
    queryFn: ({ signal }) => apiGet<PlanPublic[]>("/public/plans", signal),
  });

  const [name, setName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [billingEmail, setBillingEmail] = useState("");
  const [planId, setPlanId] = useState(params.get("plan") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [redirecting, setRedirecting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const result = await apiSend<OrganizationRegisterResponse>("POST", "/public/organizations", {
        name: name.trim(),
        tax_id: taxId.trim(),
        billing_email: billingEmail.trim(),
        plan_id: planId,
      });
      setRedirecting(true);
      redirectToCheckout(result.checkout_url);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(MESSAGES[status] ?? (err instanceof Error ? err.message : "No se pudo registrar."));
    } finally {
      setPending(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-primary";

  if (redirecting) {
    return (
      <section className="mx-auto max-w-md space-y-4 text-center">
        <h1 className="text-2xl font-bold">Redirigiendo a Stripe…</h1>
        <p className="text-sm text-muted">
          Te llevamos al checkout seguro para añadir la tarjeta. La tarjeta se teclea siempre en
          Stripe, nunca aquí.
        </p>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-md space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Registra tu empresa</h1>
        <p className="mt-1 text-sm text-muted">
          Crearemos tu organización y te llevaremos al pago. Después recibirás un email para crear
          la contraseña de tu cuenta.
        </p>
      </div>

      {error ? <ErrorState message={error} /> : null}

      {plans.isPending ? <Spinner label="Cargando planes" /> : null}

      <form
        onSubmit={onSubmit}
        className="space-y-3 rounded-lg border border-border bg-surface p-4"
      >
        <label className="block space-y-1 text-sm">
          <span className="text-muted">Nombre de la empresa</span>
          <input
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={200}
            placeholder="Dicampus S.L."
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-muted">NIF / CIF</span>
          <input
            className={inputClass}
            value={taxId}
            onChange={(e) => setTaxId(e.target.value)}
            required
            maxLength={32}
            placeholder="B12345678"
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-muted">Email de facturación</span>
          <input
            className={inputClass}
            type="email"
            value={billingEmail}
            onChange={(e) => setBillingEmail(e.target.value)}
            required
            autoComplete="email"
            placeholder="facturacion@empresa.com"
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-muted">Plan</span>
          <select
            className={inputClass}
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
            required
          >
            <option value="" disabled>
              Elige un plan…
            </option>
            {(plans.data ?? []).map((plan) => (
              <option key={plan.id} value={plan.id}>
                {plan.name} — {plan.price_eur}€/mes
              </option>
            ))}
          </select>
        </label>

        <button
          type="submit"
          disabled={pending || !planId}
          className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {pending ? "Preparando el pago…" : "Continuar al pago"}
        </button>
      </form>

      <p className="text-center text-sm text-muted">
        <Link to="/precios" className="text-primary hover:underline">
          Ver los planes
        </Link>
      </p>
    </section>
  );
}
