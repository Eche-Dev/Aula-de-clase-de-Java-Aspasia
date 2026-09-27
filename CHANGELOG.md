# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).

**Documentación relacionada**: [README](./README.md) · índice [Explicacion_de_Cada_ARCHIVO](./Archivo_Markdown/Explicacion_de_Cada_ARCHIVO.md) · planes ([Claude](./Archivo_Markdown/PLAN/PLAN_CLAUDE.md), [Admin](./Archivo_Markdown/PLAN/PLAN_ADMIN.md), [Profesor](./Archivo_Markdown/PLAN/PLAN_PROFESOR.md), [Alumno](./Archivo_Markdown/PLAN/PLAN_ALUMNO.md), [Super-admin](./Archivo_Markdown/PLAN/PLAN_SUPER_ADMIN.md)) · informes ([Admin](./Archivo_Markdown/PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ADMIN.md), [Profesor](./Archivo_Markdown/PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_PROFESOR.md), [Alumno](./Archivo_Markdown/PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ALUMNO.md), [Super-admin](./Archivo_Markdown/PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md)) · [comandos](./Archivo_Markdown/COMANDOS/COMANDOS_DE_LA_APP.md).

## [Fase D SaaS] — 2026-09-28

### Hecho

- Backend (Fase D de `1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md`):
  **2FA TOTP obligatorio para `super_admin`** (RFC 6238, sin dependencias
  nuevas).
  - `app/services/totp.py` (nuevo, solo stdlib): secreto base32, código de
    6 dígitos / 30 s / SHA-1, `verify_totp` con ventana ±1 y `otpauth_url`
    con issuer `Aspasia`. Vectores del RFC 6238 en verde (8 dígitos → se
    compara la cola de 6).
  - **Modelo + migración `d8e9f0a1b2c3`** (revisión `c7d8e9f0a1b2`):
    `users.mfa_secret` (String(64) nullable) + `users.mfa_enabled`
    (Boolean NOT NULL, `server_default` false); aplicada a `dev.db` con
    roundtrip `downgrade -1 → upgrade head` verificado.
  - **Reto de login** (`auth_service.login_staff`): `super_admin` ya **no**
    recibe tokens en `POST /auth/login/staff` → `StaffLoginResponse` con
    `access_token=""`, `mfa_required=true`, `mfa_token` (JWT `type=mfa`, 5
    min) y `mfa_enrolled`; el resto de roles conserva `TokenResponse`
    (regresión cubierta). Audita `auth.mfa_challenge`.
  - **Endpoints `/auth/mfa/*`**: `setup` (secreto pendiente sin activar,
    409 si ya activo), `verify` (TOTP ±1 → activa; con `mfa_token` emite la
    sesión real, con sesión solo confirma; fallo → audit `mfa_failed` y
    **429 a los 5 intentos**) y `disable` (204, exige código vigente +
    `require_super_admin`, audita `mfa_disabled`). Estados expuestos en
    `UserPublic.mfa_enabled`; `OptionalSessionUser` en `policies.py`.
  - **Tests** `tests/test_saas_phase_d.py` (**14**): vectores RFC +
    drift ±1, challenge sin tokens + regresión de roles, flujo completo
    setup → verify → tokens → relogin ya enrolled, código inválido → 401 y
    lockout 429, `mfa_token` basura/`type != mfa` → 401, fronteras de rol
    y disable con código correcto → 204. `MIGRATION_HEAD` de phase A →
    `d8e9f0a1b2c3`.
  - **Prueba de mutación** (evidencia en PLAN §14.4): sabotear el reto en
    `login_staff` (`if False and …`) → **`4 failed, 10 passed`** →
    revertida → `14 passed`.
- Frontend (Fase D): **páginas públicas + panel de la plataforma + acceso
  2FA**.
  - Públicas: `/precios` (catálogo con CTA a `/registro-empresa?plan=`),
    `/registro-empresa` (alta con plan preseleccionado de la URL y salto al
    Checkout de Stripe vía `lib/checkout.ts` `redirectToCheckout`; errores
    traducidos: 409 duplicado, 503 sin precio, 502 Stripe caído) y
    `/activar-cuenta/:token` (contraseña en un solo uso, 48 h).
  - **Acceso de la plataforma** `/plataforma/acceso` (NO enlazada en la web
    pública): contraseña → reto 2FA con setup la primera vez (muestra
    secreto + `otpauth_url`, sin QR) → código → sesión; `loginStaff` con
    `mfa_required` **no** crea sesión (`AuthContext.finishMfaLogin`).
  - **Panel `/plataforma`** con guard `RequireSuperAdmin` y layout propio:
    métricas (agregados de negocio), organizaciones (filtros, alta, edición
    en línea y borrado en dos pasos), suscripciones y sección 2FA
    (alta/desactivación con código).
  - Redirección por rol: `homePathAfterLogin` (`super_admin → /plataforma`,
    `org_admin → /admin`) y navegación distinta según sesión (con sesión sin
    sesión: link "Precios"; `super_admin` autenticado solo ve
    "Plataforma"/"Mi cuenta"/"Salir").
  - **Tests Vitest +18** (`PublicPhaseD`, `SuperAdminPhaseD` y
    `routes.test.tsx` ampliado): planes, 409 de registro, activación
    válida/caducada, plan preseleccionado, flujo enrolled y primera vez,
    código incorrecto, métricas, guard de rol, borrado en dos pasos,
    gestión del 2FA y reto desde el login.
- **Gates**: backend `ruff` + `format` + `mypy` (75 módulos) en verde,
  `pytest --cov=app` → **177 tests · 87.11 %**; frontend `eslint` +
  `prettier --check` + `tsc -b` en verde, `vitest` → **85 tests** (de 66);
  `alembic current` → `d8e9f0a1b2c3 (head)`.
- Documentación: `PLAN_CLAUDE.md` §14 → IMPLEMENTADA (con evidencia de
  gates y mutación) e informe
  [TRABAJO_REALIZADO_EN_SUPER_ADMIN.md](./Archivo_Markdown/PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md)
  actualizado a Fases A–D.

### Pendiente / limitaciones

- Sin escáner QR para el 2FA (se muestra el secreto y el `otpauth_url`;
  dependencia nueva deliberadamente evitada).
- WebSocket y emails fuera del flujo de activación siguen fuera de alcance
  (heredado de fases previas).

## [Fase C SaaS] — 2026-09-28

### Hecho

- Backend (Fase C de `1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md`):
  **aislamiento multi-tenant en todas las rutas + rutas `/superadmin/*`**.
  - **Choke points nuevos en `security/policies.py`**:
    `ensure_same_org(user, resource_org_id, detail)` (recurso de otra org →
    **404, nunca 403**), `_ensure_course_org` (llamado dentro de
    `get_course_or_404`, `require_staff_of_course` y `require_enrolled` —
    cubre también las llamadas directas con `_get_course` locales),
    `require_super_admin` (solo `UserRole.super_admin`) y la rama
    `org_admin` de `can_read_submission` que exige curso de la propia org.
  - **Scoping endpoint a endpoint** en los 5 ficheros admin (65 rutas):
    `admin.py` (12: usuarios, reset-pin/password/status/unlock,
    import-students, audit-logs vía JOIN por actor, dashboard KPIs +
    `recent_audit`/`recent_subs`, observer submissions/evaluations),
    `courses.py` (17, vía choke + `ensure_same_org` en student/teacher),
    `phase3.py` (clone con `organization_id` del admin, RGPD admin),
    `phase_c.py` (multi dashboard, settings por org, reports, backup),
    `phase_d.py` (22: categorías, cohorts, roles, sesiones, taxonomy,
    auto-enroll, custom-role, unlock); además `messages.py` (5 fugas:
    `_can_message`, directorio, unread-count, thread, envío) y
    `course_chat.py`/`calendar_inst.py`/`work.py`.
  - **Rutas nuevas `/api/v1/superadmin/*`** (`routes/superadmin.py` +
    `schemas/superadmin.py`, con `require_super_admin`): CRUD de
    organizaciones (DELETE solo de org vacía → 409 con detalle),
    `GET /superadmin/subscriptions` y `GET /superadmin/metrics`
    (agregados **sin datos académicos**); `super_admin` sigue con 403 en
    `/admin/*` y `org_admin` con 403 en `/superadmin/*`.
  - **Modelo + migración `c7d8e9f0a1b2`**: `organization_id` (FK, backfill
    org 1) en `course_categories`, `cohorts`, `custom_roles` y
    `system_settings`; PK de `system_settings` pasa a
    `(key, organization_id)`; unicidades globales → compuestas por org
    (`courses.code`, `slug`, `code` de cohorte, `name` de rol). Aplicada a
    `dev.db` con roundtrip upgrade→downgrade→upgrade verificado; los
    tests usan `create_all`, por eso el default de seguridad `1` en el
    modelo.
  - **Tests** `tests/test_saas_phase_c.py` (14): el principal crea las dos
    orgs con el **flujo real de la Fase B** (registro + webhook firmado +
    activación); cobertura de la matriz de aislamiento (usuarios, cursos,
    contenido académico, settings, sesiones, audit logs), unicidades por
    org, asignaciones cruzadas → 404, CRUD de superadmin y fronteras de
    rol.
  - **Prueba de mutación** (evidencia en PLAN §13.4): (a) quitar el
    `where(organization_id)` de `GET /admin/users` → 2 tests en rojo;
    (b) sabotear `_ensure_course_org` a no-op → 2 tests en rojo
    (`assert 200 == 404`). Nota: el check puntual de
    `require_staff_of_course` resultó estar enmascarado por las capas de
    `get_course_or_404`/`require_enrolled` (refuerzo en 3 sitios), así que
    la mutación (b) se aplicó sobre el choke compartido.
  - **Gates**: `ruff check` + `ruff format --check` + `mypy app` en verde;
    `pytest --cov=app` → **163 tests · 86.75 %**; migración
    `alembic current` → `c7d8e9f0a1b2`; frontend sin cambios
    (`eslint` + 66 tests en verde).
  - Fuera de alcance (→ Fase D): frontend (`/precios`,
    `/registro-empresa`, `/activar-cuenta/:token`, rutas por rol, panel de
    super_admin) y 2FA TOTP de `super_admin`.

## [Fase B SaaS] — 2026-09-26

### Hecho

- Backend (Fase B de `1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md`):
  - **Rutas públicas** (`routes/public.py`): `GET /public/plans`
    (catálogo estático de 3 planes en `services/plans.py`, sin tabla
    propia) y `POST /public/organizations` → `Organization`
    `pending_payment` **sin crear `User`** + Stripe Checkout Session
    (`mode=subscription`, trial 14 días en `subscription_data`,
    `payment_method_collection=always`, `metadata.organization_id`;
    404 plan inexistente, 409 email ya cliente, 503 sin Price,
    502 si falla Stripe).
  - **Webhook** `POST /webhooks/stripe` con **verificación de firma
    obligatoria** (`stripe.Webhook.construct_event`; ausente, inválida o
    de otro `whsec_` → 400 sin ningún efecto) + **idempotencia** por
    `event_id` (tabla nueva `stripe_webhook_events`). Eventos:
    `checkout.session.completed` → `org_admin` con token de activación
    hasheado y `password_hash=NULL` + org `trialing`;
    `trial_will_end` → email de aviso 3 días antes;
    `invoice.payment_succeeded/failed` → `active`/`past_due`;
    `customer.subscription.deleted` → `canceled`. Emails se envían
    **tras** el commit (best-effort).
  - **Activación** (`services/activation.py`): token aleatorio de un
    solo uso, hash sha256 en BD, 48 h; `GET/POST /auth/activate`;
    `GET` con token inválido/expirado → 400.
  - **Login staff con `password_hash NULL` → 401 explícito**
    ("Account not activated…", sin llegar a `verify_password`) con
    registro en AuditLog (`reason=not_activated`).
  - **`EmailService`** abstracto + `ResendEmailService` (REST vía
    httpx) y `ConsoleEmailService` (sin `RESEND_API_KEY` en dev, el
    enlace va al log).
  - **Config**: `Settings` con `STRIPE_SECRET_KEY`,
    `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_*`, `RESEND_API_KEY`,
    `EMAIL_FROM`, `PUBLIC_BASE_URL`; en `production` los tres secretos
    son obligatorios y no-placeholder (validación + test).
    `.env.example` ampliado.
  - **Limpieza**: `python -m scripts.cleanup_pending_organizations`
    (borra `pending_payment` >7 días; nunca con usuarios).
  - Dependencias: `stripe==15.6.1` y `httpx` pasan a runtime
    (`github_meta` ya lo importaba).
  - Migración alembic `f4e5d6c7b8a9` (revis. `e1a2b3c4d5f6`):
    tabla `stripe_webhook_events`; `dev.db` migrado al head.
  - Tests: `tests/test_saas_phase_b.py` (**16**: firma ausente/otra
    clave/payload basura → 400 sin efectos, flujo completo registro →
    Checkout → webhook → `org_admin` + email + idempotencia, login
    bloqueado hasta activar, activación con reuso y caducidad,
    ciclo de vida de la suscripción, super_admin bloqueado en
    Submission/Evaluation/CourseMessage con URLs construidas a mano,
    Settings en producción, cleanup, catálogo, conflictos de registro,
    Checkout con `stripe.checkout.Session.create` parcheado y
    EmailService).
- Documentación: entorno local de Stripe (`stripe listen`/`stripe
  trigger`, `whsec_` local ≠ producción, Resend en modo test) en
  `COMANDOS_DE_LA_APP.md` y `backend/README.md`; PLAN_CLAUDE.md §12.
- Gates: backend **149 tests · 86.50 %** (ruff, format, mypy,
  cobertura verdes); frontend **66 tests** sin cambios (lint y tests
  verdes). Mutación de firma detectada: con la verificación
  sabotada, los tests de firma fallan (`200 == 400`) y tras revertir
  vuelven a verde.

### Pendiente / limitaciones

- Fuera del alcance de la Fase B: `/superadmin/*` y filtrado por
  `organization_id` en las rutas existentes (**Fase C**, condición no
  negociable), frontend (`/precios`, `/registro-empresa`,
  `/activar-cuenta/:token`) y 2FA TOTP de super_admin (**Fase D**).
- El envío real de email requiere `RESEND_API_KEY`; en desarrollo el
  enlace de activación sale por log. `stripe_billing` solo se prueba
  con la API de Stripe parcheada (sin red).

## [Fase A SaaS] — 2026-09-26

### Hecho

- Backend (Fase A de `1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md`):
  - Modelos: `Organization` + `OrgStatus`
    (pending_payment/trialing/active/past_due/canceled) en
    `models/organization.py`; `users.organization_id`,
    `activation_token_hash` y `activation_token_expires_at`;
    `courses.organization_id NOT NULL`.
  - Roles: `UserRole = super_admin | org_admin | teacher | student`
    (renombrado `admin → org_admin` en toda la API) + dos CHECK en
    `users`: `ck_users_org_by_role` (solo super_admin sin organización)
    y `ck_users_role_valid` (domino cerrado de roles).
  - `security/policies.py`: super_admin sin acceso académico
    (`can_read_submission → False`, `user_permissions → []`;
    `require_admin`/staff siguen denegándolo).
  - `routes/admin.py`: usuarios, CSV y cursos heredan la organización
    del admin; crear o promover a `super_admin` por API → 403 (solo CLI).
  - Migración alembic `e1a2b3c4d5f6` (revis. `d9a4b5c6e7f8`): tabla
    `organizations`, org por defecto, backfill `admin → org_admin` +
    `organization_id`, índices/FKs, rama PostgreSQL con swap seguro del
    tipo `userrole` y downgrade reversible. `dev.db` migrado.
  - CLI `python -m scripts.create_admin --role org_admin|super_admin`
    (env vars `AULA_ADMIN_*` de fallback), helper
    `services/organization.get_or_create_default_organization` y
    `seed_demo` con organización.
  - Tests: `tests/test_saas_phase_a.py` (8: migración con ciclo
    upgrade/downgrade sobre datos crudos, constraints, CLI con
    `SessionLocal` parcheado, 403 de super_admin por API y permisos).
    Comprobación de mutación: sabotar el backfill o el CHECK hace
    fallar la suite (detectado y revertido).
- Frontend: literales de rol `admin → org_admin` en guards, layout,
  formularios, `roleLabel` y mocks de tests; `lib/api.ts` añade
  `super_admin` a la unión de roles (sin rutas nuevas).
- Gates: backend **133 tests** (ruff, format, mypy y cobertura verdes);
  frontend **66 tests** (lint, format, typecheck y build verdes).

### Pendiente / limitaciones

- Fuera del alcance de la Fase A: registro público con activación
  (Fase B), Stripe/webhooks (Fase B-C) y rutas nuevas de frontend
  `/superadmin/*` (Fase C).
- El listado de cursos/usuarios aún no filtra por tenant (aislamiento =
  Fase C); super_admin puede iniciar sesión pero aterriza en `/`.

## [Fase S] — 2026-09-25

### Hecho

- Backend (Alumnado):
  - `routes/student.py`: `GET /student/dashboard` (KPIs, mis cursos,
    próximas fechas, actividad reciente y lista "Por entregar", con
    aislamiento por matrícula) y `GET /student/pending-count` para el
    badge de navegación; 403 a profesorado, admin ve todos los cursos.
  - `routes/courses.py`: `GET /courses/{id}/my-progress` con
    `require_enrolled` — progreso propio por tarea (estado, nota,
    fecha de entrega), resumen (entregadas/pendientes, nota media, %
    de entrega) y asistencia (presentes/tardes/faltas/justificadas +
    %); 404 sin matrícula y 403 al profesorado.
  - Esquemas `app/schemas/student.py` (`StudentDashboard`,
    `StudentPendingItem`, `StudentCourseProgress`, …).
  - ruff + format + mypy + pytest+cov **123 tests, 86.70%**.
- Frontend `features/student/`:
  - S0: `StudentLayout` (nav responsive, tarjeta de usuario, logout),
    guard `RequireStudent` (student+admin), rutas `/student`,
    `homePath.ts → /student` y enlace "Panel" en la nav global.
  - S1: dashboard con KPIs, tarjetas de curso, "Por entregar" y
    evaluaciones recientes (componentes SRP en `dashboard/`).
  - S2: `usePendingCount` (refresco 30 s), badge "N entregas por
    entregar" en el NavLink de Inicio y componente `PendingList`
    (sustituye a `UpcomingList`, con chips de vencida/sin fecha).
  - S3: `MyProgressPage` en `/student/courses/:courseId` con resumen,
    asistencia y progreso por tarea; accesos rápidos a aula/tareas y
    enlaces desde `CourseCard` y "Mis cursos" (solo students).
  - S4: guard `RequireStaff` en `/courses/:id/evaluate`,
    `/attendance`, `/rubrics` y `/gradebook` (student → `/student`);
    la cabecera del aula oculta "Asistencia" y "Rúbricas" a no-staff.
  - Tests: `StudentPhaseS.test.tsx` — **66 tests frontend** en verde
    (lint, format, typecheck y build incluidos).

### Pendiente / limitaciones

- Badge y "Por entregar" usan polling (30 s), sin WebSocket (D-S5).
- La lista "Por entregar" muestra como máximo 10 tareas.
- Sin migraciones de esquema (D-S7); las reglas de visibilidad del
  backend no se tocaron (D-S6).

## [Fase T] — 2026-09-25

### Hecho

- Backend (Profesorado):
  - Endpoints de docente (`routes/teacher.py`): `GET /teacher/dashboard`
    (totales, cursos con pendientes y próxima entrega, próximos
    vencimientos y actividad reciente), `GET /teacher/queue` (cola
    paginada con filtros por curso, estado y búsqueda) y
    `GET /teacher/pending-count`.
  - Panel de curso (`routes/courses.py`): `GET /courses/{id}/overview`
    (progreso por tarea + estado por alumno) y
    `GET /courses/{id}/students/{student_id}` (nota media, asistencia y
    entregas), accesibles al staff del curso (teacher o admin).
  - Exportación de notas reutilizando `GET /courses/{id}/export/grades.csv`.
  - ruff + format + mypy + pytest+cov **114 tests, 86.11%**.
- Frontend `features/teacher/`:
  - T0: `TeacherLayout` con nav por secciones, guard `RequireTeacher`
    (teacher+admin) y rutas `/teacher`, `/teacher/queue`,
    `/teacher/courses/:id` y `/teacher/courses/:id/students/:studentId`.
  - T1: dashboard con KPIs, tarjetas de curso (enlazan al panel del
    curso), próximos vencimientos y actividad reciente.
  - T2: cola de evaluación con filtros, tabla de entregas y badge
    "Por revisar" con refresco cada 30 s (`usePendingCount`).
  - T3: panel de curso (accesos rápidos, progreso por tarea y tarjetas
    de alumno) y ficha del alumno (media, asistencia y entregas).
  - T4:
    - `usePermissions` (`GET /auth/permissions`) y guard
      `RequirePermission`; `/admin/reports` sale del árbol
      `RequireAdmin` y pasa a exigir `reports.view` (admin entra
      directo).
    - `AdminLayout` oculta las secciones solo-admin a no-admins
      (conserva Mensajes, Reportes y cerrar sesión).
    - `TeacherLayout`: enlace "Informes" condicional a `reports.view`
      y sidebar responsive (fila envuelta en móvil, columna en `lg`).
    - Botón "Exportar notas CSV" en el panel del curso (`apiDownload`
      con toast de confirmación y de error).
    - Contraste AA: `--color-warning` en claro `#d97706` → `#b45309`.
  - Tests `TeacherPhaseT.test.tsx` (12, 5 nuevos en T4); lint/format/
    typecheck/build **43 tests frontend** en verde.

### Pendiente / limitaciones

- El enlace "Informes" depende del permiso `reports.view` (Fase D); un
  rol personalizado sin ese permiso no lo ve, por diseño.
- No se añaden vistas de reportes propias del profesorado: se reutiliza
  el informe de Fase C en `/admin/reports`.

## [Fase D] — 2026-09-24

### Hecho

- Backend (Escala):
  - Modelos nuevos (`models/scale.py`): `CourseCategory`, `Cohort`,
    `CohortMembership`, `CustomRole`; FKs `Course.category_id`,
    `Course.cohort_id`, `User.custom_role_id` (SET NULL); migración
    `d9a4b5c6e7f8` aplicada localmente.
  - Categorías: CRUD `/admin/categories` (+ `GET /categories` con
    `course_count`) y `PATCH /admin/courses/{id}/taxonomy` para asignar
    categoría/cohort a un curso.
  - Cohorts: CRUD `/admin/cohorts` con miembros (alta/baja individual y
    masiva, idempotente) y `POST /courses/{id}/auto-enroll` (solo staff;
    matricula a todos los estudiantes del cohort de su curso con huecos
    libres; motivos `no_cohort|empty_cohort|no_free_seats|
    already_enrolled`; audit `course.auto_enrolled`).
  - Roles personalizados: CRUD `/admin/roles` con catálogo
    `KNOWN_PERMISSIONS` (`reports.view`, `settings.manage`,
    `backup.export`, `gradebook.view`, `courses.manage`,
    `users.manage`; permiso desconocido → 422), asignación vía
    `POST /admin/users/{id}/custom-role`, `GET /admin/permissions` y
    `GET /auth/permissions`.
  - Control de acceso basado en permisos: `require_permission()` en
    `security/policies.py` (admin → todos los permisos, resto → su
    `CustomRole`); conectado a Fase C: `/admin/settings` exige
    `settings.manage` y `/admin/reports/overview[.csv]` exige
    `reports.view`.
  - Sesiones y desbloqueo: `GET /admin/sessions` (refresh tokens vivos),
    `POST /admin/sessions/revoke` (audit `sessions.revoked`) y
    `POST /admin/users/{id}/unlock` (limpia fallos de login del audit,
    audit `user.unlocked`).
  - `CoursePublic` expone `category_id`/`cohort_id`.
  - Tests Fase D (`tests/test_phase_d.py`, 7 tests): categorías,
    taxonomy, cohorts + miembros + autoenrolamiento (con y sin huecos),
    gating de reportes por permiso personalizado, rutas solo-admin,
    sesiones y desbloqueo; `test_models` con las 4 tablas nuevas.
  - ruff + format + mypy + pytest+cov **105 tests, 86%**.
- Frontend modular `features/scale/`:
  - `/admin/categories`: CRUD de categorías con contador de cursos.
  - `/admin/cohorts`: CRUD de cohorts con despliegue de miembros y
    gestión individual/masiva.
  - `/admin/roles`: CRUD de roles personalizados con selección de
    permisos y asignación a usuarios.
  - `/admin/sessions`: tabla de sesiones activas + acciones de cuenta
    (revocar sesiones, desbloquear cuenta).
  - `CourseTaxonomyPanel` en el detalle de curso admin (asignar
    categoría/cohort + botón autoenrolar con feedback de motivos).
  - Nav AdminLayout con Categorías, Cohorts, Roles y Sesiones.
  - Tipos nuevos en `lib/api.ts` (category, cohort, role, session,
    autoenroll, taxonomy) y `CoursePublic.category_id/cohort_id`.
  - Tests `ScalePhaseD.test.tsx` (4); lint/format/typecheck/build
    **31 tests frontend** en verde.

### Pendiente / limitaciones

- Item 17 (email real opcional) descartado por diseño: la plataforma
  es in-app (notificaciones y mensajes internos), sin envío SMTP.
- Pendiente Fase B: notificaciones in-app y anuncios globales.
- Ajustes de sesión (expiración, MFA) siguen fuera del alcance.

## [Fase C] — 2026-09-24

### Hecho

- Backend (LMS profesional):
  - Dashboard multi-curso: `GET /admin/dashboard/multi` con totales
    (cursos, matrículas, tareas, entregas, pendientes) y fila por curso
    con tasa de avance; solo admin.
  - Gradebook matriz: `GET /courses/{id}/gradebook` (staff del curso)
    con columnas = tareas, filas = alumnos matriculados, celda con
    estado + nota (última evaluación) y media por alumno.
  - Ajustes del centro: tabla `system_settings` (migración
    `c8f5e1a2b3d4`), `GET/PUT /admin/settings` (nombre, email soporte,
    visibilidad por defecto, entregas entre compañeros, largo PIN,
    tamaño máx. de upload, términos Markdown) con audit
    `settings.updated`.
  - Reportes: `GET /admin/reports/overview` (totales + por curso:
    matrículas, entregas, revisadas, nota media, asistencia) y
    `GET /admin/reports/overview.csv` con `Content-Disposition`.
  - Calendario institucional: `GET /calendar/institutional` (tareas con
    `due_at` + anuncios de los cursos visibles según rol; admin→todos,
    teacher→sus cursos, student→matrículas activas).
  - Backup de curso: `GET /courses/{id}/backup` (solo admin) en JSON
    con curso, seats, profes, matrículas, secciones, rúbricas, tareas,
    anuncios y entregas con notas; audit `course.backup`.
  - Tests Fase C (`tests/test_phase_c.py`, 6 tests): permisos por rol,
    gradebook, settings roundtrip, reportes+CSV, visibilidad del
    calendario y contenido del backup; `test_models` actualizado con
    `system_settings`.
  - ruff + format + mypy + pytest+cov **98 tests, 86%**.
- Frontend modular `features/phasec/` (1 responsabilidad por archivo):
  - `/admin/multi`: dashboard multi-curso (KPIs + tabla con avance).
  - `/admin/settings`: ajustes del centro (formulario PUT + feedback).
  - `/admin/reports`: informe con totales, tabla por curso y export CSV.
  - `/courses/:id/gradebook`: matriz de notas (columnas tareas, media).
  - `/calendar`: calendario institucional (tareas + anuncios por curso).
  - `CourseBackupButton` en el detalle de curso admin (export JSON).
  - Nav: AdminLayout con Multi-curso, Reportes y Ajustes; nav global
    con Calendario; enlace Gradebook en detalle de curso.
  - Tipos nuevos en `lib/api.ts` (multi, gradebook, settings, reports,
    calendar, backup).
  - Tests `PhaseC.test.tsx` (5); lint/format/typecheck/build
    **27 tests frontend** en verde.
- Migración local: `alembic upgrade head` → `c8f5e1a2b3d4`.

### Pendiente / limitaciones

- Ajustes del centro no incluyen políticas de sesión (Fase D: sesiones
  activas y desbloqueo de cuentas).
- Backup JSON no incluye archivos binarios de entregas (solo metadatos
  y notas); descarga directa desde el navegador.

## [Fase B] — 2026-09-24

### Hecho

- Backend (comunicación):
  - Chat privado ampliado: student↔student si comparten matrícula activa;
    `GET /messages/directory` por rol (admin→todos, teacher→sus alumnos+
    admins, student→profes+admins+compañeros de clase con `course_ids`).
  - `GET /messages/unread-count` (privados + no leídos por sala de curso,
    `total` calculado en `build_unread_count`).
  - Chat global por curso: tablas `course_messages` y `course_message_reads`
    (migración `b7e2d4f1a9c3`); `GET/POST /courses/{id}/chat`,
    `POST .../chat/read`, `GET /me/course-chats`; miembros 404 si no
    pertenecen; audit `course_chat.sent`.
  - Tests Fase B (`tests/test_messages_phase_b.py`, 5 tests): permisos
    student→student, directorio por rol, unread-count, sala de curso,
    aislamiento de no miembros.
  - ruff + format + mypy + pytest+cov **92 tests, 85%**.
- Frontend modular `features/messages/` (1 responsabilidad por archivo):
  - `/messages` accesible a todos los roles: pestañas Privado y Por curso.
  - Privado: conversaciones, directorio messageable, hilo, composer.
  - Curso: lista de salas (`/me/course-chats`), hilo con no leídos, composer.
  - Badge de no leídos en la nav (`useUnreadCount`, polling 20 s).
  - `features/admin/messages/` eliminado; `/admin/messages` redirige a
    `/messages`; AdminLayout y QuickActions actualizados.
  - Tipos nuevos en `lib/api.ts` (directory, unread, course chat).
  - Tests `MessagesPhaseB.test.tsx` (4); lint/format/typecheck/build
    **22 tests frontend** en verde.
- Migración local: `alembic upgrade head` → `b7e2d4f1a9c3`.

### Pendiente / limitaciones

- Notificaciones in-app (campana) y anuncios globales del centro: aún en
  Fase B roadmap (pendientes 6 y 8).
- Chat sin WebSocket (polling 8–20 s con TanStack Query).

## [Fase A] — 2026-09-24

### Hecho

- Backend:
  - Chat 1:1: tabla `messages` (migración `a1f3c9d2e8b4`), rutas
    `/messages/conversations`, `/messages/{user_id}`, `POST /messages`,
    `POST /messages/{id}/read`; permisos admin→cualquiera, teacher↔curso,
    student↔staff de sus cursos.
  - Admin: `POST /admin/users` (alta con `temporary_secret` una sola vez),
    `PATCH /admin/users/{id}`, `POST .../reset-password`, dashboard
    `GET /admin/dashboard` (KPIs + actividad reciente), observador
    `GET /admin/observer/submissions|evaluations`.
  - Perfil: `PATCH /auth/me` (nombre/email, 409 email duplicado).
  - `list_conversations` en Python puro (compatible SQLite sin `least`).
  - Tests Fase A (`tests/test_admin_phase_a.py`); ruff + mypy + pytest+cov
    **87 tests, 84.98%**.
- Frontend (estructura modular, 1 responsabilidad por archivo):
  - `features/admin/AdminLayout.tsx` + rutas anidadas en `app/routes.tsx`
    (dashboard, cursos, detalle de curso, usuarios, mensajes, observador,
    auditoría, import CSV, herramientas).
  - Dashboard: KPIs, acciones rápidas, entregas y auditoría recientes.
  - Cursos: crear/editar, matrículas, profesorado, enlace a observador.
  - Usuarios: alta con banner de secreto temporal, filtros, activar/desactivar,
    reset PIN/contraseña, borrado RGPD.
  - Mensajes: lista de conversaciones, hilo de chat con no leídos, escritura.
  - Observador: entregas + notas con filtros de curso/estado/alumno.
  - Import CSV: por curso (`name[,email][,username]`) con PINs en lote.
  - Herramientas: clonar curso, export CSV de notas, métricas por curso.
  - Mi cuenta (`/account`): perfil + cambio de contraseña
    (`PATCH /auth/change-credentials`); Privacidad solo RGPD (clonar/CSV
    movidos a Herramientas).
  - Nav: Mi cuenta, Mensajes (admin), Admin.
  - Tipos nuevos en `lib/api.ts`; `AuthContext.refreshUser`.
  - Tests: `AdminPhaseA.test.tsx` (3) + privacidad actualizada;
    **18 tests**, lint/format/typecheck/build en verde.

### Pendiente / limitaciones

- Smoke en vivo de la UI admin en el navegador del usuario (la app ya corre
  en local).
- Mensajes no usan WebSocket (polling 8–15 s con TanStack Query).

## [Fase 3] — 2026-09-24

### Hecho

- Backend:
  - Rúbricas: tabla `rubrics` + `assignments.rubric_id` (migración
    `c4f1a90e2b7d`, FK `SET NULL`, `batch_alter_table` compatible SQLite);
    CRUD `/courses/{id}/rubrics` con auditoría `rubric.*` y validación de
    curso al enlazar tareas.
  - Asistencia: `GET/PUT /courses/{id}/attendance` (upsert por día),
    `GET .../attendance/summary`; solo staff del curso; 404 si el alumno no
    está matriculado.
  - Calendario: `GET /courses/{id}/calendar` (tareas con `due_at` + anuncios
    ordenados); requiere matrícula.
  - Clonar curso (admin): `POST /courses/{id}/clone` copia seats, profesores,
    secciones, rúbricas, tareas y 20 anuncios (no enrollments/submissions);
    409 si `code` duplicado.
  - Export CSV: `GET /courses/{id}/export/grades.csv` (staff) con
    `Content-Disposition: attachment`.
  - Metadatos GitHub: `GET /submissions/{id}/github-meta` con caché en memoria
    TTL 300 s, timeout 3 s, degradación sin 500 si falla la API.
  - RGPD: `GET /me/export` (datos personales + entregas + evaluaciones +
    asistencia); `DELETE /me/data` (estudiante se autoanonimiza);
    `DELETE /admin/users/{id}/data` (admin, no a sí mismo → 400).
  - Tests: suite Fase 3 (`tests/test_phase3.py`) + `test_models` actualizado
    con tabla `rubrics`; ruff + mypy + pytest+cov en verde; `alembic upgrade
    head` verificado sobre SQLite.
- Frontend (Fase 3):
  - Tipos API nuevos (`RubricPublic`, `Attendance*`, `CalendarEvent`,
    `GithubMetaResponse`, `RgpdExportResponse`, `apiDownload` con `PUT`).
  - Asistencia (`/courses/:id/attendance`): pasada de lista por asiento con
    estados (presente/tarde/ausente/justificada), acciones masivas y resumen
    por estudiante.
  - Calendario (`/courses/:id/calendar`): eventos de tareas y anuncios con
    enlace a la tarea.
  - Rúbricas (`/courses/:id/rubrics`): CRUD con criterios (id, label, max) y
    confirmación de borrado.
  - Evaluación: selector de rúbrica + puntuación por criterio; panel de
    metadatos GitHub (`GithubMetaPanel`) degradable.
  - Cuenta y privacidad (`/account/privacy`): exportar datos RGPD en JSON,
    borrar datos con confirmación; admin: exportar notas CSV y clonar curso.
  - Nav: enlace Privacidad; aula: enlaces a Calendario, Asistencia y Rúbricas.
  - `Toast`/`ConfirmDialog` con `aria-live` y `role=alertdialog`; `ToastViewport`
    montado en `App`.
  - Tests: 17 (asistencia, calendario, rúbricas, privacidad, más la suite
    Fase 1–2); lint/format/typecheck/build en verde.
- Verificación local:
  - Backend: ruff, mypy, pytest+cov; `alembic upgrade head` SQLite
    (`3a38236975b6` → `2b87aadf33ae` → `c4f1a90e2b7d`).
  - Frontend: eslint, prettier, tsc, vitest (17), vite build.
  - TestClient: `GET /health` y `/api/v1/health` → 200.
  - Smoke en vivo sobre `demo_phase3.db` (seed + admin + migraciones):
    **27/27 checks OK** (login staff/estudiante, rúbricas, asistencia, CSV,
    clonar, RGPD, calendario, GitHub meta, cambios de PIN, aislamiento 403).

### Pendiente / limitaciones

- Docker/PostgreSQL no disponibles en esta máquina (CI + compose); el arranque
  en vivo de uvicorn+vite se validó con TestClient (sandbox no mantiene
  procesos en segundo plano).
- Metadatos GitHub reales dependen de red; en tests se cubre el parser y la
  degradación.
- Métricas de tasa de entrega avanzadas y UX/a11y finos pueden ampliarse en
  iteraciones futuras.

## [Fase 2] — 2026-09-23

### Hecho

- Backend:
  - Secciones de curso: CRUD (`/courses/{id}/sections`), slug único por curso
    (409), `kind` content|external, Markdown y URL externa.
  - Anuncios: CRUD (`/courses/{id}/announcements`) con autor y auditoría.
  - Tareas: `GET/PATCH/DELETE /assignments/{id}`, `due_at`, `max_score`,
    `visibility` (private|class), reentrega con `version` en submissions.
  - Panel admin (`/admin/*`, solo `require_admin`):
    - Listado/búsqueda de usuarios con filtro por rol.
    - Activar/desactivar cuentas (audit `user.status_changed`).
    - Reset de PIN de estudiante (PIN de 6 dígitos, se devuelve una sola vez,
      audit `pin.reset` sin PIN en claro).
    - Importación CSV de estudiantes por curso (`name[,email][,username]`),
      PINs generados en lote, matrícula automática, audit
      `students.imported`.
    - AuditLog con filtros por `action`, `course_id`, `actor_id`.
    - Métricas por curso: matrículas y entregas por estado.
  - `GET /auth/me` → `UserPublic` (rol para UI admin/staff).
  - Tests: 68 tests, cobertura **87 %** (mínimo 80 %); ruff + mypy en verde.
- Frontend (Fase 2):
  - `Markdown` seguro (sin HTML del usuario): títulos, listas, negrita,
    cursiva, código inline y bloques, enlaces http(s).
  - Contenido del curso (`/courses/:id/content`): sidebar de secciones,
    vista de sección (content/external) y anuncios; formularios de creación
    para staff.
  - Detalle de tarea (`/courses/:id/work/:assignmentId`): fecha límite,
    visibilidad, máximo, edición (staff) de título/descripción/due_at/
    visibility/max_score.
  - Lista de tareas en WorkPage con enlace al detalle y badge de atrasada.
  - Panel admin (`/admin`): pestañas Usuarios (búsqueda, activar/desactivar,
    reset PIN), Importar CSV, Audit log (filtro action) y Métricas por curso.
  - `AuthContext` carga `/auth/me`; nav muestra enlace Admin solo a admins.
  - Tests: 11 (rutas, login, secciones, detalle tarea, admin) + lint/format/
    typecheck/build en verde.
- Verificación local:
  - `alembic upgrade head` sobre SQLite (`3a38236975b6` → `2b87aadf33ae`).
  - TestClient: `GET /health` y `/api/v1/health` → 200.
  - Backend: ruff, mypy, pytest+cov 87 %. Frontend: eslint, prettier, tsc,
    vitest (11), vite build.

### Pendiente / limitaciones

- Docker/PostgreSQL no disponibles en esta máquina (CI + compose).
- Asistencia, calendario, GitHub metadata, clonar cursos, export CSV y
  rúbricas: Fase 3.
- Código de secciones/temas del curso en menú lateral ampliable (hoy
  Contenido desde el aula).

## [Fase 1] — 2026-09-23

### Hecho

- Backend:
  - Auth completa: login estudiante (course_code + identifier + PIN), login
    staff (email + password), refresh con rotación, logout, cambio obligatorio
    de credenciales (`must_change_credentials`).
  - Rate-limit de login fallido (5 intentos / 15 min → 429) vía `audit_logs`.
  - Políticas de permisos centralizadas en `app/security/policies.py`
    (admin / teacher-of-course / enrolled / peer visibility).
  - Cursos: CRUD, seats, matrículas, asignación de profesorado, vista de aula
    (classroom grid con estado de entrega por asiento).
  - Trabajo académico: assignments, submissions (draft/submit), archivos
    (validación extensión + magic bytes), evaluaciones (historial append-only).
  - Storage local con API abstracta (preparada S3).
  - Migración `2b87aadf33ae` (añade `users.username`).
  - Scripts: `seed_demo` (curso JAVA 3×5, 15 estudiantes con PIN, profe) y
    `create_admin`.
  - Tests: 57 tests, cobertura **86 %** (mínimo 80 %); ruff + mypy en verde.
- Frontend (Fase 1):
  - Contexto de sesión (access token en localStorage, refresh cookie).
  - Login (estudiante / personal), cambio de credenciales obligatorio.
  - Lista de cursos, vista de aula (cuadrícula con estados de entrega),
    workspace de estudiante (entregas + GitHub + archivos) y vista de
    evaluación de la profesora.
  - Rutas protegidas (`RequireAuth` + redirect a `/change-credentials`).
  - Tests: 7 (rutas, login success/error) + lint/format/typecheck/build.
- Verificación local:
  - `alembic upgrade head` sobre SQLite.
  - uvicorn + `GET /health` → 200; login staff + `GET /courses` → 200.
  - `seed_demo` + `create_admin` ejecutados sobre SQLite local.

### Pendiente / limitaciones

- Docker/PostgreSQL no disponibles en esta máquina (CI + compose).
- Announcements, attendance y secciones de contenido: Fase 2+.

## [Fase 0] — 2026-09-23

### Hecho

- [`PLAN_CLAUDE.md`](./Archivo_Markdown/PLAN/PLAN_CLAUDE.md) con esquema de
  datos completo, matriz de permisos, estructura de carpetas y decisiones
  (D1–D14).
- Estructura del monorepo: `backend/` (FastAPI) + `frontend/` (React/Vite) +
  infraestructura raíz.
- Backend:
  - App FastAPI con CORS, headers de seguridad, logging JSON y `/health`
    (+ alias bajo `/api/v1/health`).
  - Configuración con pydantic-settings y `.env.example`.
  - Modelos SQLAlchemy 2.x de todo el dominio (users, courses, seats,
    enrollments, sections, assignments, submissions, files, evaluations,
    announcements, attendance, audit_logs, refresh_tokens).
  - Alembic: migración inicial `3a38236975b6` (14 tablas, índices y
    únicas).
  - Seguridad base: argon2 (`hash_secret`/`verify_secret`), JWT access,
    valor de refresh token.
  - Tests: 20 tests (sistemas, modelos/integridad, seguridad) con
    cobertura **92 %** (mínimo exigido 80 %).
  - `ruff check`, `ruff format --check` y `mypy --strict` en verde.
- Frontend:
  - Vite 7 + React 19 + TypeScript 5.9 + Tailwind 4 + React Router 7 +
    TanStack Query 5.
  - Design tokens (claro/oscuro), layout base, estados Loading/Empty/Error,
    página de inicio que consulta la salud de la API.
  - ESLint flat + Prettier + Vitest (3 tests en verde) + `tsc -b` + build.
- Infra:
  - `docker-compose.yml` (postgres 17, api, frontend nginx).
  - Dockerfiles backend (python:3.12-slim) y frontend (multi-stage nginx).
  - GitHub Actions: lint + tests backend (con PostgreSQL y `alembic upgrade`),
    lint + tests + build frontend, validación de compose.
  - `Makefile`, `.pre-commit-config.yaml`, `.gitignore`, `.env.example`.

### Probado

- `pytest --cov=app --cov-fail-under=80` → 20 passed, 92.27 %.
- `ruff check .` / `ruff format --check .` / `mypy app` → OK.
- `alembic upgrade head` sobre SQLite local (CI lo hace sobre PostgreSQL).
- `npm run lint`, `format:check`, `typecheck`, `test`, `build` → OK.
- Arranque de uvicorn + `GET /health` → 200 (verificación local).

### Pendiente / limitaciones del entorno

- **Docker no está instalado** en la máquina de desarrollo: el compose no se
  pudo levantar aquí; se valida en CI (`docker compose config`) y deberá
  verificarse manualmente en una máquina con Docker (Fase 1).
- Local solo tiene **Python 3.14**: el objetivo oficial sigue siendo 3.12
  (Docker/CI). Ver [`PLAN_CLAUDE.md`](./Archivo_Markdown/PLAN/PLAN_CLAUDE.md)
  D1/D2.
- Seed demo, primer admin y endpoints de auth/cursos: **Fase 1**.
