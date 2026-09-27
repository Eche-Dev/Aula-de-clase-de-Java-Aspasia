# Prompt — Super Admin (SaaS multi-tenant)

Aquí tienes el prompt completo para OpenCode, con la falla del webhook (y las demás que hemos ido viendo en este diseño) puestas como requisitos explícitos, no como notas al margen.

**Documentación relacionada**: análisis previo [PLAN_SUPER_ADMIN.md](../PLAN/PLAN_SUPER_ADMIN.md) · arquitectura actual [PLAN_CLAUDE.md](../PLAN/PLAN_CLAUDE.md) · entregas [TRABAJO_REALIZADO_EN_SUPER_ADMIN.md](../PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md) · [Índice de docs](../Explicacion_de_Cada_ARCHIVO.md) · [CHANGELOG.md](../../CHANGELOG.md).

---

## 1. ROL Y OBJETIVO

Actúa como ingeniero senior full stack. Vas a extender el proyecto existente en
github.com/kindred-98/Aula-de-clase-de-Java (backend FastAPI + frontend React) para
convertirlo en una plataforma SaaS multi-tenant: pasa de "una app con cursos" a
"una plataforma con organizaciones clientes que pagan suscripción, cada una con sus
propios cursos, profesores y alumnos".

Antes de tocar código: actualiza PLAN.md con el nuevo modelo de datos, la matriz de
permisos ampliada, el flujo de alta de organización y el diagrama de webhooks de
Stripe. No avances de fase sin que la fase anterior tenga tests pasando.

---

## 2. CONTEXTO DE NEGOCIO

- Yo (el dueño de la plataforma) soy `super_admin`. Mantengo el código, mejoro la
  app, gestiono organizaciones y facturación. NUNCA veo datos académicos de ningún
  cliente (entregas, notas, mensajes, archivos de alumnos) — es un compromiso de
  producto, no solo técnico.
- Cada empresa que paga (ej. "Dicampus") es una `Organization`. Su usuario principal
  tiene rol `org_admin`: gestiona solo sus propios profesores, alumnos y cursos.
  No ve ni sabe de la existencia de otras organizaciones.
- Roles finales: `super_admin`, `org_admin`, `teacher`, `student`.
- Habrá 3-5 planes de suscripción. El alta de una organización nueva ocurre cuando
  alguien intenta comprar un plan sin tener organización registrada.
- El trial pide tarjeta por adelantado (no se cobra hasta que termine el trial).
- Pago vía Stripe Billing (Checkout + Subscriptions). Nunca se procesan ni
  almacenan datos de tarjeta en este backend.
- Email transaccional vía Resend (interfaz abstracta para poder cambiar de
  proveedor sin tocar el resto del sistema).

---

## 3. MODELO DE DATOS NUEVO/MODIFICADO

```python
class OrgStatus(StrEnum):
    pending_payment = "pending_payment"  # checkout de Stripe iniciado, sin confirmar
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"

class Organization(Base):
    id: Mapped[int]
    name: Mapped[str]
    tax_id: Mapped[str]                        # NIF/CIF
    billing_email: Mapped[str]
    status: Mapped[OrgStatus]
    plan_id: Mapped[str]                       # referencia al Price de Stripe
    stripe_customer_id: Mapped[str | None]
    stripe_subscription_id: Mapped[str | None]
    trial_ends_at: Mapped[datetime | None]
    created_at: Mapped[datetime]

class UserRole(StrEnum):
    super_admin = "super_admin"
    org_admin = "org_admin"
    teacher = "teacher"
    student = "student"

# User: añadir
#   organization_id: Mapped[int | None]  -> ForeignKey("organizations.id")
#     NULL únicamente para super_admin. Obligatorio para los otros tres roles.
#   activation_token_hash: Mapped[str | None]   # solo org_admin recién creado
#   activation_token_expires_at: Mapped[datetime | None]

# Course: añadir
#   organization_id: Mapped[int]  -> ForeignKey("organizations.id"), NOT NULL
```

Migración: crear una `Organization` por defecto para los datos que ya existen
(la organización actual pasa a ser un cliente más, con status=`active`), migrar
el `admin` actual a `org_admin` de esa organización, y crear un único
`super_admin` nuevo por CLI (extiende el comando `create-admin` que ya existe
con un flag `--role super_admin`, o un comando `create-super-admin` aparte).

---

## 4. FLUJO DE ALTA DE ORGANIZACIÓN (orden estricto, no lo invirtáis)

1. Formulario público "Registra tu empresa" (nombre, NIF/CIF, email de contacto,
   plan elegido). NO crea `User` todavía. Guarda los datos en `Organization`
   con `status=pending_payment`.
2. Backend crea una Stripe Checkout Session:
   `mode="subscription"`, `trial_period_days=14`,
   `payment_method_collection="always"` (pide tarjeta aunque no cobre aún),
   `metadata={"organization_id": ...}`.
3. Redirige al Checkout de Stripe. La tarjeta se teclea en la página de Stripe,
   nunca pasa por este backend.
4. Webhook `checkout.session.completed`: AHÍ, y solo ahí, se crea el
   `User(role=org_admin)` de esa organización, con `activation_token` (aleatorio,
   se guarda su hash, nunca el valor en claro), `password_hash=NULL`, y
   `Organization.status` pasa a `trialing`.
5. Se envía email (vía `EmailService`) con un enlace de activación de un solo uso,
   válido 48h, que lleva a una pantalla donde la empresa crea su propia
   contraseña. Hasta que no la crea, no puede iniciar sesión.
6. Si el checkout se abandona, la `Organization` se queda en `pending_payment`;
   un job (o un cron simple) la limpia a los 7 días.

---

## 5. WEBHOOKS DE STRIPE A IMPLEMENTAR

`/api/v1/webhooks/stripe`, sin autenticación de usuario:

| Evento | Efecto |
|---|---|
| `checkout.session.completed` | Crear `User(org_admin)` + enviar email de activación (paso 4-5 de arriba) |
| `customer.subscription.trial_will_end` | Email de aviso 3 días antes de que acabe el trial |
| `invoice.payment_succeeded` | `Organization.status = active` |
| `invoice.payment_failed` | `Organization.status = past_due` |
| `customer.subscription.deleted` | `Organization.status = canceled` |

---

## 6. ⚠️ FALLA DE SEGURIDAD A EVITAR DESDE EL DISEÑO — NO NEGOCIABLE

El endpoint de webhooks de Stripe crea usuarios y activa organizaciones. Es, en
la práctica, una puerta de entrada al sistema tan sensible como el login.

**OBLIGATORIO en cada request a `/api/v1/webhooks/stripe`:**
```python
try:
    event = stripe.Webhook.construct_event(
        payload=await request.body(),
        sig_header=request.headers.get("Stripe-Signature", ""),
        secret=settings.stripe_webhook_secret,
    )
except (ValueError, stripe.error.SignatureVerificationError):
    raise HTTPException(status_code=400, detail="Invalid signature")
```
Si no se verifica la firma, cualquiera puede mandar un POST falso a ese endpoint
simulando "esta organización ya pagó" y crear una cuenta `org_admin` gratis sin
pasar por Stripe. Este endpoint necesita un test explícito que confirme que un
payload sin firma válida, o con firma de otro webhook secret, devuelve 400 y no
crea ningún `User` ni cambia ningún `Organization.status`.

**Otras fallas ya detectadas en este proyecto que NO deben repetirse en esta fase
nueva** (aplican con el mismo peso a todo el código de `Organization`/Stripe):
- Ninguna relación SQLAlchemy sin comillas cuando el modelo importado solo está
  bajo `TYPE_CHECKING` (causó un `NameError` que impedía arrancar la app entera).
- Ningún secreto (incluido `stripe_webhook_secret`, `stripe_secret_key`,
  `resend_api_key`) con valor por defecto utilizable en producción; validar en
  `Settings` que si `environment == "production"` estas variables estén
  definidas y no sean el placeholder de desarrollo.
- Ninguna ruta de `org_admin` que dé acceso a datos de otra organización: TODA
  query de `org_admin` debe filtrar por `organization_id == user.organization_id`,
  igual que hoy se filtra por matrícula o por `CourseTeacher`. 404 si no coincide,
  nunca 403 (no reveles que existe otra organización).
- Ninguna ruta de `super_admin` debe tocar `Submission`, `Evaluation`,
  `CourseMessage` ni tablas de contenido académico — ni de lectura. Que sea
  imposible a nivel de router, no solo "no lo uso".

---

## 7. RUTAS

Backend:

```text
/api/v1/public/* — precios, registro de organización (sin auth)
/api/v1/webhooks/stripe — webhook, sin auth de usuario, con verificación de firma
/api/v1/auth/* — login estudiante, login staff, activación de cuenta
/api/v1/superadmin/* — CRUD de Organization, ver suscripciones, métricas agregadas
/api/v1/admin/* — lo que hoy es admin.py, re-acotado por organization_id
/api/v1/teacher/* — como ya existe
/api/v1/student/* — como ya existe
```

Frontend:

```text
/precios — pública, marketing
/registro-empresa — formulario, dispara Checkout de Stripe
/activar-cuenta/:token — crear contraseña tras el email de activación
/login — staff (teacher / org_admin), redirige por rol tras entrar
/login/estudiante — como ya existe
/plataforma/acceso — login del super_admin, NO enlazado desde la web pública
/admin/... — dashboard de organización (org_admin)
/teacher/... — como ya existe
/alumno/... — como ya existe
```

`super_admin` requiere 2FA por TOTP (es la cuenta con más poder del sistema:
puede suspender a cualquier cliente). Implementa el segundo factor solo para
este rol en esta fase; no hace falta para los demás todavía.

---

## 8. TESTS OBLIGATORIOS DE ESTA FASE (además de los que ya existían)

- Webhook sin firma válida → 400, no crea nada, no cambia ningún estado.
- Webhook con firma de un `webhook_secret` distinto → 400.
- `org_admin` de la organización A no puede leer/escribir cursos, alumnos ni
  profesores de la organización B (aislamiento multi-tenant, igual que se probó
  aislamiento entre cursos en la fase anterior, ahora un nivel más arriba).
- `super_admin` recibe 403/404 al intentar acceder a cualquier ruta de
  `Submission`, `Evaluation` o `CourseMessage`, aunque construya la URL a mano.
- Un `User(org_admin)` recién creado por webhook no puede autenticarse hasta
  activar su cuenta (password_hash NULL → login debe rechazar, no solo fallar
  por password incorrecta).
- El token de activación expira a las 48h y no puede reusarse una vez consumido.
- Prueba de mutación manual (como en la fase anterior): rompe a propósito el
  filtro `organization_id` en una query de `org_admin` y confirma que algún test
  falla. Si no falla ninguno, el test está mal escrito, no el código.

---

## 9. FASES

- Fase A: modelo de datos (`Organization`, roles nuevos, migración de datos
  existentes), CLI para crear `super_admin`.
- Fase B: registro de organización + Stripe Checkout + webhooks + verificación de
  firma + `EmailService`/Resend + activación de cuenta.
- Fase C: re-acotar todas las rutas de `admin.py` existentes por
  `organization_id`; rutas nuevas de `superadmin/*` (CRUD de Organization,
  métricas agregadas sin datos académicos).
- Fase D: frontend — rutas separadas por rol, formulario de registro de empresa,
  pantalla de activación, 2FA para super_admin.

Al terminar cada fase: lint + mypy + tests + la prueba de mutación
correspondiente, y actualiza CHANGELOG.md. Empieza por la Fase A y muéstrame
PLAN.md antes de continuar.