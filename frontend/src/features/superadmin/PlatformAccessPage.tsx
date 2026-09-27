import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { homePathAfterLogin } from "../auth/homePath";
import { apiSend, type MfaSetupResponse, type MfaVerifyResponse } from "../../lib/api";
import { ErrorState } from "../../components/ui/ErrorState";

type NavState = { mfa_token?: string; mfa_enrolled?: boolean } | null;

/**
 * Acceso de la dueña de la plataforma (Fase D): pantalla NO enlazada desde
 * la web pública. Flujo: contraseña → reto 2FA (setup la primera vez) →
 * tokens. El super_admin no tiene sesión posible sin el segundo factor.
 */
export function PlatformAccessPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { loginStaff, finishMfaLogin } = useAuth();

  const navState = (location.state ?? null) as NavState;
  const [mfaToken, setMfaToken] = useState<string | null>(navState?.mfa_token ?? null);
  const [enrolled, setEnrolled] = useState<boolean>(navState?.mfa_enrolled ?? false);
  const [setup, setSetup] = useState<MfaSetupResponse | null>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function startSetup(token: string) {
    const result = await apiSend<MfaSetupResponse>("POST", "/auth/mfa/setup", {
      mfa_token: token,
    });
    setSetup(result);
  }

  async function onSubmitPassword(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const tokens = await loginStaff({ email: email.trim(), password });
      if (!tokens.mfa_required || !tokens.mfa_token) {
        // Cuenta sin 2FA (no debería ser super_admin): sigue el flujo normal
        navigate(homePathAfterLogin(), { replace: true });
        return;
      }
      setMfaToken(tokens.mfa_token);
      setEnrolled(Boolean(tokens.mfa_enrolled));
      if (!tokens.mfa_enrolled) await startSetup(tokens.mfa_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar sesión.");
    } finally {
      setPending(false);
    }
  }

  async function onSubmitCode(event: FormEvent) {
    event.preventDefault();
    if (!mfaToken) return;
    setError(null);
    setPending(true);
    try {
      const result = await apiSend<MfaVerifyResponse>("POST", "/auth/mfa/verify", {
        mfa_token: mfaToken,
        code: code.trim(),
      });
      if (!result.access_token) {
        setError("El servidor no devolvió la sesión. Inténtalo de nuevo.");
        return;
      }
      finishMfaLogin({
        access_token: result.access_token,
        must_change_credentials: Boolean(result.must_change_credentials),
      });
      navigate("/plataforma", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código no válido.");
    } finally {
      setPending(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-primary";

  return (
    <section className="mx-auto max-w-md space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Acceso de la plataforma</h1>
        <p className="mt-1 text-sm text-muted">
          Zona restringida a la dueña de la plataforma. Requiere doble factor (2FA).
        </p>
      </div>

      {error ? <ErrorState message={error} /> : null}

      {mfaToken === null ? (
        <form
          onSubmit={onSubmitPassword}
          className="space-y-3 rounded-lg border border-border bg-surface p-4"
        >
          <label className="block space-y-1 text-sm">
            <span className="text-muted">Email</span>
            <input
              className={inputClass}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-muted">Contraseña</span>
            <input
              className={inputClass}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="current-password"
            />
          </label>
          <button
            type="submit"
            disabled={pending}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {pending ? "Entrando…" : "Continuar"}
          </button>
        </form>
      ) : (
        <form
          onSubmit={onSubmitCode}
          className="space-y-3 rounded-lg border border-border bg-surface p-4"
        >
          {enrolled ? (
            <p className="text-sm text-muted">
              Introduce el código de tu aplicación authenticator.
            </p>
          ) : (
            <>
              <p className="text-sm text-muted">
                Primera vez: añade esta cuenta a tu app authenticator con el secreto y confirma con
                su código.
              </p>
              {setup ? (
                <div className="space-y-2">
                  <p className="rounded-md border border-border bg-bg px-3 py-2 font-mono text-sm break-all">
                    {setup.secret}
                  </p>
                  <p className="text-xs text-muted break-all">{setup.otpauth_url}</p>
                </div>
              ) : (
                <p className="text-sm text-muted">Generando el secreto…</p>
              )}
            </>
          )}
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
              autoFocus
              autoComplete="one-time-code"
              placeholder="123456"
            />
          </label>
          <button
            type="submit"
            disabled={pending || (!enrolled && setup === null)}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {pending ? "Verificando…" : "Verificar y entrar"}
          </button>
        </form>
      )}

      <p className="text-center text-sm text-muted">
        <Link to="/" className="text-primary hover:underline">
          Volver al inicio
        </Link>
      </p>
    </section>
  );
}
