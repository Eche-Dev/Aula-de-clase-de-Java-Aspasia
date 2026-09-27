# Archivos del proyecto — qué hace cada uno

> Índice de toda la documentación con enlaces relativos (funcionan en GitHub y en el editor).

## Carpeta `Archivo_Markdown/`

## 1. [prompt_Claude_PrimerasFases.md](PROMPT_INICIAL/prompt_Claude_PrimerasFases.md) · `PROMPT_INICIAL/`

El contrato de trabajo (briefing). Es el prompt/instrucciones que se dieron a la IA al empezar: rol (ingeniero senior full stack), contexto del producto (aula Java 3×5 con profesora al frente), stack prohibido de cambiar, modelo de datos, matriz de permisos, requisitos de seguridad (PIN+argon2, rate limiting), funcionalidad por pantalla (10 pantallas), UX/a11y, tests obligatorios (criterios de aceptación) y las fases 0–3 con reglas ("no avanzar de fase sin tests verdes", "documentar en español, código en inglés"). Transmite: cómo se debía construir la app y qué condiciones había que cumplir.

- **De él salen**: el plan técnico [PLAN_CLAUDE.md](PLAN/PLAN_CLAUDE.md) y el roadmap de módulos que luego ejecutaron [PLAN_ADMIN.md](PLAN/PLAN_ADMIN.md), [PLAN_PROFESOR.md](PLAN/PLAN_PROFESOR.md) y [PLAN_ALUMNO.md](PLAN/PLAN_ALUMNO.md).

## 2. [PLAN_CLAUDE.md](PLAN/PLAN_CLAUDE.md) · `PLAN/`

El plan técnico (arquitectura y decisiones). La contraparte ejecutada del prompt: stack verificado con versiones reales, 14 decisiones tomadas ante ambigüedades (D1 Python 3.14 local vs 3.12 CI, D6 el profe no tiene asiento, D8 evaluaciones inmutables…), esquema de datos completo, matriz de permisos con 7 invariantes de seguridad, estructura de carpetas, superficie API por fase, seguridad transversal, calidad/CI y las fases 0–3. Transmite: las decisiones de arquitectura y por qué, para que nadie las reabra sin motivo.

- **Origen**: [prompt_Claude_PrimerasFases.md](PROMPT_INICIAL/prompt_Claude_PrimerasFases.md) · **Decisiones en ejecución**: [CHANGELOG.md](../CHANGELOG.md).

## 3. [PLAN_ADMIN.md](PLAN/PLAN_ADMIN.md) · `PLAN/`

El plan del módulo admin (fases A–D). Reconstrucción/documento del plan con el que se ejecutó el módulo admin, en el mismo formato que los otros dos planes: contexto y "conexiones del rol", 9 decisiones de diseño (D-A1 layout/rutas `/admin` con `RequireAdmin` como patrón que luego calcaron profesor y alumno, D-A3 un archivo por responsabilidad, D-A5 auditoría, D-A6 RGPD by design, D-A7 permisos por capas con `require_permission`, D-A8 in-app sin WebSocket/email, D-A9 migraciones Alembic por fase), inventario de lo reutilizado (Fases 0–3) frente a lo creado, detalle de las 4 fases (A "cerrar API sin UI" → D "escala"), verificación por fase (87→105 tests backend, 18→31 frontend) y el roadmap de origen. Transmite: cómo se planeó y bajo qué reglas la administración.

- **Ejecutado en**: [TRABAJO_REALIZADO_EN_ADMIN.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ADMIN.md) · **Patrón que calcan**: [PLAN_PROFESOR.md](PLAN/PLAN_PROFESOR.md) y [PLAN_ALUMNO.md](PLAN/PLAN_ALUMNO.md).

## 4. [PLAN_PROFESOR.md](PLAN/PLAN_PROFESOR.md) · `PLAN/`

El plan del módulo profesor (fases T0–T4). Define el panel propio del profesorado siguiendo el patrón del módulo admin: decisiones de diseño (D-T1 rutas compartidas planas, D-T2 login → `/teacher`, D-T3 guard `RequireTeacher`, D-T4 componentes en `features/teacher/`, D-T5 permisos custom de Fase D, D-T6 polling sin WebSocket), inventario de los 59 endpoints utilizables por teacher, los 5 endpoints de agregación a crear (`/teacher/dashboard`, `/teacher/queue`, `/teacher/pending-count`, `/courses/{id}/overview`, `/courses/{id}/students/{sid}`) y el detalle de cada fase con su cadena de verificación. Transmite: cómo se iba a construir el panel del profe y bajo qué reglas.

- **Patrón de origen**: [PLAN_ADMIN.md](PLAN/PLAN_ADMIN.md) · **Ejecutado en**: [TRABAJO_REALIZADO_EN_PROFESOR.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_PROFESOR.md) · **Siguiente módulo**: [PLAN_ALUMNO.md](PLAN/PLAN_ALUMNO.md).

## 5. [PLAN_ALUMNO.md](PLAN/PLAN_ALUMNO.md) · `PLAN/`

El plan del módulo alumno (fases S0–S4). La contraparte del plan del profesor para el alumnado: decisiones (D-S1 rutas planas, D-S2 login → `/student`, D-S3 guard `RequireStudent`, D-S4 componentes en `features/student/`, D-S5 polling 30 s, D-S6 cero cambios de visibilidad en `policies.py`, D-S7 sin migraciones), inventario de los 44 endpoints del student y los 3 huecos de agregación a crear (`/student/dashboard`, `/student/pending-count`, `/courses/{id}/my-progress`), más las fases S0→S4 y la verificación obligatoria. Transmite: qué se prometió para el panel del alumno y con qué límites de seguridad.

- **Patrón de origen**: [PLAN_ADMIN.md](PLAN/PLAN_ADMIN.md) · **Ejecutado en**: [TRABAJO_REALIZADO_EN_ALUMNO.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ALUMNO.md) · **Hermano**: [PLAN_PROFESOR.md](PLAN/PLAN_PROFESOR.md).

## 6. [TRABAJO_REALIZADO_EN_ADMIN.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ADMIN.md) · `PLANES_APLICADO_CON_EXITO/`

El informe de entregas del módulo admin (estado real). Lo que ya está hecho y commiteado: tabla de commits de las 4 fases (A `86d505d` → D `26f100a`), detalle de cada fase con endpoints, modelos, archivos y tests, verificación (105 backend / 31 frontend), pendientes conocidos y el roadmap de origen preservado. Transmite: qué hay entregado hoy, dónde está y qué falta — el "estado del proyecto" para teammates.

- **Plan**: [PLAN_ADMIN.md](PLAN/PLAN_ADMIN.md) · **Bitácora**: [CHANGELOG.md](../CHANGELOG.md).

## 7. [TRABAJO_REALIZADO_EN_PROFESOR.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_PROFESOR.md) · `PLANES_APLICADO_CON_EXITO/`

El informe de entregas del módulo profesor (fases T0–T4 completadas). Tabla de commits (`d251624` T0 → `bc1f125` CHANGELOG), decisiones aplicadas, detalle fase a fase (T4 pulido/permisos/export → T0 estructura), los endpoints nuevos creados, verificación al cierre (**114 tests backend, 86.11 %; 43 tests frontend**) y sus limitaciones (informes reutilizados de Fase D, sin WebSocket). Transmite: el estado del panel del profesorado.

- **Plan**: [PLAN_PROFESOR.md](PLAN/PLAN_PROFESOR.md) · **Bitácora**: [CHANGELOG.md](../CHANGELOG.md) · **Hermano**: [TRABAJO_REALIZADO_EN_ALUMNO.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ALUMNO.md).

## 8. [TRABAJO_REALIZADO_EN_ALUMNO.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ALUMNO.md) · `PLANES_APLICADO_CON_EXITO/`

El informe de entregas del módulo alumno (fases S0–S4 completadas). Tabla de commits (`ffc6c67` S0 → `7ed6780` S4), las 7 decisiones de diseño, la tabla de los 3 endpoints nuevos de agregación, detalle fase a fase (S4 guards → S0 estructura), verificación final (**123 tests backend, 86.70 %; 66 tests frontend**) y pendientes (polling, límite de 10 en "Por entregar", sin migraciones). Transmite: el estado del panel del alumnado.

- **Plan**: [PLAN_ALUMNO.md](PLAN/PLAN_ALUMNO.md) · **Bitácora**: [CHANGELOG.md](../CHANGELOG.md) · **Hermano**: [TRABAJO_REALIZADO_EN_PROFESOR.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_PROFESOR.md).

## 9. [TRABAJO_REALIZADO_EN_SUPER_ADMIN.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md) · `PLANES_APLICADO_CON_EXITO/`

El informe de entregas del módulo SaaS multi-tenant (fases A–D completadas). Tabla de commits (`05b3d28` A → `814541f` B, C y D sin commit), la cadena de verificación por cierre (133 → 149 → 163 → **177 tests backend, 87.11 %**; 66 → **85 tests frontend**) y, como cuerpo más reciente, la Fase D: el 2FA TOTP de `super_admin` (reto de login sin tokens, endpoints `/auth/mfa/*`, migración `d8e9f0a1b2c3`, 14 tests + prueba de mutación) y el frontend por rol (`/precios`, `/registro-empresa`, `/activar-cuenta/:token`, panel `/plataforma` con su guard); antes, la Fase C (invariante 404-nunca-403, choke points de `policies.py`, scoping de las 65 rutas, rutas `/superadmin/*`, 14 tests con 2 mutaciones). Transmite: qué hay entregado hoy en el SaaS (la totalidad de `Super-admin-prompt.md`) y qué queda como deuda heredada (QR de 2FA, WebSocket, emails).

- **Prompt**: [Super-admin-prompt.md](1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md) · **Plan**: [PLAN_CLAUDE.md](PLAN/PLAN_CLAUDE.md) §11–13 · **Bitácora**: [CHANGELOG.md](../CHANGELOG.md) · **Hermano**: [TRABAJO_REALIZADO_EN_ADMIN.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ADMIN.md).

## 10. [COMANDOS_DE_LA_APP.md](COMANDOS/COMANDOS_DE_LA_APP.md) · `COMANDOS/`

La guía operativa (manual de uso). Solo comandos: requisitos, variables de entorno, arranque con Docker (opción A) o local sin Docker (opción B), primer admin y seed, migraciones, tests/lint, Makefile, puertos/URLs, credenciales de los flujos de acceso y solución de problemas. Transmite: cómo instalar, arrancar y mantener la app en el día a día — pensada para quien la ejecuta, no para quien la diseña.

- **Arranque express**: [run_comando.md](COMANDOS/run_comando.md) · **Presentación**: [README.md](../README.md).

## 11. [run_comando.md](COMANDOS/run_comando.md) · `COMANDOS/`

La chuleta rápida de arranque. El mínimo para tener la app corriendo en local con SQLite ya configurado: 2 terminales (Terminal 1 `uvicorn app.main:app --reload` con `DEBUG=true`; Terminal 2 `npm run dev`), la nota de `Set-ExecutionPolicy` si PowerShell bloquea scripts y las URLs resultantes (`localhost:5173` y `localhost:8000/docs`). Transmite: el "arranque express" de 30 segundos, sin explicación.

- **Manual completo**: [COMANDOS_DE_LA_APP.md](COMANDOS/COMANDOS_DE_LA_APP.md).

---

## Carpeta `1-REVISION_DE_CODIGO_CLAUDE/`

## 12. [Super-admin-prompt.md](1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md)

El prompt completo de la futura fase SaaS multi-tenant (organizaciones clientes, Stripe, webhooks con verificación de firma, roles `super_admin`/`org_admin`): requisitos explícitos con las fallas ya detectadas (firma del webhook, aislamiento multi-tenant, secretos sin default) puestos como condiciones "no negociables". Transmite: qué se le pide a la IA en la próxima gran fase.

- **Análisis previo**: [PLAN_SUPER_ADMIN.md](PLAN/PLAN_SUPER_ADMIN.md) · **Arquitectura actual**: [PLAN_CLAUDE.md](PLAN/PLAN_CLAUDE.md).

## 13. [PLAN_SUPER_ADMIN.md](PLAN/PLAN_SUPER_ADMIN.md) · `PLAN/`

El análisis de diseño previo al prompt: concepto `Organization` (el tenant), los 4 roles bien separados, cambios en el modelo de datos, multi-tenancy en cada query, qué hace y qué no hace `super_admin`, migración de lo existente y la pregunta abierta sobre el alta del primer `org_admin`. Transmite: el "por qué" y las reglas antes de escribir código.

- **Requisitos completos**: [Super-admin-prompt.md](1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md) · **Otros documentos de la carpeta**: [FIXES.md](1-REVISION_DE_CODIGO_CLAUDE/FIXES.md) (revisión de código por gravedad), [DESPLIEGUE.md](1-REVISION_DE_CODIGO_CLAUDE/DESPLIEGUE.md) (fases pendientes de despliegue).

---

## Archivos en la raíz del repositorio

## 14. [CHANGELOG.md](../CHANGELOG.md)

La bitácora de entregas (historial legible sin git). Formato [Keep a Changelog](https://keepachangelog.com/es/1.1.0/): una entrada por fase — `## [Fase 0]` … `## [Fase 3]`, `## [Fase A]`–`[Fase D]` (admin), `## [Fase T]` (profesor) y `## [Fase S]` (alumno) — ordenadas de más reciente a más antigua, y cada entrada con dos bloques:

- **Hecho**: qué se entregó en backend, frontend y tests (con % de cobertura y número de tests).
- **Pendiente / limitaciones**: lo que quedó fuera a propósito o aplazado.

Para qué sirve: responder de un vistazo "¿qué se hizo en cada fase y qué falta?" sin tener que leer el historial de commits; es el documento que se actualiza al cerrar cada fase (uno de los criterios de aceptación de todos los planes: [PLAN_ADMIN.md](PLAN/PLAN_ADMIN.md), [PLAN_PROFESOR.md](PLAN/PLAN_PROFESOR.md), [PLAN_ALUMNO.md](PLAN/PLAN_ALUMNO.md)).

## 15. [README.md](../README.md)

La puerta de entrada del repositorio. Presenta el producto (Aspasia/aula virtual), para qué sirve, roles y permisos, flujos de registro y acceso con credenciales de demo, pantallas, arquitectura técnica y modelo de datos, calidad con tests, instalación express (Docker o local) y documentación relacionada. Transmite: qué es el proyecto y cómo empezar en 5 minutos — el primer archivo que abre quien llega nuevo.

---

### Resumen

- **Instrucciones**: [prompt](PROMPT_INICIAL/prompt_Claude_PrimerasFases.md) (qué pedir) → planes `PLAN_*` en [`PLAN/`](PLAN/) (cómo se decidió: [Claude](PLAN/PLAN_CLAUDE.md), [Admin](PLAN/PLAN_ADMIN.md), [Profesor](PLAN/PLAN_PROFESOR.md), [Alumno](PLAN/PLAN_ALUMNO.md)).
- **Estado**: informes `TRABAJO_REALIZADO_*` en [`PLANES_APLICADO_CON_EXITO/`](PLANES_APLICADO_CON_EXITO/) (qué hay: [Admin](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ADMIN.md), [Profesor](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_PROFESOR.md), [Alumno](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_ALUMNO.md), [Super-admin](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md)) + [CHANGELOG.md](../CHANGELOG.md) (historial por fases).
- **Uso**: [COMANDOS_DE_LA_APP.md](COMANDOS/COMANDOS_DE_LA_APP.md) (manual completo) → [run_comando.md](COMANDOS/run_comando.md) (arranque express) → [README.md](../README.md) (presentación general).
- **SaaS multi-tenant (fases A–D aplicadas)**: [Super-admin-prompt.md](1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md) (requisitos) ← [PLAN_SUPER_ADMIN.md](PLAN/PLAN_SUPER_ADMIN.md) (análisis) → entregas en [TRABAJO_REALIZADO_EN_SUPER_ADMIN.md](PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md), con [FIXES.md](1-REVISION_DE_CODIGO_CLAUDE/FIXES.md) y [DESPLIEGUE.md](1-REVISION_DE_CODIGO_CLAUDE/DESPLIEGUE.md).
