import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { apiSend, type MfaSetupResponse } from "../../lib/api";
import { ErrorState } from "../../components/ui/ErrorState";

/**
 * Segundo factor de la dueña de la plataforma (Fase D): alta con secreto +
 * desactivación, ambos con código TOTP. Con sesión propia el backend solo
 * valida/activa (no emite tokens).
 */
export function MfaSettingsPage() {
  const { user, refreshUser } = useAuth();
  const enabled = Boolean(user?.mfa_enabled);

  const [setup, setSetup] = useState<MfaSetupResponse | null>(null);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const beginSetup = useMutation({
    mutationFn: () => apiSend<MfaSetupResponse>("POST", "/auth/mfa/setup", {}),
    onSuccess: (result) => {
      setError(null);
      setMessage(null);
      setSetup(result);
    },
    onError: (err) => setError(err instanceof Error ? err.message : "No se pudo iniciar."),
  });

  const submit = useMutation({
    mutationFn: async (input: { code: string }) => {
      if (enabled) {
        await apiSend<void>("POST", "/auth/mfa/disable", input);
      } else {
        await apiSend<{ mfa_enabled: boolean }>("POST", "/auth/mfa/verify", input);
      }
    },
    onSuccess: async () => {
      setError(null);
      setCode("");
      setSetup(null);
      await refreshUser();
      setMessage(
        enabled
          ? "Segundo factor desactivado. Vuelve a activarlo cuanto antes."
          : "Segundo factor activado. Ya lo necesitarás en cada acceso.",
      );
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Código no válido."),
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    submit.mutate({ code: code.trim() });
  }

  const busy = submit.isPending;
  const canSubmit = code.trim().length === 6 && (enabled || setup !== null);
  const inputClass =
    "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-primary";

  return (
    <section className="max-w-md space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Segundo factor (2FA)</h1>
        <p className="mt-1 text-sm text-muted">
          Tu cuenta es la única con 2FA obligatorio: sin el código de tu app authenticator no hay
          sesión posible.
        </p>
      </div>

      <p className="rounded-md border border-border bg-surface px-3 py-2 text-sm">
        Estado:{" "}
        <strong className={enabled ? "text-success" : "text-danger"}>
          {enabled ? "Activado" : "No activado"}
        </strong>
      </p>

      {error ? <ErrorState message={error} /> : null}
      {message ? <p className="text-sm text-success">{message}</p> : null}

      {!enabled && !setup ? (
        <button
          type="button"
          onClick={() => beginSetup.mutate()}
          disabled={beginSetup.isPending}
          className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {beginSetup.isPending ? "Generando secreto…" : "Configurar el 2FA"}
        </button>
      ) : null}

      {!enabled && setup ? (
        <div className="space-y-1 rounded-lg border border-border bg-surface p-4 text-sm">
          <p className="text-muted">
            Añade esta cuenta a tu app authenticator con el secreto y confirma con su código:
          </p>
          <p className="rounded-md border border-border bg-bg px-3 py-2 font-mono break-all">
            {setup.secret}
          </p>
          <p className="text-xs text-muted break-all">{setup.otpauth_url}</p>
        </div>
      ) : null}

      {setup !== null || enabled ? (
        <form
          onSubmit={onSubmit}
          className="space-y-3 rounded-lg border border-border bg-surface p-4"
        >
          <label className="block space-y-1 text-sm">
            <span className="text-muted">Código de 6 dígitos</span>
            <input
              className={inputClass}
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              autoComplete="one-time-code"
              placeholder="123456"
            />
          </label>
          <button
            type="submit"
            disabled={busy || !canSubmit}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {busy ? "Comprobando…" : enabled ? "Desactivar 2FA" : "Activar 2FA con este código"}
          </button>
        </form>
      ) : null}
    </section>
  );
}
