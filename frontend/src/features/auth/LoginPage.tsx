import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { homePathAfterLogin } from "./homePath";
import { ErrorState } from "../../components/ui/ErrorState";

type Mode = "student" | "staff";

export function LoginPage() {
  const { loginStudent, loginStaff } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("student");
  const [courseCode, setCourseCode] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [pin, setPin] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      if (mode === "student") {
        await loginStudent({ course_code: courseCode.trim(), identifier: identifier.trim(), pin });
      } else {
        const tokens = await loginStaff({ email: email.trim(), password });
        if (tokens.mfa_required) {
          // super_admin (Fase D): el2FA se resuelve en su pantalla de acceso
          navigate("/plataforma/acceso", {
            replace: true,
            state: { mfa_token: tokens.mfa_token, mfa_enrolled: tokens.mfa_enrolled },
          });
          return;
        }
      }
      navigate(homePathAfterLogin(), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar sesión.");
    } finally {
      setPending(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-primary";

  return (
    <section className="mx-auto max-w-md space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Iniciar sesión</h1>
        <p className="mt-1 text-sm text-muted">
          Estudiantes: código de curso + identificador + PIN. Personal: email + contraseña.
        </p>
      </div>

      <div className="flex gap-2" role="tablist" aria-label="Tipo de acceso">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "student"}
          onClick={() => setMode("student")}
          className={`flex-1 rounded-md border px-3 py-2 text-sm ${
            mode === "student" ? "border-primary bg-primary/10 text-primary" : "border-border"
          }`}
        >
          Estudiante
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "staff"}
          onClick={() => setMode("staff")}
          className={`flex-1 rounded-md border px-3 py-2 text-sm ${
            mode === "staff" ? "border-primary bg-primary/10 text-primary" : "border-border"
          }`}
        >
          Personal
        </button>
      </div>

      {error ? <ErrorState message={error} /> : null}

      <form
        onSubmit={onSubmit}
        className="space-y-3 rounded-lg border border-border bg-surface p-4"
      >
        {mode === "student" ? (
          <>
            <label className="block space-y-1 text-sm">
              <span className="text-muted">Código de curso</span>
              <input
                className={inputClass}
                value={courseCode}
                onChange={(e) => setCourseCode(e.target.value)}
                required
                autoComplete="off"
                placeholder="JAVA"
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-muted">Identificador</span>
              <input
                className={inputClass}
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                required
                autoComplete="username"
                placeholder="student01"
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-muted">PIN (6+ dígitos)</span>
              <input
                className={inputClass}
                type="password"
                inputMode="numeric"
                value={pin}
                onChange={(e) => setPin(e.target.value)}
                required
                minLength={6}
                pattern="\d{6,}"
                autoComplete="current-password"
              />
            </label>
          </>
        ) : (
          <>
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
          </>
        )}

        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {pending ? "Entrando…" : "Entrar"}
        </button>
      </form>

      <p className="text-center text-sm text-muted">
        <Link to="/" className="text-primary hover:underline">
          Volver al inicio
        </Link>
      </p>
    </section>
  );
}
