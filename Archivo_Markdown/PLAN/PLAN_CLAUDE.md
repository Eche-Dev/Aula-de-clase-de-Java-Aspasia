# PLAN — Plataforma de Aula Virtual Multi-Curso

Documento de arquitectura y decisiones. Se actualiza ante cada decisión ambigua
(opción más segura) y sirve de referencia durante todas las fases.

- Idioma: documentación en español; código, variables y commits en inglés.
- Multi-tenant desde el día 1: todo dato de curso lleva `course_id` y toda
  consulta lo filtra.

**Documentación relacionada**: [prompt_Claude_PrimerasFases.md](../PROMPT_INICIAL/prompt_Claude_PrimerasFases.md)
(origen del plan) · [PLAN_ADMIN.md](PLAN_ADMIN.md),
[PLAN_PROFESOR.md](PLAN_PROFESOR.md), [PLAN_ALUMNO.md](PLAN_ALUMNO.md)
(planes por módulo) ·
[TRABAJO_REALIZADO_EN_ADMIN.md](../PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ADMIN.md),
[TRABAJO_REALIZADO_EN_PROFESOR.md](../PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_PROFESOR.md),
[TRABAJO_REALIZADO_EN_ALUMNO.md](../PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ALUMNO.md),
[TRABAJO_REALIZADO_EN_SUPER_ADMIN.md](../PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md)
(informes de entrega) · [CHANGELOG.md](../../CHANGELOG.md) ·
[Índice de docs](../Explicacion_de_Cada_ARCHIVO.md).

---

## 1. Stack (verificado)

| Capa | Tecnología | Versión usada | Verificación |
|------|------------|---------------|--------------|
| Backend | Python | `>=3.12` (Docker/CI: 3.12) | máquina local solo tiene 3.14 → ver decisión D1 |
| API | FastAPI | 0.141.1 | PyPI |
| ORM | SQLAlchemy | 2.0.54 | PyPI |
| Migraciones | Alembic | 1.20.0 | PyPI |
| Validación | Pydantic | 2.13.5 (v2) | PyPI |
| Settings | pydantic-settings | 2.15.0 | PyPI |
| BD | PostgreSQL | 3 (imagen `postgres:17-alpine`) | compose/CI |
| Driver PG | psycopg | 3.3.6 | PyPI |
| Auth hash | argon2-cffi | 25.1.0 | PyPI |
| JWT | PyJWT | 2.15.0 | PyPI |
| Servidor | uvicorn | 0.53.0 | PyPI |
| Frontend | React | 19.3.0 | npm |
| Build | Vite | 7.x + `@vitejs/plugin-react` 5.x | npm (peer deps comprobados) |
| Lenguaje | TypeScript | 5.9.x | npm (typescript-eslint admite `<6.1.0`) |
| CSS | Tailwind CSS | 4.x (`@tailwindcss/vite`) | npm |
| Datos | TanStack Query | 5.x | npm |
| Routing | React Router | 7.x | npm |
| Tests FE | Vitest 5 + Testing Library | — | npm |
| Lint BE | ruff 0.16.x, mypy 2.x | — | PyPI |
| Lint FE | eslint 9 (flat) + prettier 3 | — | npm |
| Tests BE | pytest 9 + pytest-cov | — | PyPI |

Nada de lo anterior se cambia sin justificarlo aquí.

---

## 2. Decisiones (ambigüedades resueltas)

**D1 — Python local vs objetivo 3.12.** La máquina de desarrollo solo tiene
Python 3.14 y no hay Docker instalado. Objetivo oficial: 3.12
(`requires-python = ">=3.12"`, imágenes `python:3.12-slim`, CI con 3.12).
El código evita sintaxis propia de 3.13/3.14. La verificación local se ejecuta
en 3.14; la de producción/CI en 3.12.

**D2 — Docker no disponible localmente.** Se generan `docker-compose.yml` y
Dockerfiles igualmente (requisito de infra). La verificación de la app en esta
máquina se hace arrancando uvicorn y vite en local; en CI se valida
`docker compose config` y las migraciones contra PostgreSQL real.

**D3 — Tests de BD.** Local: SQLite (sin infra). CI: PostgreSQL (servicio).
Los modelos usan tipos portables (`String`, `DateTime`, `JSON` con variante
`JSONB` en PG, `Enum` nativo) para que el comportamiento sea equivalente.
La cobertura mínima del 80 % se mide en el backend.

**D4 — Refresh token.** La especificación pide refresh rotatorio y revocable
pero no nombra la tabla. Se añade `refresh_tokens` (fase 1, contemplada en el
esquema): token hasheado, `expires_at`, `revoked_at`, rotación al usar.

**D5 — Rate limiting de PIN.** Sin dependencias externas: se cuentan intentos
fallidos consultando `audit_logs` (acción `auth.login_failed`) por IP y por
cuenta; bloqueo temporal a los 5 intentos. Persiste en BD → sobrevive reinicios.

**D6 — El profesor no tiene asiento.** La cuadrícula es solo de estudiantes
(`layout_rows × layout_cols`). La UI pinta a la profesora "al frente" fuera de
la cuadrícula. No se crea fila extra en BD.

**D7 — `submission.assignment_id` nullable.** Permite entregas libres (sin
tarea asociada) tal y como pide el modelo. `course_id` siempre presente.

**D8 — `evaluation` inmutable.** Nunca se UPDATE: cada evaluación es una fila
nueva (historial). La "actual" es la de `created_at` más reciente.

**D9 — Archivos.** Interfaz `Storage` con `LocalStorage` (disco, nombre
aleatorio + sha256) y `S3Storage` preparada (boto3) para producción. Descarga
siempre vía endpoint que comprueba permisos; `Content-Disposition: attachment`.

**D10 — Markdown.** Render en cliente con sanitización estricta; en servidor se
guarda Markdown crudo. Nunca HTML confiado.

**D11 — Archivar ≠ borrar.** Cursos se archivan (`status=archived`). El borrado
físico no existe en la UI de admin (solo RGPD para datos de un estudiante).

**D12 — CSV importación.** Formato: `name,email?,username?` (+ columnas
opcionales). PINs se generan en lote y se muestran una sola vez.

**D13 — Cookies vs bearer.** Access token JWT en memoria/`localStorage`
corto (15 min); refresh en cookie `HttpOnly` `SameSite=strict` path acotado.
En desarrollo sin HTTPS, cookie sin `Secure`; en producción `Secure`.

**D14 — Unicidad de estudiante por curso.** `UNIQUE(course_id, student_id)` y
`UNIQUE(course_id, seat_id)` en `enrollments`. Cambiar de asiento solo actualiza
`seat_id`; las `submissions` cuelgan del estudiante, no del asiento → no se
pierden entregas.

---

## 3. Esquema de datos

```
users
  id PK
  name str(200)
  email str(320) NULL UNIQUE          -- opcional en estudiantes
  role enum(admin|teacher|student)
  pin_hash str NULL                   -- argon2, solo estudiantes
  password_hash str NULL              -- argon2, admin/teacher
  is_active bool default true
  must_change_credentials bool default false
  created_at timestamptz

courses
  id PK
  name str(200)
  description text NULL
  code str(16) UNIQUE                 -- código corto de acceso
  status enum(active|archived) default active
  layout_rows int default 3
  layout_cols int default 5
  settings jsonb default {}           -- p.ej. {"peer_visibility_default": "class"}
  created_at timestamptz

course_teachers                          -- PK compuesta
  course_id FK->courses
  teacher_id FK->users
  PRIMARY KEY (course_id, teacher_id)

seats
  id PK
  course_id FK->courses
  row int, col int
  UNIQUE(course_id, row, col)

enrollments
  id PK
  course_id FK->courses
  student_id FK->users
  seat_id FK->seats NULL
  status enum(active|inactive) default active
  UNIQUE(course_id, student_id)
  UNIQUE(course_id, seat_id)          -- NULLs múltiples permitidos (PG)

sections
  id PK
  course_id FK->courses
  title str(200)
  slug str(80)
  order int
  kind enum(content|external)
  body_markdown text NULL
  external_url str(500) NULL
  UNIQUE(course_id, slug)

assignments
  id PK
  course_id FK->courses
  section_id FK->sections NULL
  title str(200)
  description_markdown text
  due_at timestamptz NULL
  max_score decimal(6,2) default 100
  visibility enum(private|class) default private
  created_by FK->users
  created_at timestamptz

submissions
  id PK
  assignment_id FK->assignments NULL   -- entregas libres
  course_id FK->courses
  student_id FK->users
  github_url str(500) NULL
  notes text
  status enum(draft|submitted|reviewed|needs_changes) default draft
  submitted_at timestamptz NULL
  version int default 1
  created_at, updated_at

submission_files
  id PK
  submission_id FK->submissions ON DELETE CASCADE
  original_name str(255)
  stored_name str(64)                  -- nombre aleatorio en disco/S3
  mime str(100)
  size_bytes bigint
  sha256 str(64)

evaluations
  id PK
  submission_id FK->submissions
  teacher_id FK->users
  score decimal(6,2) NULL
  rubric_scores jsonb default {}
  comment_markdown text
  created_at timestamptz               -- historial append-only

announcements
  id PK
  course_id FK->courses
  author_id FK->users
  title str(200)
  body_markdown text
  created_at timestamptz

attendance_records
  id PK
  course_id FK->courses
  student_id FK->users
  date date
  status enum(present|late|absent|excused)
  UNIQUE(course_id, student_id, date)

audit_logs
  id PK
  actor_id FK->users NULL
  action str(80)                       -- p.ej. auth.login_failed, pin.reset
  entity_type str(80) NULL
  entity_id str(64) NULL
  course_id FK->courses NULL
  payload jsonb default {}
  ip str(45) NULL
  created_at timestamptz

refresh_tokens                          -- D4, fase 1
  id PK
  user_id FK->users
  token_hash str(64)                   -- sha256 del token
  expires_at timestamptz
  revoked_at timestamptz NULL
  created_at timestamptz
```

Índices: todas las FK + columnas de filtrado frecuente
(`courses.code`, `enrollments.student_id`, `submissions.course_id`,
`submissions.student_id`, `submissions.status`, `audit_logs.action`,
`audit_logs.created_at`, `attendance_records.date`…).

Relación clave estudiante–asiento: `enrollments` separa entidades (D14);
mover un estudiante de asiento no toca `submissions`.

---

## 4. Matriz de permisos (siempre en backend)

Políticas reutilizables de FastAPI (dependencias): `CurrentUser`,
`RequireAdmin`, `RequireTeacherOf(course)`, `RequireEnrolled(course)`,
`CanWriteSubmission`, `CanReadSubmission`, `CanEvaluate`.

| Acción | admin | teacher (sus cursos) | student (matriculado) |
|--------|:-----:|:--------------------:|:---------------------:|
| CRUD cursos, clonar, archivar | ✔ | — | — |
| Gestionar profesores/estudiantes/PINs | ✔ | — | — |
| Ver AuditLog / métricas | ✔ | métricas de sus cursos | — |
| Crear secciones/tareas/anuncios | ✔ | ✔ | — |
| Ver todas las entregas del curso | ✔ | ✔ | solo si `visibility=class` (sin evaluaciones ajenas) |
| Escribir/borrar entrega | — | — | solo las suyas |
| Evaluar (nota, rúbrica, comentario) | ✔ | ✔ | — (solo lee la propia) |
| Pasar lista | ✔ | ✔ | — |
| Ver anuncios/secciones del curso | ✔ | ✔ | ✔ |
| Matricularse / ver cursos ajenos | ✔ | solo los suyos | solo los suyos |
| Exportar CSV notas / RGPD | ✔ / RGPD propio | exportar sus cursos | exportar sus datos |

Invariantes de seguridad (con tests obligatorios):

1. Estudiante jamás recibe `score`, `comment_markdown` o `rubric_scores` de
   otra persona (ni por ID directo).
2. Estudiante solo escribe en `submissions.student_id == yo`.
3. Estudiante sin matrícula ⇒ 404 en cualquier recurso del curso (no 403 con
   filtración de existencia).
4. Teacher sin `course_teachers` ⇒ 404 en el curso.
5. Multi-tenant: toda query de curso incluye `course_id`.
6. Mover de asiento no altera `submissions`.
7. PIN erróneo ×5 ⇒ bloqueo temporal + `audit_logs`.

---

## 5. Estructura de carpetas

```
/
├── README.md  CHANGELOG.md  LICENSE
├── Archivo_Markdown/        ← documentación (PLAN_*, TRABAJO_*, comandos)
├── Makefile  docker-compose.yml  .env.example
├── .pre-commit-config.yaml  .gitignore
├── .github/workflows/ci.yml
├── backend/
│   ├── Dockerfile  pyproject.toml  alembic.ini
│   ├── alembic/
│   │   ├── env.py  script.py.mako
│   │   └── versions/0001_initial.py
│   ├── app/
│   │   ├── main.py                   # create_app, middleware, router
│   │   ├── core/                     # config, logging, security, deps
│   │   ├── db/                       # base, session
│   │   ├── models/                   # SQLAlchemy 2.x (Mapped[])
│   │   ├── schemas/                  # Pydantic v2
│   │   ├── api/v1/routes/            # endpoints
│   │   ├── services/                 # lógica de negocio
│   │   ├── security/                 # políticas/permisos reutilizables
│   │   └── storage/                  # LocalStorage / S3Storage (fase 1)
│   ├── scripts/seed_demo.py          # curso Java 3×5 demo (fase 1+)
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       └── integration/
└── frontend/
    ├── Dockerfile  package.json  vite.config.ts  eslint.config.js
    ├── index.html  tsconfig*.json  .prettierrc
    └── src/
        ├── main.tsx  App.tsx  index.css
        ├── app/                      # router, providers, layout
        ├── components/ui/            # Button, Spinner, Toast, Confirm…
        ├── features/                 # auth, classroom, assignments, admin…
        ├── lib/                      # api client, query, utils
        └── test/setup.ts
```

---

## 6. Superficie API (v1, resumen por fase)

- **Fase 1:** `POST /auth/login` (curso+código+PIN / email+password),
  `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/change-credentials`,
  `GET /courses`, `GET /courses/{code}`, `GET /courses/{id}/classroom`,
  `GET/POST /courses/{id}/enrollments`, seats, `GET/POST /submissions`,
  upload/download de archivos, `GET/POST /submissions/{id}/evaluations`.
- **Fase 2:** sections, assignments (+versiones, fechas), announcements,
  admin CRUD, import CSV, audit log.
- **Fase 3:** rubrics, attendance, calendar, GitHub metadata, clone course,
  metrics, CSV export, RGPD.

Prefijo: `/api/v1`. Errores: `{ "detail": str }` FastAPI estándar.

---

## 7. Seguridad transversal

- CORS por lista de orígenes (`CORS_ORIGINS`), no `*`.
- Headers: `X-Content-Type-Options`, `X-Frame-Options=DENY`,
  `Referrer-Policy`, CSP básica en producción.
- Pydantic estricto; sin SQL a mano; ORM/parametrizado.
- Secretos solo por env; `.env.example` sin valores reales.
- Logs JSON estructurados sin PIN/tokens/contraseñas.
- Markdown sanitizado al renderizar (FE) y nunca se guarda HTML confiado.
- RGPD (fase 3): exportar y borrar datos de un estudiante.

---

## 8. Calidad y CI

- `ruff check` + `ruff format --check` + `mypy` + `pytest --cov` (≥80 %).
- `eslint` + `prettier --check` + `vitest run`.
- pre-commit: ruff, format, trailing whitespace, EOF, check-yaml,
  detect-private-key, prettier (FE).
- GitHub Actions: jobs `backend` (3.12, lint+tests+alembic sobre PG) y
  `frontend` (lint+tests) y `compose-config`.

---

## 9. Fases

| Fase | Contenido | Criterio de salida |
|------|-----------|--------------------|
| 0 | PLAN, repo, compose, CI, linters, BD+migraciones | lint+tests en verde; `alembic upgrade head` OK |
| 1 MVP | auth PIN segura, cursos, asientos, matrículas, vista de aula, entregas (archivos+GitHub), evaluación, tests de permisos | tests de permisos obligatorios en verde |
| 2 | secciones MD, tareas+fechas+versiones, visibilidad, admin, CSV, anuncios, AuditLog | lint+tests+compose+CHANGELOG |
| 3 | rúbricas, asistencia, calendario, GitHub meta, clonar, métricas, CSV, RGPD, UX/a11y | lint+tests+compose+CHANGELOG |

---

## 10. Seed de demo (script aparte, nunca en código de producción)

Curso "Java" 3×5 asientos, 1 profesora, 15 estudiantes, secciones de ejemplo
(HTML, CSS, Java, JS, Información externa). Comando: `make seed` /
`python -m scripts.seed_demo`.

---

## 11. Fase A (Super-admin multi-tenant) — IMPLEMENTADA Y MERGEADA

Registro de lo que ya existe en código (commit *"FASE A DE SUPER ADMIN"*).
Origen: [Super-admin-prompt.md](../1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md).
**Esta sección no propone cambios: documenta la Fase A tal como está.**

### 11.1 Modelo de datos añadido

- **`models/organization.py`** (nuevo):
  - `Organization`: `id`, `name str(200)`, `tax_id str(32)`,
    `billing_email str(320)`, `status` (index), `plan_id str(64)`,
    `stripe_customer_id str(64) UNIQUE NULL`,
    `stripe_subscription_id str(64) UNIQUE NULL`, `trial_ends_at timestamptz NULL`,
    `created_at`. Índices/únicos: `pk_organizations`,
    `uq_organizations_stripe_customer_id`, `uq_organizations_stripe_subscription_id`,
    `ix_organizations_status`.
  - `OrgStatus` (StrEnum): `pending_payment | trialing | active | past_due | canceled`.
    (`pending_payment`/`trialing`/`past_due`/`canceled` anticipan la Fase B-C de
    facturación; en la Fase A solo se usa `active`.)
- **`models/user.py`**:
  - `UserRole` ahora es `super_admin | org_admin | teacher | student`
    (el viejo `admin` desaparece; renombrado a `org_admin` en toda la API y FE).
  - Campos nuevos: `organization_id FK→organizations NULL` (índice),
    `activation_token_hash str(255) NULL` y
    `activation_token_expires_at timestamptz NULL` (columnas preparadas para la
    Fase B de activación por email; vacías en la Fase A).
  - Dos CHECK en `__table_args__` (los nombres los prefija la naming convention):
    - `ck_users_org_by_role`: `(role='super_admin' AND organization_id IS NULL)
      OR (role<>'super_admin' AND organization_id IS NOT NULL)` — solo
      `super_admin` carece de organización; todos los demás, obligatoria.
    - `ck_users_role_valid`: `role IN ('super_admin','org_admin','teacher','student')`
      — dominio cerrado de roles (SQLite no valida el tipo Enum a nivel BD, por
      eso el CHECK es necesario).
- **`models/course.py`**: `organization_id FK→organizations NOT NULL` + índice
  (`ix_courses_organization_id`).

### 11.2 Migración `e1a2b3c4d5f6` (revis. `d9a4b5c6e7f8`)

Paso a paso de `upgrade()`:

1. Crea la tabla `organizations` (+ 2 únicos de Stripe + `ix_organizations_status`).
2. Añade a `users` las 3 columnas nuevas **sin FK todavía** (SQLite no permite
   `ALTER ... ADD CONSTRAINT`; la FK entra en el batch del paso 5) +
   `ix_users_organization_id`.
3. Inserta la **organización por defecto** con SQL autocontenido:
   `name='Organización por defecto'`, `tax_id='000000000A'`,
   `billing_email = COALESCE(email del primer admin, 'admin@localhost')`,
   `status='active'`, `plan_id=''`.
4. **Backfill de roles y organización**:
   `UPDATE users SET role='org_admin' WHERE role='admin'` y
   `UPDATE users SET organization_id=<org> WHERE role<>'super_admin'`.
5. FK + enum de 4 roles + los 2 CHECK, **con manejo distinto por dialecto**:
   - **PostgreSQL**: `ALTER TYPE ... ADD VALUE` no puede ejecutarse dentro de una
     transacción → `create_foreign_key`, `ALTER TYPE userrole RENAME TO
     userrole_old`, crear el tipo nuevo con 4 valores, `ALTER COLUMN role TYPE
     userrole USING (CASE WHEN role='admin' THEN 'org_admin' ELSE role END)`,
     `DROP TYPE userrole_old` y crear los 2 CHECK con `create_check_constraint`.
   - **SQLite**: `batch_alter_table('users')` (recrea la tabla con los datos ya
     backfilleados): `alter_column role` al enum nuevo, `create_foreign_key` y
     los 2 CHECK dentro del batch. (Los nombres de CHECK se pasan **sin** el
     prefijo `ck_users_`: la naming convention de `Base.metadata` lo añade.)
6. `courses.organization_id`: `add_column` nullable → backfill a la org por
   defecto → `batch_alter_table` a `NOT NULL` + FK + `ix_courses_organization_id`.

`downgrade()` inverso y también probado: borra los `super_admin` (el esquema
monolítico antiguo no los admite), `org_admin → admin`, cae primero los 2 CHECK
antes del backfill inverso (porque `admin` ya no pertenece al dominio), revierte
el tipo `userrole` (misma bifurcación PG/SQLite), elimina las columnas y
`organizations` al final. **Verificado: upgrade → downgrade → upgrade** sobre una
copia de `dev.db` y sobre BD temporal; `dev.db` real está en `e1a2b3c4d5f6`
(3 usuarios + curso Java en la org 1).

### 11.3 CLI y helper

- **`scripts/create_admin.py`**: argparse con `--role {org_admin|super_admin}`
  (default `org_admin`), `--email`, `--password`, `--name`; fallback a las env
  vars `AULA_ADMIN_EMAIL` / `AULA_ADMIN_PASSWORD`. `org_admin` hereda la
  organización por defecto (se crea si no existe); `super_admin` nace con
  `organization_id=NULL`. **Único camino para crear `super_admin`**; es
  idempotente (si el email existe, no duplica).
- **`services/organization.py`** (nuevo): `get_or_create_default_organization(db,
  billing_email=None)` — devuelve la primera organización existente o crea la de
  por defecto (billing: parámetro → primer email de staff → `admin@localhost`).
  Lo usan el CLI, `seed_demo` y los tests.

### 11.4 Cambios en `policies.py` y `admin.py` respecto a `super_admin`

- **`security/policies.py`**:
  - `require_admin` exige `org_admin` → **`super_admin` recibe 403 en `/api/v1/admin/*`**.
  - `user_permissions`: `org_admin` → todos los permisos conocidos;
    `super_admin` → `[]` (permisos académicos fuera de su alcance en esta fase).
  - `can_read_submission`: `super_admin` cae a `return False` explícito
    (antes habría un `AssertionError` por rama inalcanzable).
  - `require_staff_of_course` / `require_enrolled`: `super_admin` no es
    `org_admin`/`teacher` ⇒ denegado (403 / 404 según la invariante).
- **`api/v1/routes/admin.py`**:
  - `create_user`: 403 si `body.role == super_admin` (mensaje "solo CLI");
    los usuarios creados heredan `organization_id = admin.organization_id`.
  - `update_user`: 403 si se intenta promover a `super_admin`.
  - `import_students_csv`: cada estudiante importado lleva
    `organization_id = admin.organization_id`.
  - (Coherente en el resto: `courses.create_course` usa la org del admin y
    `phase3.clone_course` copia la del curso origen.)

### 11.5 FUERA del alcance de la Fase A → condición de aceptación de la Fase C

**Ningún endpoint de `admin.py` filtra todavía por `organization_id`.** Es
intencional en la Fase A (el aislamiento por tenant completo es la Fase C), pero
queda escrito aquí como **requisito obligatorio de la Fase C** en:

- `list_users`, `update_user`, `reset_staff_password`, `set_user_status`,
  `reset_pin`, `import_students_csv`, `list_audit_logs`, `course_metrics`
  (además de `admin_dashboard` y las rutas de observador).
- **Rutas de cursos** (`courses.py` y `phase3.py`): listado, detalle, métricas,
  clonado, etc., tampoco recortan por `organization_id`.

Es decir: hoy un `org_admin` de la org 1 podría listar usuarios/cursos de otra
organización si existieran. En la Fase A solo existe la org por defecto, así que
no hay fuga real, pero **la Fase C debe añadir ese filtrado y sus tests de
aislamiento**.

### 11.6 Tests (`tests/test_saas_phase_a.py`, 8) y prueba de mutación

- `test_migration_backfill_and_downgrade` — crea una BD temporal en el esquema
  antiguo (`d9a4b5c6e7f8`), inserta datos crudos (admin/teacher/student/curso),
  migra a `head` y verifica org por defecto, `admin→org_admin`,
  `organization_id` backfilleado y los CHECK/FK en el DDL; después ejecuta el
  `downgrade` y verifica el esquema monolítico restaurado.
- `test_check_constraint_rejects_invalid_role_org_pairs` — `super_admin` con org
  ⇒ `IntegrityError`; `org_admin` sin org ⇒ `IntegrityError`; rol legacy `admin`
  ⇒ `IntegrityError`.
- `test_cli_create_org_admin_and_super_admin` — CLI con `SessionLocal`
  parcheado a BD temporal: `org_admin` con org, `super_admin` sin org,
  idempotencia y `billing_email` heredado.
- `test_get_or_create_default_organization_is_idempotent`.
- `test_super_admin_blocked_from_admin_api` — 403 en `/admin/dashboard` y
  `/admin/users`.
- `test_super_admin_cannot_be_created_or_promoted_via_api` — 403 en
  `POST /admin/users` y en `PATCH ... {"role": "super_admin"}`.
- `test_super_admin_has_no_academic_permissions` — `user_permissions → []`,
  `can_read_submission → False` (frente a `True` para el teacher).
- `test_created_users_inherit_admin_organization` — usuario y curso creados por
  un admin heredan su `organization_id`.

**Prueba de mutación realizada** (sabotaje → test en rojo → revertido):

1. Neutralizado el backfill de roles del paso 4 de la migración → la migración
   falla con `CHECK constraint failed: ck_users_role_valid` (el nuevo dominio de
   roles detecta el backfill roto).
2. Comentado el CHECK `org_by_role` del modelo → el test de constraints falla
   con `DID NOT RAISE IntegrityError`.

Ambos sabotajes detectados por la suite y revertidos.

**Gates de la fase**: backend `ruff + format + mypy + pytest --cov` →
**133 tests, 86,71 %**; frontend `lint + format + typecheck + test + build` →
**66 tests** (literales de rol `admin → org_admin` en guards, formularios, mocks
y `roleLabel`; `lib/api.ts` con `super_admin` en la unión de roles, sin rutas
nuevas).

---

## 12. Fase B (registro + Stripe Checkout + webhooks + EmailService + activación) — IMPLEMENTADA

**Estado: IMPLEMENTADA y con todos los gates en verde** (commit de la fase
pendiente de usuario). Origen: secciones 4, 5, 6 y 8 de
[Super-admin-prompt.md](../1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md).
Fuera de esta fase: CRUD de `superadmin/*` y aislamiento por organización →
Fase C; frontend y 2FA TOTP → Fase D.

### 12.1 Alcance (solo backend)

1. **Catálogo público de planes**: `GET /api/v1/public/plans` (sin auth) desde
   `app/services/plans.py` — catálogo **estático** de 3 planes (id, nombre,
   descripción, precio, `stripe_price_id` proveniente de Settings). **Sin tabla
   nueva** para los planes.
2. **Registro de organización**: `POST /api/v1/public/organizations`
   (`name`, `tax_id`, `billing_email`, `plan_id`) → crea
   `Organization(status=pending_payment)` **sin crear ningún `User`**, crea el
   cliente y la **Checkout Session** de Stripe con `mode="subscription"`,
   `trial_period_days=14`, `payment_method_collection="always"` (tarjeta por
   adelantado), `metadata={"organization_id": id}` y success/cancel URLs sobre
   `public_base_url`. Devuelve la `checkout_url`; la tarjeta se teclea en Stripe,
   nunca pasa por este backend.
3. **Webhook** `POST /api/v1/webhooks/stripe` (sin auth de usuario) con
   **verificación de firma obligatoria** (sección 6 del prompt):
   `stripe.Webhook.construct_event(payload, Stripe-Signature,
   settings.stripe_webhook_secret)` → en firma ausente, inválida o de otro
   `whsec_` ⇒ **400** y ningún efecto. Eventos y efectos:

   | Evento | Efecto |
   |---|---|
   | `checkout.session.completed` | `User(role=org_admin)` con `activation_token_hash` (hash del token aleatorio; **nunca** el valor en claro), `password_hash=NULL`; org → `trialing` + `trial_ends_at`; email de activación |
   | `customer.subscription.trial_will_end` | Email de aviso 3 días antes del fin del trial |
   | `invoice.payment_succeeded` | `Organization.status = active` |
   | `invoice.payment_failed` | `Organization.status = past_due` |
   | `customer.subscription.deleted` | `Organization.status = canceled` |

   **Idempotencia**: tabla nueva `stripe_webhook_events` (`event_id` único,
   `event_type`, `received_at`); un evento repetido responde 200 sin re-ejecutar
   (nunca crea un segundo `org_admin` ni reenvía el email).
4. **Activación de cuenta** (un solo uso, 48 h): `GET /api/v1/auth/activate`
   (valida el token y devuelve los datos a mostrar) y
   `POST /api/v1/auth/activate` `{token, password}` → `password_hash=argon2`,
   borra `activation_token_hash/expires_at` (uso único). Token expirado o ya
   consumido ⇒ 4xx.
5. **Login con `password_hash IS NULL`** ⇒ rechazo **explícito con 401** (sin
   llegar a `verify_password`) + registro en AuditLog: la cuenta creada por el
   webhook no puede autenticarse hasta activarse.
6. **`EmailService` abstracto** (`app/services/email.py`, interfaz para cambiar
   de proveedor sin tocar el resto) + **`ResendEmailService`** (REST de Resend
   vía `httpx`). Sin `resend_api_key` en desarrollo ⇒ el enlace de activación se
   **loguea** (nunca fallo silencioso; en `production` la clave es obligatoria).
7. **Limpieza de `pending_payment`**: `python -m
   scripts.cleanup_pending_organizations` — borra organizaciones en
   `pending_payment` con más de 7 días (CLI para cron en producción; el repo no
   tiene scheduler).
8. **Config**: campos nuevos en `Settings` + `.env.example` con placeholders; si
   `environment == "production"`, `stripe_secret_key`, `stripe_webhook_secret` y
   `resend_api_key` **deben existir y no ser el placeholder de desarrollo**
   (validación al arrancar, con test).

### 12.2 Fuera de alcance de la Fase B

- `/api/v1/superadmin/*` (CRUD de Organization, métricas agregadas) → **Fase C**.
- Filtrado por `organization_id` en `admin.py`/`courses.py`/`phase3.py` →
  **Fase C** (condición no negociable, ver 11.5).
- Frontend (`/precios`, `/registro-empresa`, `/activar-cuenta/:token`,
  redirección por rol) y 2FA TOTP de `super_admin` → **Fase D**.
- La Fase A **no se toca**: migración `e1a2b3c4d5f6`, CLI y CHECKs quedan como
  están.

### 12.3 Modelo, dependencias y configuración nuevos

- **Migración nueva** (con `downgrade`) únicamente para la tabla
  `stripe_webhook_events`. `Organization` y `User` **no cambian**: estados,
  `trial_ends_at` y los campos de token de activación ya existen desde la
  Fase A (11.1).
- **Dependencias**: añadir `stripe` a `dependencies` y **promover `httpx` de
  `dev` a runtime** (`services/github_meta.py` ya lo importa; hoy solo está en
  extras de desarrollo) para Resend.
- **Settings nuevos** (dev: vacío/placeholder): `stripe_secret_key`,
  `stripe_webhook_secret`, `stripe_price_*` (un Price por plan),
  `resend_api_key`, `email_from`, `public_base_url`.
  Producción: los tres secretos obligatorios y no-placeholder (ver 12.1.8).

### 12.4 Tests de la fase (`tests/test_saas_phase_b.py`) y prueba de mutación

- Webhook **sin firma** → 400, no crea `User` ni cambia ningún
  `Organization.status`.
- Webhook con firma de un **`whsec_` distinto** → 400, mismo "no efecto".
- Evento con `event_id` **duplicado** → idempotencia (un solo efecto).
- Flujo feliz: registro → `pending_payment` sin `User` → webhook →
  `trialing` + `org_admin` con token y `password_hash=NULL`.
- **Login de esa cuenta → 401** (rechazo explícito, AuditLog).
- Activación: token válido OK; **token reusado → 4xx**; **token con más de
  48 h → 4xx**.
- `super_admin` → **403/404** en rutas de `Submission`, `Evaluation` y
  `CourseMessage` **con la URL construida a mano** (no enlazada).
- `Settings` en `production` con placeholder de secreto → error de validación.
- Cleanup: borra `pending_payment` > 7 días y **no** borra `trialing` ni
  organizaciones con usuarios.
- **Prueba de mutación de la Fase B (REALIZADA)**: sabotaje en
  `routes/webhooks.py` — el `except` de la verificación de firma pasó a
  `pass` (se acepta cualquier payload). Resultado, en rojo:

  ```text
  FAILED tests/test_saas_phase_b.py::test_webhook_without_signature_returns_400_and_changes_nothing
  FAILED tests/test_saas_phase_b.py::test_webhook_rejects_signature_from_another_secret
  FAILED tests/test_saas_phase_b.py::test_webhook_rejects_garbage_payload_with_valid_signature
  E   assert 200 == 400   (+ where 200 = <Response [200 OK]>.status_code)
  3 failed, 13 deselected
  ```

  Revertido el sabotaje → **16/16 en verde**. La suite detecta la ausencia
  de verificación de firma: sin ella, un POST sin firma o firmado con la
  clave de otro secreto, iría a 200 y procesaría el evento.

### 12.5 Entorno local (documentado en COMANDOS_DE_LA_APP.md)

- Claves **solo test** (`sk_test_`/`pk_test_`); nunca claves de producción.
- `stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe` → el
  `whsec_` del tunnel va a `STRIPE_WEBHOOK_SECRET` del `.env` local;
  `stripe trigger checkout.session.completed` para disparar eventos de prueba.
- El `whsec_` local (tunnel) **≠** el de producción (dashboard): es una variable
  por entorno, jamás un valor fijo en código.
- Resend en modo prueba: entrega en bandeja real sin dominio verificado
  (remitente por defecto `onboarding@resend.dev`).

### 12.6 Gates para cerrar la Fase B — RESULTADO

- `ruff check .` → **All checks passed**; `ruff format --check .` →
  **97 files already formatted**; `mypy app` → **no issues (72 files)**.
- `pytest --cov=app --cov-fail-under=80` → **149 tests, 86.50 %**
  (Fase A: 133/86.71 %; los 16 nuevos viven en `test_saas_phase_b.py`;
  módulos nuevos: `email.py` y `plans.py` al 100 %, `activation.py` 90 %,
  `stripe_webhooks.py` 73 %).
- Migración `f4e5d6c7b8a9` aplicada a `dev.db` (`alembic current` → head).
- Frontend sin cambios: `npm run lint` y `npm run test` → **66 tests**.
- **Mutación de firma: en rojo y revertida** (evidencia en 12.4).
- Entrada en `CHANGELOG.md` (`## [Fase B SaaS] — 2026-09-26`).

**Siguiente: Fase C** (aislamiento por `organization_id` + rutas
`/superadmin/*`) — condición no negociable descrita en 11.5, con sus tests
de aislamiento cruzado y su propia prueba de mutación.

---

## 13. Fase C (aislamiento multi-tenant de todas las rutas + `/superadmin/*`) — PLAN

**Estado: IMPLEMENTADA (2026-09-28).** Evidencia de gates y mutaciones al
final de la sección (13.4 y 13.6). Resumen ejecutivo en
[TRABAJO_REALIZADO_EN_SUPER_ADMIN.md](../PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md).
Origen: secciones 6 (invariantes), 7 (rutas),
8 (tests) y 9 (definición de Fase C) de
[Super-admin-prompt.md](../1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md) +
condición no negociable de 11.5. Frontend y 2FA TOTP de super_admin → Fase D.

### 13.1 Alcance

1. **Invariante central**: toda query de `org_admin` filtra por
   `organization_id == user.organization_id`; un recurso de otra organización
   responde **404, nunca 403** (no se revela su existencia). `super_admin`
   sigue sin ver datos académicos (Fase A) y tendrá sus rutas propias.
2. **Choke points nuevos en `app/security/policies.py`** (cubren casi todas las
   rutas desde un solo sitio):
   - `_ensure_course_org(user, course)` → 404 si
     `course.organization_id != user.organization_id`. Se llama **dentro** de
     `get_course_or_404`, `require_staff_of_course` y `require_enrolled` —
     estas dos se invocan también como llamada directa con `_get_course`
     locales (`courses.py`, `announcements.py`, `sections.py`, `work.py`), así
     que el check va en la función, no solo en la dependencia `Depends`.
     Super_admin (`organization_id IS NULL`) no entra por aquí: los deps de
     staff/teacher ya lo bloquean como hoy.
   - `ensure_same_org(user, resource_org_id, detail)` → 404: para todos los
     `db.get(User|CourseCategory|Cohort|CustomRole)` con id de path.
   - `can_read_submission`: la rama `org_admin` pasa a exigir que la entrega
     pertenezca a un curso de su organización (cubre `GET /submissions/{id}`
     y `GET /submissions/{id}/github-meta`).
   - `require_super_admin(user)`: solo `UserRole.super_admin` (org_admin y
     demás → 403).
   - Guards inline se auditan y refuerzan con lo anterior:
     `course_chat._assert_course_member`, los checks de `messages.py` y
     `calendar_inst.py`, y los `_get_course` locales de `admin.py`
     (`import-students`, `metrics`).
3. **Inventario completo de endpoints a re-acotar (los 5 ficheros admin, 65
   endpoints; se listan también los que NO cambian)**:

#### `routes/admin.py` (12)

| Ruta | Scoping |
|---|---|
| `GET /admin/users` | `where(User.organization_id == admin.organization_id)` |
| `POST /admin/users` | sin cambio (ya hereda `organization_id=admin.organization_id`) |
| `PATCH /admin/users/{user_id}` | `ensure_same_org` → 404 |
| `POST /admin/users/{user_id}/reset-password` | `ensure_same_org` → 404 |
| `PATCH /admin/users/{user_id}/status` | `ensure_same_org` → 404 |
| `POST /admin/users/{user_id}/reset-pin` | `ensure_same_org` → 404 |
| `POST /admin/courses/{course_id}/import-students` | org del curso → 404 (check manual, hoy `db.get` a secas) |
| `GET /admin/audit-logs` | JOIN: solo logs cuyo `actor` es usuario de la org (sin columna nueva) |
| `GET /admin/metrics/course/{course_id}` | org del curso → 404 |
| `GET /admin/dashboard` | todos los KPIs + `recent_audit` + `recent_submissions` filtrados por org (JOIN por actor/curso) |
| `GET /admin/observer/submissions` | `Submission.course_id` ∈ cursos de la org |
| `GET /admin/observer/evaluations` | idem vía `Submission → Course` |

#### `routes/courses.py` (17)

| Ruta | Scoping |
|---|---|
| `GET /courses` | rama org_admin: `where(Course.organization_id == user.organization_id)` |
| `POST /courses` | ya hereda org; `Course.code` pasa a único **por org** (13.3) |
| `GET /courses/{course_id}` | choke (course org → 404) |
| `PATCH /courses/{course_id}` | choke |
| `GET /courses/{course_id}/classroom` | choke |
| `GET /courses/{course_id}/seats` | choke |
| `GET /courses/{course_id}/enrollments` | choke |
| `POST /courses/{course_id}/enrollments` | choke + `ensure_same_org(student)` |
| `PATCH /courses/{course_id}/enrollments/{enrollment_id}/seat` | choke |
| `GET /courses/{course_id}/enrollments/me` | sin cambio (consulta por `user.id`) |
| `DELETE /courses/{course_id}/enrollments/{enrollment_id}` | choke |
| `POST /courses/{course_id}/teachers/{teacher_id}` | choke + `ensure_same_org(teacher)` |
| `DELETE /courses/{course_id}/teachers/{teacher_id}` | choke |
| `GET /me/courses` | hereda de `list_courses` (la rama org_admin queda scoping) |
| `GET /courses/{course_id}/overview` | choke |
| `GET /courses/{course_id}/students/{student_id}` | choke (el student ya se valida por matrícula del curso) |
| `GET /courses/{course_id}/my-progress` | sin cambio (personal; la rama org_admin queda cubierta por el choke en `require_enrolled`) |

#### `routes/phase3.py` (6)

| Ruta | Scoping |
|---|---|
| `POST /courses/{course_id}/clone` | choke + el clon pasa a `organization_id=admin.organization_id` (hoy se queda en la del origen) |
| `GET /courses/{course_id}/export/grades.csv` | choke |
| `GET /submissions/{submission_id}/github-meta` | vía `can_read_submission` con org |
| `GET /me/export` | sin cambio (personal) |
| `DELETE /me/data` | sin cambio (personal) |
| `DELETE /admin/users/{user_id}/data` | `ensure_same_org` → 404 (hoy anonimiza usuarios ajenos) |

#### `routes/phase_c.py` (7)

| Ruta | Scoping |
|---|---|
| `GET /admin/dashboard/multi` | `where(Course.organization_id == …)` |
| `GET /courses/{course_id}/gradebook` | choke |
| `GET /admin/settings` | fila por `(key, organization_id)` (13.3) |
| `PUT /admin/settings` | idem (hoy una org pisa la fila global de todas) |
| `GET /admin/reports/overview` (+ `.csv`) | filtro por org dentro del helper compartido |
| `GET /courses/{course_id}/backup` | `ensure_same_org(course)` → 404 (usa `require_admin` a secas) |

#### `routes/phase_d.py` (22)

| Ruta | Scoping |
|---|---|
| `GET /categories` | `where(org)` + `course_count` solo de la org |
| `POST /admin/categories` | `organization_id=admin.organization_id`; slug único **por org** |
| `PATCH`/`DELETE /admin/categories/{category_id}` | `ensure_same_org(category)` → 404 |
| `PATCH /admin/courses/{course_id}/taxonomy` | choke + category/cohort de la misma org → 404 |
| `GET`/`POST /admin/cohorts` | org; `code` único **por org** |
| `GET`/`DELETE /admin/cohorts/{cohort_id}` | `ensure_same_org(cohort)` → 404 |
| `POST /admin/cohorts/{cohort_id}/members` | `ensure_same_org(cohort)` + `ensure_same_org(student)` |
| `DELETE /admin/cohorts/{cohort_id}/members/{student_id}` | idem |
| `POST /courses/{course_id}/auto-enroll` | choke + cohort de la misma org del curso |
| `GET /admin/permissions` | sin cambio (catálogo estático, sin BD) |
| `GET /auth/permissions` | sin cambio (personal) |
| `GET`/`POST /admin/roles` | org; name único **por org**; `assigned_count` solo de la org |
| `PATCH`/`DELETE /admin/roles/{role_id}` | `ensure_same_org(role)` → 404 |
| `POST /admin/users/{user_id}/custom-role` | `ensure_same_org(user)` + `ensure_same_org(role)` |
| `GET /admin/sessions` | JOIN `User.organization_id == admin.organization_id` |
| `POST /admin/sessions/revoke` | `ensure_same_org(user)` |
| `POST /admin/users/{user_id}/unlock` | `ensure_same_org(user)` |

Ficheros no listados (`announcements`, `sections`, `work`, `rubrics`,
`attendance`, `calendar`, `student`, `teacher`): heredan la protección de los
choke points de `policies.py`; solo se auditan sus llamadas directas.

4. **Rutas nuevas `/api/v1/superadmin/*`** — `routes/superadmin.py` +
   `schemas/superadmin.py` (hoy **no existe** ningún schema de salida de
   `Organization`), con `require_super_admin`:

   | Método y ruta | Qué hace | Errores |
   |---|---|---|
   | `GET /superadmin/organizations` | Lista orgs con `status`, `plan_id`, ids de Stripe, `trial_ends_at` + contadores de usuarios/cursos; filtros `status`/`q` | — |
   | `GET /superadmin/organizations/{org_id}` | Detalle de una org | 404 |
   | `POST /superadmin/organizations` | Alta manual (enterprise, sin Checkout) con `status` en el payload (default `active`) | 201 / 409 email duplicado |
   | `PATCH /superadmin/organizations/{org_id}` | `name`/`tax_id`/`billing_email`/`plan_id`/`status` (el dueño de la plataforma gestiona estados a mano) | 404 |
   | `DELETE /superadmin/organizations/{org_id}` | Solo si la org **no tiene usuarios ni cursos** (org vacía); protegida frente a borrados masivos | 204 / 409 con detalle |
   | `GET /superadmin/subscriptions` | Filas de suscripción: customer/subscription de Stripe, estado, plan, trial | — |
   | `GET /superadmin/metrics` | Agregados **sin datos académicos**: orgs por estado y plan, usuarios por rol, total de cursos, trials que terminan en ≤7 días | — |

   `super_admin` **no** recibe endpoints de AuditLog ni de
   Submission/Evaluation/CourseMessage (compromiso de producto). Org_admin →
   403 en todas las rutas `/superadmin/*` (y super_admin sigue recibiendo 403
   en `/admin/*`, ya cubierto por tests de Fase A/B).

### 13.2 Fuera de alcance de la Fase C

- Frontend (`/precios`, `/registro-empresa`, `/activar-cuenta/:token`,
  rutas por rol, panel de super_admin) y **2FA TOTP** → **Fase D**.
- Datos académicos para super_admin, reset de contraseñas de org_admin desde
  `/superadmin`, exportaciones masivas → fuera del alcance pedido.
- La Fase A y la Fase B **no se tocan** (migraciones `e1a2b3c4d5f6` y
  `f4e5d6c7b8a9` quedan como están; la de la Fase C se apila encima).

### 13.3 Modelo, migración y configuración

- **Migración nueva** (revisión tras `f4e5d6c7b8a9`, con downgrade):
  - Columna `organization_id` (FK → `organizations`, backfill a la
    organización por defecto, después NOT NULL) en **4 tablas hoy globales**:
    `course_categories`, `cohorts`, `custom_roles`, `system_settings`.
    `batch_alter_table` en SQLite + rama PostgreSQL, como las migraciones
    anteriores.
  - `system_settings`: la PK pasa de `key` a `(key, organization_id)`
    (ajustes del centro **por** organización).
  - Unicidades globales → compuestas: `slug` de categorías, `code` de
    cohorts, `name` de roles y `courses.code` pasan a ser únicos **dentro de
    una organización** (hoy un código de curso repetido en otra org daba 409
    y revelaba su existencia). Mismo-org sigue dando 409 (los tests
    existentes se mantienen en verde).
  - `audit_logs`: **sin columna nueva** — el filtro de `GET /admin/audit-logs`
    es un JOIN por el `actor` de la organización (todo log de org tiene actor
    de esa org).
  - Nota: el esquema de los tests se crea con `Base.metadata.create_all`, así
    que las 4 tablas llevan un default de seguridad en el modelo para las
    inserciones directas que ya hacen los tests (org id 1 = org por defecto);
    verificar que los tests existentes de settings/categories/cohorts/roles
    siguen en verde.
- **Schemas nuevos**: `app/schemas/superadmin.py` (`OrganizationAdminPublic`,
  `OrganizationCreate/Update`, `SubscriptionRow`, `PlatformMetrics`).
- **Config**: sin secretos ni env vars nuevos (Fase C no toca `.env`).

### 13.4 Tests de la fase (`tests/test_saas_phase_c.py`) y prueba de mutación

Aislamiento con **dos organizaciones** — la prueba principal crea las dos orgs
**mediante el flujo real de la Fase B** (registro público + webhook firmado +
activación de las dos cuentas `org_admin`); el resto de tests usa el patrón de
orgs creadas directamente en `db` (barato):

1. `test_cross_org_isolation_via_real_registration_flow` — matriz amplia: el
   org_admin A no lista ni lee usuarios/cursos de B (404/ausencia) con las dos
   orgs nacidas del flujo real.
2. `test_org_admin_users_list_scoped_to_own_org` — `GET /admin/users`.
3. `test_org_admin_cannot_modify_user_of_other_org` — PATCH user, status,
   reset-password, reset-pin, unlock, custom-role, DELETE data → 404.
4. `test_org_admin_audit_logs_scoped_to_own_org`.
5. `test_org_admin_dashboard_observer_and_reports_scoped` — KPIs distintos
   por org; observer sin entregas ajenas.
6. `test_org_admin_cannot_touch_other_org_courses` — GET/PATCH, clone,
   backup, gradebook, metrics, import-students, taxonomy, auto-enroll,
   enrollments, teachers → 404; `GET /courses` sin cursos ajenos.
7. `test_course_code_and_catalogs_unique_per_org` — mismo `code`/`slug`/
   `name` en dos orgs → 201 en ambos; repetido en la misma org → 409.
8. `test_cross_org_student_and_teacher_assignment_blocked` — matricular alumno
   de B en curso de A, añadir profesor de B, miembros de cohort → 404.
9. `test_settings_isolated_between_orgs` — PUT en A no cambia el GET de B.
10. `test_sessions_list_revoke_scoped` — solo sesiones/usuarios propios.
11. `test_org_admin_cannot_read_academic_content_of_other_org` —
    `GET /submissions/{id}`, `github-meta` y `POST /courses/{id}/chat` de otra
    org → 404.
12. `test_super_admin_organization_crud` — crear/listar/patch/borrar org
    vacía; borrar org con usuarios → 409; id inexistente → 404.
13. `test_super_admin_subscriptions_and_metrics_no_academic_data` — métricas
    correctas y **sin claves** de submissions/evaluations/messages (assert
    explícito de claves prohibidas).
14. `test_super_admin_role_boundaries` — org_admin → 403 en todos los
    `/superadmin/*` (parametrizado); super_admin → 403 en `/admin/*`.

- **Prueba de mutación (2 sabotajes, evidencia pegada)**:
  a) quitar el `where(User.organization_id == …)` de `GET /admin/users` →
  el test 2 **debe fallar** → **EJECUTADA: `2 failed, 12 passed`**
  (`test_org_admin_users_list_scoped_to_own_org` +
  `test_cross_org_isolation_via_real_registration_flow`) → revertida.
  b) sabotear `_ensure_course_org` → **EJECUTADA: `2 failed, 12 passed`**
  (`test_org_admin_cannot_touch_other_org_courses` con
  `assert 200 == 404` en línea 478 + `test_cross_org_isolation_via_real_registration_flow`)
  → revertida. **Desviación respecto al plan**: se previó sabotear solo el
  `_ensure_course_org` de `require_staff_of_course`, pero al ejecutar la
  mutación **no falló ningún test** (`14 passed`): el check está
  enmascarado porque `CurrentCourse` (`get_course_or_404`) y
  `require_enrolled` repiten el mismo guard (refuerzo en 3 sitios). La
  mutación se reorientó al **choque compartido `_ensure_course_org`**, que
  sí es load-bearing. El test 11 no cae con (b) porque sus guards son
  `can_read_submission`/`_assert_course_member` (codepaths distintos de
  `_ensure_course_org`), y esos guards ya demuestran su 404 en el propio
  test 11.
- Riesgo conocido: los **149 tests existentes** debían seguir en verde →
  **cumplido** (solo hubo que actualizar `MIGRATION_HEAD` en
  `test_saas_phase_a.py`, que fija el head de alembic por constante).

### 13.5 Entorno local

- Sin cambios de entorno: solo aplicar la migración en local con
  `ALEMBIC_DATABASE_URL="sqlite:///./dev.db" alembic upgrade head`.

### 13.6 Gates para cerrar la Fase C — ✅ TODOS EN VERDE (2026-09-28)

- ✅ `ruff check .` → `All checks passed!`; `ruff format --check .` →
  `100 files already formatted`; `mypy app` → `Success: no issues found
  in 74 source files`.
- ✅ `pytest --cov=app --cov-fail-under=80` → **163 passed · 86.75 %**
  (149 existentes + 14 nuevos de `tests/test_saas_phase_c.py`).
- ✅ Migración aplicada a `dev.db`: `alembic current` →
  `c7d8e9f0a1b2 (head)`; roundtrip `upgrade → downgrade → upgrade`
  verificado (uniqueness indexes + PK compuesta correctos).
- ✅ Frontend sin cambios: `npm run lint` en verde + `npm run test` →
  **66 passed**.
- ✅ Las 2 mutaciones en rojo y revertidas con la evidencia en 13.4.
- ✅ Entrada nueva en `CHANGELOG.md` (`## [Fase C SaaS] — 2026-09-28`).
- ✅ Este PLAN mostrado → **parar antes de la Fase D**.

---

## 14. Fase D (frontend por rol + registro/activación + 2FA de super_admin) — IMPLEMENTADA

**Estado: IMPLEMENTADA (2026-09-28).** Evidencia de gates y mutación al
final de la sección (14.4 y 14.6). Origen: sección 9 (definición de
Fase D) y 7 (rutas) de
[Super-admin-prompt.md](../1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md).
Asumida con el "aplica la fase D" del usuario. Resumen ejecutivo en
[TRABAJO_REALIZADO_EN_SUPER_ADMIN.md](../PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md).

### 14.1 Alcance — qué hace esta fase

Backend (lo mínimo que falta; el flujo público/activación ya existe de la
Fase B):

1. **TOTP (RFC 6238) sin dependencias nuevas**: `app/services/totp.py` con
   `secrets`/`hmac`/`hashlib`/`base64` de stdlib →
   `generate_secret()` (20 bytes → base32), `totp_code(secret, at)`,
   `verify_totp(secret, code, window=±1)` y `otpauth_url(...)`. Se comprueba
   con los **vectores oficiales del RFC 6238** (SHA-1, T=59 → `94287082`,
   T=1111111109 → `07081804`, …).
2. **Modelo + migración `d8e9f0a1b2c3`**: columnas en `users`
   `mfa_secret` (String(64) nullable) y `mfa_enabled` (Boolean NOT NULL
   default false). Sin secretos en Settings (el secreto TOTP es del
   usuario, no de despliegue).
3. **Login de `super_admin` exige siempre 2FA** (spec §7: "super_admin
   requiere 2FA por TOTP… solo para este rol en esta fase"):
   - `POST /auth/login/staff` con credenciales válidas de un
     `super_admin` → **NO emite tokens**: devuelve
     `StaffLoginResponse{access_token:"", mfa_required:true, mfa_token(JWT
     type=mfa, exp 5 min), mfa_enrolled}`. El resto de roles mantiene
     `TokenResponse` exactamente igual (regresión cubierta por tests
     existentes).
   - `POST /auth/mfa/setup` `{mfa_token}` → genera y guarda el secreto
     pendiente (`mfa_enabled=false`), devuelve `secret` + `otpauth_url`
     (el usuario lo introduce a mano en su app; **sin QR** — se evita una
     dependencia nueva). 409 si ya está activo.
   - `POST /auth/mfa/verify` `{mfa_token, code}` → valida TOTP con
     ventana ±1; si estaba pendiente lo **activa**; emite los tokens
     reales (cookie refresh incluida) → `TokenResponse`. Si ya estaba
     activo, solo verifica. Código malo → 401 + `record_failed_login`
     (`reason=mfa_failed`) → **lockout a los 5 intentos → 429**
     (reutiliza `_is_locked`/`MAX_FAILED_ATTEMPTS`); token inválido/
     caducado/otro propósito → 401 sin efectos.
   - `POST /auth/mfa/disable` `{code}` (sesión `super_admin`) → 204,
     borra secreto + flag; auditoría `auth.mfa_disabled`.
   - `GET /auth/me` (`UserPublic`) expone `mfa_enabled` para que el
     panel sepa el estado sin endpoint extra.
   - **Recuperación**: si se pierde el dispositivo, un CLI/rollback de BD
     es la vía (documentado; fuera de alcance generar códigos de
     respaldo).
4. `login_staff` con MFA pendiente/activo **no** registra
   `auth.login_success` hasta completar el verify (audita
   `auth.mfa_challenge` en su lugar).

Frontend (rutas de spec §7):

| Ruta | Qué es | Detalle |
|---|---|---|
| `/precios` | pública | `GET /public/plans` → 3 tarjetas (nombre, precio, descripción, máx. cursos) + CTA "Registra tu empresa" → `/registro-empresa?plan=<id>` |
| `/registro-empresa` | pública | form (nombre, NIF/CIF, email, plan) → `POST /public/organizations` → `redirectToCheckout(checkout_url)` (helper en `lib/checkout.ts`, testeable con spy). Errores 409/502/503 traducidos |
| `/activar-cuenta/:token` | pública | `GET /auth/activate?token=` → muestra el email + form contraseña (confirmación) → `POST /auth/activate` → éxito con enlace a `/login`; token inválido → 400 explicado |
| `/plataforma/acceso` | no enlazada públicamente | login `super_admin`: email+contraseña → `mfa_required` → **setup** (muestra secreto + otpauth, input de código) o **verify** según `mfa_enrolled` → `setSession` → `/plataforma` |
| `/login` (staff) | existente | si la respuesta trae `mfa_required` → navega a `/plataforma/acceso` con `state={mfa_token,mfa_enrolled}` (una sola UI de MFA) |
| `/plataforma` | panel | `RequireSuperAdmin` + `SuperAdminLayout`: índice de métricas (`/superadmin/metrics`), organizaciones (tabla + filtros `status`/`q` + crear/editar/borrar con confirm), suscripciones, y 2FA (estado + disable) |

- **Redirección por rol** (`homePath.ts`): `super_admin → /plataforma`,
  `org_admin → /admin` (antes `/`), `teacher → /teacher`,
  `student → /student`.
- **Guards** en `routes.tsx`: `RequireSuperAdmin` (rol distinto → `/`);
  el resto de guards existentes sin cambios.
- **Nav** (`layout.tsx`): sin sesión → enlace "Precios"; `super_admin`
  autenticado → solo "Plataforma" + "Mi cuenta" + "Salir" (oculta
  Cursos/Calendario/Mensajes/Privacidad, que para él son enlaces rotos);
  el resto de roles sin cambios.

### 14.2 Fuera de alcance de la Fase D

- QR de otpauth (se muestra el secret copiable), 2FA para otros roles,
  códigos de recuperación, emails nuevos, Stripe real en dev.
- Cambios de API de Fases A–C salvo los descritos arriba.

### 14.3 Modelo de datos y migración

- `users.mfa_secret` (String(64) nullable) + `users.mfa_enabled`
  (Boolean NOT NULL, `server_default` false) → migración `d8e9f0a1b2c3`
  (revisión `c7d8e9f0a1b2`), downgrade `drop_column` ×2. En SQLite se
  añaden columnas planas (sin FK), no hace falta `batch_alter_table`.
- Los tests usan `create_all` → defaults en el modelo.

### 14.4 Tests de la fase (`backend/tests/test_saas_phase_d.py`)

1. Vectores RFC 6238 + drift ±1 ventana (fuera de ventana → false).
2. `login_staff` de `super_admin` → `mfa_required=true` + `mfa_token`,
   **sin** access_token usable; `org_admin`/`teacher` → `TokenResponse`
   normal (regresión).
3. Flujo completo: setup → verify con código correcto → tokens →
   `GET /auth/me` funciona y `mfa_enabled=true`; segundo login → ya sin
   `setup`.
4. Verify con código inválido → 401 y **sin** token; 5 fallos → 429
   (lockout); `mfa_token` basura/caducado/`type != mfa` → 401.
5. Fronteras: `setup` con `mfa_token` de un `org_admin` → 401; endpoints
   de sesión `mfa/*` con rol distinto de `super_admin` → 403; `disable`
   con código correcto → 204 y el siguiente login exige setup otra vez.
6. Login de `super_admin` **sin** 2FA configurado nunca entrega tokens
   hasta completar verify (imposible saltarse el segundo factor).

- **Prueba de mutación**: sabotear `login_staff` para que no imponga el
  challenge (`mfa_required` siempre false) → el test 2 debe fallar.
  **Ejecutada (2026-09-28)**: `if False and user.role is UserRole.super_admin`
  en `auth_service.py` → `pytest tests/test_saas_phase_d.py` →
  **`4 failed, 10 passed`** (challenge, flujo completo, lockout y
  setup/verify/disable de sesión; los vectores TOTP y las fronteras de rol
  siguen en verde, como corresponde). Revertida → **`14 passed`**.

### 14.5 Tests frontend (Vitest)

- `PreciosPage`: renderiza los 3 planes y el CTA con el plan preseleccionado.
- `RegistroEmpresaPage`: envía el POST correcto y llama a
  `redirectToCheckout`; error 409 traducido.
- `ActivarCuentaPage`: token inválido → error; éxito → confirmación.
- `PlatformAccessPage`: password → `mfa_required` → setup con código →
  `setSession` + navegación a `/plataforma`.
- `SuperAdmin.test.tsx`: métricas + organizaciones (mock fetch) y
  redirección de `/plataforma` con rol no super_admin.
- `routes.test.tsx` ampliado: `/precios` pública, `/activar-cuenta/:token`
  y `/plataforma/acceso` sin sesión.

### 14.6 Gates para cerrar la Fase D

- [x] Backend: `ruff check` + `ruff format --check` + `mypy app` en verde
  (102 ficheros, 75 módulos); `pytest --cov=app --cov-fail-under=80` →
  **177 passed · 87.11 %** (163 existentes + 14 nuevos de
  `tests/test_saas_phase_d.py`; `app/services/totp.py` al 100 %).
- [x] Migración `alembic upgrade head` en `dev.db` +
  roundtrip `downgrade -1 → upgrade head` → `d8e9f0a1b2c3 (head)`.
- [x] Frontend: `npm run lint` + `npm run format:check` + `npm run typecheck`
  + `npm run test` en verde (66 existentes → **85 tests**; los 18 nuevos
  cubren §14.5 y los flujos de 2FA).
- [x] Mutación de 14.4 en rojo con evidencia y revertida (4 failed → 14
  passed).
- [x] Entrada nueva en `CHANGELOG.md` (`## [Fase D SaaS]`) y actualización de
  [TRABAJO_REALIZADO_EN_SUPER_ADMIN.md](../PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md).

**Siguiente**: no queda Fase definida en `Super-admin-prompt.md`; pendientes
heredados en el informe (WebSocket, emails solo de activación, QR de 2FA).
