import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet, apiSend, type ActivationDone, type ActivationInfo } from "../../lib/api";
import { ErrorState } from "../../components/ui/ErrorState";
import { Spinner } from "../../components/ui/Spinner";

export function ActivarCuentaPage() {
  const { token = "" } = useParams<{ token: string }>();
  const info = useQuery({
    queryKey: ["activation", token],
    queryFn: ({ signal }) =>
      apiGet<ActivationInfo>(`/auth/activate?token=${encodeURIComponent(token)}`, signal),
    retry: false,
    enabled: token.length > 0,
  });

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState<ActivationDone | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setPending(true);
    try {
      const result = await apiSend<ActivationDone>("POST", "/auth/activate", {
        token,
        password,
      });
      setDone(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo activar la cuenta.");
    } finally {
      setPending(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-primary";

  if (done) {
    return (
      <section className="mx-auto max-w-md space-y-4 text-center">
        <h1 className="text-2xl font-bold">Cuenta activada</h1>
        <p className="text-sm text-muted">
          La contraseña de <strong>{done.email}</strong> ya está creada. Ya puedes entrar con ella.
        </p>
        <Link
          to="/login"
          className="inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-white"
        >
          Ir a iniciar sesión
        </Link>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-md space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Crea tu contraseña</h1>
        <p className="mt-1 text-sm text-muted">
          Este enlace es de un solo uso y caduca a las 48 horas desde el email.
        </p>
      </div>

      {info.isPending ? <Spinner label="Comprobando el enlace" /> : null}

      {info.isError ? (
        <ErrorState message="El enlace de activación no es válido o ha caducado. Pide uno nuevo a la plataforma." />
      ) : null}

      {info.isSuccess ? (
        <>
          <p className="rounded-md border border-border bg-surface px-3 py-2 text-sm">
            Cuenta: <strong>{info.data.email}</strong>
          </p>
          {error ? <ErrorState message={error} /> : null}
          <form
            onSubmit={onSubmit}
            className="space-y-3 rounded-lg border border-border bg-surface p-4"
          >
            <label className="block space-y-1 text-sm">
              <span className="text-muted">Contraseña (mínimo 8 caracteres)</span>
              <input
                className={inputClass}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-muted">Repite la contraseña</span>
              <input
                className={inputClass}
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </label>
            <button
              type="submit"
              disabled={pending}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {pending ? "Activando…" : "Activar cuenta"}
            </button>
          </form>
        </>
      ) : null}
    </section>
  );
}
