# Trabajo realizado en Super-admin — Fases A–D completadas (SaaS multi-tenant)

Informe de entregas del módulo SaaS multi-tenant (organizaciones clientes,
Stripe, roles `super_admin`/`org_admin`). Fuente de los requisitos:
[Super-admin-prompt.md](../1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md);
plan técnico: [PLAN_CLAUDE.md](../PLAN/PLAN_CLAUDE.md) §11–14.
Documenta lo entregado fase a fase, con verificación y pendientes.

**Documentación relacionada**: prompt [Super-admin-prompt.md](../1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md) ·
plan [PLAN_CLAUDE.md](../PLAN/PLAN_CLAUDE.md) ·
[CHANGELOG.md](../../CHANGELOG.md) (entradas `## [Fase A SaaS]` … `## [Fase D SaaS]`) ·
[PLAN_SUPER_ADMIN.md](../PLAN/PLAN_SUPER_ADMIN.md) (análisis previo) ·
hermanos [TRABAJO_REALIZADO_EN_ADMIN.md](TRABAJO_REALIZADO_EN_ADMIN.md),
[TRABAJO_REALIZADO_EN_PROFESOR.md](TRABAJO_REALIZADO_EN_PROFESOR.md) y
[TRABAJO_REALIZADO_EN_ALUMNO.md](TRABAJO_REALIZADO_EN_ALUMNO.md) ·
[Índice de docs](../Explicacion_de_Cada_ARCHIVO.md).

Resumen en `main`
(`https://github.com/kindred-98/Aula-de-clase-de-Java-Aspasia`):

| Fase | Commit | Contenido |
|------|--------|-----------|
| A | `05b3d28` | Base multi-tenant: `Organization`, roles `super_admin`/`org_admin`, migración `e1a2b3c4d5f6` |
| B | `814541f` | Registro público + Stripe Checkout + webhook con firma + activación por token |
| C | *sin commit todavía* | Aislamiento multi-tenant de todas las rutas + `/superadmin/*` |
| D | *sin commit todavía* | Frontend por rol (`/precios`, `/registro-empresa`, `/activar-cuenta/:token`, panel `/plataforma`) + 2FA TOTP de `super_admin` |

Verificación siempre en verde tras cada fase (backend `backend/`:
`ruff check .` → `ruff format --check .` → `mypy app` →
`pytest --cov=app --cov-fail-under=80`; frontend `frontend/`:
`npm run lint` → `npm run format:check` → `npm run typecheck` →
`npm run test`):

| Cierre | Backend | Frontend | Migración |
|---|---|---|---|
| Fase A | 133 tests | 66 tests | `e1a2b3c4d5f6` |
| Fase B | 149 tests · 86.50 % | 66 tests | `f4e5d6c7b8a9` |
| Fase C | 163 tests · 86.75 % | 66 tests (sin cambios FE) | `c7d8e9f0a1b2` |
| Fase D | **177 tests · 87.11 %** | **85 tests** (de 66) | `d8e9f0a1b2c3` |

---

## Fase D — Frontend por rol + 2FA de `super_admin` (2026-09-28)

Alcance completo en [PLAN_CLAUDE.md §14](../PLAN/PLAN_CLAUDE.md) (IMPLEMENTADA).
Cierra `Super-admin-prompt.md`: con esta fase están implementadas las
seis fases del prompt (A–D de este módulo más las previas del aula).

### 2FA TOTP obligatorio de `super_admin` (backend)

- `app/services/totp.py` (nuevo, **solo stdlib** — ninguna dependencia
  añadida): secreto base32, código de 6 dígitos / 30 s / SHA-1, verificación
  con ventana ±1 y `otpauth_url` con issuer `Aspasia`. Vectores del
  RFC 6238 en verde (el RFC publica 8 dígitos; el test compara la cola de 6).
- **Reto de login**: `POST /auth/login/staff` de `super_admin` ya **no**
  entrega tokens → `StaffLoginResponse { access_token: "", mfa_required,
  mfa_token (JWT `type=mfa`, 5 min), mfa_enrolled }`. El resto de roles
  sigue recibiendo `TokenResponse` sin cambios (regresión cubierta).
- Endpoints `/auth/mfa/setup` (secreto pendiente sin activar, 409 si ya
  está activo), `/auth/mfa/verify` (activa con el primer código; con
  `mfa_token` emite la sesión real, con sesión propia solo confirma; código
  inválido → audit `mfa_failed` y **429 a los 5 intentos**) y
  `/auth/mfa/disable` (204, exige código vigente, `require_super_admin`,
  audit `auth.mfa_disabled`).
- **Modelo + migración `d8e9f0a1b2c3`**: `users.mfa_secret` (String(64)
  nullable) y `users.mfa_enabled` (Boolean NOT NULL, `server_default`
  false). Estado expuesto en `UserPublic.mfa_enabled` (no hay endpoint
  `/mfa/status`); `OptionalSessionUser` nuevo en `security/policies.py`.

### Frontend por rol (Fase D)

- **Públicas** (sin sesión, enlazadas desde el header): `/precios`
  (catálogo de planes + CTA), `/registro-empresa` (alta con el plan
  preseleccionado de la URL y salto al Checkout de Stripe vía
  `lib/checkout.ts`; mensajes para 409 duplicado, 503 sin precio y 502
  Stripe caído) y `/activar-cuenta/:token` (contraseña de un solo uso,
  48 h).
- **`/plataforma/acceso`** (NO enlazada públicamente): pantalla propia del
  reto 2FA — contraseña → código (con setup la primera vez, mostrando
  secreto + `otpauth_url` **sin QR**) → sesión. `AuthContext.loginStaff`
  no crea sesión si `mfa_required`; `finishMfaLogin` la crea tras verificar.
- **Panel `/plataforma`** con `RequireSuperAdmin` + `SuperAdminLayout`:
  métricas de negocio, organizaciones (filtros, alta, edición en línea,
  borrado en dos pasos), suscripciones y sección de 2FA. Guard: cualquier
  otro rol autenticado redirige al inicio.
- **Navegación y redirección**: sin sesión → link "Precios";
  `homePathAfterLogin` (`super_admin → /plataforma`, `org_admin → /admin`);
  `super_admin` autenticado solo ve "Plataforma"/"Mi cuenta"/"Salir" (sin
  enlaces académicos).

### Tests, mutación y gates

- **Backend +14** (`tests/test_saas_phase_d.py`): vectores RFC + drift ±1,
  challenge sin tokens + regresión de roles, flujo completo (setup →
  verify → tokens → relogin ya enrolled), inválidos → 401 y lockout 429,
  `mfa_token` basura/`type != mfa` → 401, fronteras de rol y disable → 204.
- **Frontend +18** (`PublicPhaseD.test.tsx`, `SuperAdminPhaseD.test.tsx` y
  `routes.test.tsx` ampliado): páginas públicas, reto 2FA (enrolled y
  primera vez), código incorrecto, panel, guard de rol, borrado en dos
  pasos y gestión del 2FA.
- **Mutación** (evidencia en [PLAN §14.4](../PLAN/PLAN_CLAUDE.md)):
  sabotear el reto en `login_staff` (`if False and …`) →
  **`4 failed, 10 passed`** → revertida → `14 passed`.
- **Gates (2026-09-28)**: `ruff check` / `ruff format --check` (102
  ficheros) / `mypy app` (75 módulos) en verde; `pytest --cov=app` →
  **177 passed · 87.11 %**; migración con roundtrip
  `downgrade -1 → upgrade head` → `d8e9f0a1b2c3 (head)`; frontend
  `eslint` + `prettier --check` + `tsc -b` + `vitest` → **85 passed**.

---

## Fase C — Aislamiento multi-tenant + rutas `/superadmin/*` (2026-09-28)

Cuerpo detallado de esta fase. Alcance completo en
[PLAN_CLAUDE.md §13](../PLAN/PLAN_CLAUDE.md); resumen ejecutivo:

### Invariante central

Toda query de `org_admin` filtra por `organization_id == user.organization_id`;
un **recurso de otra organización responde 404, nunca 403** (no se revela su
existencia). `super_admin` (`organization_id IS NULL`) no ve datos académicos
y solo opera en `/superadmin/*`; `org_admin` recibe 403 en `/superadmin/*` y
`super_admin` sigue recibiendo 403 en `/admin/*`.

### Choke points nuevos (`app/security/policies.py`)

- `_ensure_course_org(user, course)` → 404; llamado **dentro de**
  `get_course_or_404`, `require_staff_of_course` y `require_enrolled` (cubre
  también las llamadas directas con `_get_course` locales).
- `ensure_same_org(user, resource_org_id, detail)` → 404 para todos los
  `db.get(...)` con id de path (usuarios, categorías, cohorts, roles…).
- `require_super_admin(user)` → solo `UserRole.super_admin`.
- Rama `org_admin` de `can_read_submission` exige curso de la propia org
  (cubre `GET /submissions/{id}` y `.../github-meta`).

### Scoping endpoint a endpoint (65 rutas de los 5 ficheros admin + fugas)

| Fichero | Rutas | Scoping aplicado |
|---|---|---|
| `admin.py` | 12 | `GET /users` con `where(organization_id)`; modificaciones de usuario → `ensure_same_org`; `audit-logs` vía JOIN por actor; dashboard KPIs + `recent_audit`/`recent_subs` filtrados; observer submissions/evaluations por cursos de la org |
| `courses.py` | 17 | rama `org_admin` de `list_courses` filtrada; choke en detalle/classroom/seats/enrollments/teachers/overview; `ensure_same_org(student/teacher)` en altas |
| `phase3.py` | 6 | `clone` con `organization_id` del admin + código único por org; RGPD admin → 404 si usuario ajeno |
| `phase_c.py` | 7 | multi dashboard filtrado; `system_settings` por PK `(key, organization_id)`; reports filtrados; backup con `ensure_same_org` |
| `phase_d.py` | 22 | categorías/cohorts/roles con org y unicidades por org; taxonomy y auto-enroll exigen misma org; sesiones vía JOIN `User`; revoke/unlock/custom-role → 404 |
| `messages.py` | 5 fugas | `_can_message`, directorio, unread-count, thread y envío → 404 o filtrado por org |
| `course_chat.py` · `calendar_inst.py` · `work.py` | — | `_assert_course_member` con choke; calendario institucional filtra cursos visibles; staff de `work.py` exige org |

### Rutas nuevas `/api/v1/superadmin/*`

`routes/superadmin.py` + `schemas/superadmin.py`, todas con
`require_super_admin`:

- `GET/POST /superadmin/organizations`, `GET/PATCH/DELETE
  /superadmin/organizations/{id}` — alta manual (enterprise), edición de
  estado/plan, **DELETE solo de org vacía** (si tiene usuarios o cursos →
  409 con detalle; limpia settings/cohorts/categories/roles propios).
- `GET /superadmin/subscriptions` — filas Stripe (customer, subscription,
  estado, plan, trial).
- `GET /superadmin/metrics` — agregados **sin datos académicos** (orgs por
  estado/plan, usuarios por rol, total de cursos, trials que terminan en
  ≤ 7 días).

### Modelo y migración `c7d8e9f0a1b2`

- Columna `organization_id` (FK, backfill a la org por defecto, después
  NOT NULL) en las 4 tablas hasta entonces globales: `course_categories`,
  `cohorts`, `custom_roles`, `system_settings`.
- PK de `system_settings`: `key` → `(key, organization_id)` (ajustes por
  organización).
- Unicidades globales → compuestas por org (`courses.code`, `slug` de
  categorías, `code` de cohorts, `name` de roles): mismo código en otra org
  → 201; repetido en la misma org → 409.
- `batch_alter_table` para SQLite + rama PostgreSQL; `audit_logs` **sin
  columna nueva** (filtro por JOIN del actor). Aplicada a `dev.db` con
  roundtrip `upgrade → downgrade → upgrade` verificado.
- Los tests crean el esquema con `create_all`, por eso las 4 columnas
  llevan `default=1` en el modelo (org por defecto).

### Tests de la fase (`tests/test_saas_phase_c.py`, 14)

- Aislamiento con **dos organizaciones**; el test principal
  (`test_cross_org_isolation_via_real_registration_flow`) las crea con el
  **flujo real de la Fase B** (registro + webhook firmado + activación).
- Matriz completa: usuarios, cursos, contenido académico, settings,
  sesiones y audit logs aislados; unicidades por org; asignaciones
  cruzadas (alumno/profesor de B en curso de A, miembros de cohort) → 404;
  CRUD de superadmin; métricas sin claves prohibidas; fronteras de rol
  (parametrizado).

### Prueba de mutación (evidencia en [PLAN §13.4](../PLAN/PLAN_CLAUDE.md))

- (a) Quitar el `where(User.organization_id == …)` de `GET /admin/users`
  → **`2 failed, 12 passed`** → revertida.
- (b) Sabotear `_ensure_course_org` a no-op → **`2 failed, 12 passed`**
  (`assert 200 == 404`) → revertida. Desviación documentada: sabotear solo
  el check de `require_staff_of_course` **no falló nada** (está enmascarado
  por `get_course_or_404` y `require_enrolled`, refuerzo en 3 sitios), así
  que la mutación se reorientó al choke compartido, que sí es load-bearing.

### Verificación Fase C (2026-09-28)

- `ruff check .` → `All checks passed!`; `ruff format --check .` →
  `100 files already formatted`; `mypy app` → `Success: no issues found in
  74 source files`.
- `pytest --cov=app --cov-fail-under=80` → **163 passed · 86.75 %**
  (149 existentes + 14 nuevos); los 149 previos siguieron en verde salvo
  `MIGRATION_HEAD` en `test_saas_phase_a.py`.
- Migración: `alembic current` → `c7d8e9f0a1b2 (head)` en `dev.db`.
- Frontend sin cambios: `npm run lint` + `npm run test` → **66 passed**.

---

## Fase B — Registro, Stripe y activación (commit `814541f`, 2026-09-26)

- `routes/public.py`: `GET /public/plans` (catálogo estático) y
  `POST /public/organizations` → org `pending_payment` sin `User` + Stripe
  Checkout Session (`mode=subscription`, trial 14 días).
- Webhook `POST /webhooks/stripe` con **verificación de firma obligatoria**
  e idempotencia por `event_id` (`stripe_webhook_events`): alta de
  `org_admin` con token de activación, avisos de trial, ciclo de vida de
  la suscripción.
- Activación de 48 h (`GET/POST /auth/activate`, hash sha256, un solo
  uso); login con `password_hash NULL` → 401 explícito + audit.
- `EmailService` abstracto con `ResendEmailService`/`ConsoleEmailService`;
  config con validación de secretos en `production`; cleanup de orgs
  pendientes. Migración `f4e5d6c7b8a9`; 16 tests
  (`tests/test_saas_phase_b.py`).

## Fase A SaaS — Base multi-tenant (commit `05b3d28`, 2026-09-26)

- Modelos `Organization` + `OrgStatus`; `users.organization_id` y campos
  de token de activación; `courses.organization_id NOT NULL`.
- `UserRole = super_admin | org_admin | teacher | student` (renombrado
  `admin → org_admin`) + CHECKs `ck_users_org_by_role` y
  `ck_users_role_valid`.
- `security/policies.py`: super_admin sin acceso académico; CLI
  `scripts.create_admin --role org_admin|super_admin` (promoción a
  `super_admin` por API → 403, solo CLI). Migración `e1a2b3c4d5f6`;
  8 tests (`tests/test_saas_phase_a.py`).

---

## Pendientes conocidos (heredados; la Fase D ya está entregada)

- Sin escáner QR para el 2FA (se muestran el secreto y el `otpauth_url`;
  se evitó a propósito añadir dependencias).
- Sin WebSocket (polling con TanStack Query) y email solo in-app salvo
  Resend de activación (heredado de fases previas).

---

## Superficie de esta rama (sin commitear al cierre de Fase D)

```
M  Archivo_Markdown/{1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md, Explicacion_de_Cada_ARCHIVO.md, PLAN/{PLAN_CLAUDE.md, PLAN_SUPER_ADMIN.md}} · CHANGELOG.md
M  backend/app/api/v1/{router.py, routes/{admin,auth,courses,phase3,phase_c,phase_d,work,messages,course_chat,calendar_inst}.py}
M  backend/app/models/{course,scale,system,user}.py · backend/app/security/policies.py
M  backend/app/{schemas/auth.py, services/auth_service.py} · backend/tests/test_saas_phase_a.py
M  frontend/src/app/{layout.tsx, routes.tsx, routes.test.tsx} · frontend/src/lib/api.ts
M  frontend/src/features/auth/{AuthContext.tsx, LoginPage.tsx, homePath.ts} · frontend/src/features/student/StudentPhaseS.test.tsx
?? Archivo_Markdown/PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md
?? backend/alembic/versions/{c7d8e9f0a1b2_fase_c_org_scoping.py, d8e9f0a1b2c3_add_mfa_super_admin_phase_d.py}
?? backend/app/api/v1/routes/superadmin.py · backend/app/schemas/superadmin.py
?? backend/app/services/totp.py · backend/tests/{test_saas_phase_c.py, test_saas_phase_d.py}
?? frontend/src/features/public/ · frontend/src/features/superadmin/ · frontend/src/lib/checkout.ts
```
