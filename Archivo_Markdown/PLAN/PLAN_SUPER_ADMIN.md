# SUPER_ADMIN — Análisis de la arquitectura multi-tenant

Te entiendo perfectamente, y es un cambio de arquitectura real, no un ajuste menor: pasas de "una plataforma con cursos" a "una plataforma con clientes que tienen cursos". Vamos a lo concreto.

**Documentación relacionada**: prompt completo [Super-admin-prompt.md](../1-REVISION_DE_CODIGO_CLAUDE/Super-admin-prompt.md) · arquitectura actual [PLAN_CLAUDE.md](PLAN_CLAUDE.md) · informe de entrega [TRABAJO_REALIZADO_EN_SUPER_ADMIN.md](../PLANES_APLICADO_CON_EXITO/TRABAJO_REALIZADO_EN_SUPER_ADMIN.md) · [Índice de docs](../Explicacion_de_Cada_ARCHIVO.md) · [CHANGELOG.md](../../CHANGELOG.md).

---

## 1. El concepto que falta: Organization (el tenant)

Ahora mismo tu jerarquía es User → Course. Necesitas meter un nivel encima:

```text
Platform (tú)
  └── Organization (Dicampus, Instituto X, Academia Y...)
        └── Course (los cursos de esa organización)
              └── User (profesores y alumnos de esa organización)
```

Cada Course y cada User (salvo tú) pertenece a una Organization. Eso es lo que hace que "Dicampus solo vea lo suyo" sea una propiedad del sistema y no una promesa verbal.

---

## 2. Los 4 roles, bien separados

| Rol | Quién es | Qué ve |
|-----|----------|--------|
| super_admin | Tú | Organizaciones, suscripciones, salud de la plataforma. Nunca entregas, notas, mensajes ni archivos de alumnos |
| org_admin | Dicampus (el que paga) | Solo sus profesores, sus alumnos, sus cursos |
| teacher | Profesores de esa organización | Sus cursos dentro de esa organización |
| student | Alumnos | Su curso, como ahora |

Lo importante no es el nombre, es la regla: super_admin no tiene ruta de acceso a datos académicos, ni siquiera "porque podría". Si algún día necesitas depurar un bug de un cliente, entras con permiso explícito y auditado (impersonation con audit log), nunca por defecto. Eso es lo que le vendes a Dicampus cuando les dices "esto no es tuyo pero es privado": tiene que ser cierto a nivel de código, no de buena voluntad.

---

## 3. Qué cambia en tu modelo de datos

```python
class Organization(Base):
    id: Mapped[int]
    name: Mapped[str]                    # "Fundación Dicampus"
    slug: Mapped[str]                    # subdominio o identificador único
    status: Mapped[OrgStatus]            # trial | active | suspended | cancelled
    plan: Mapped[str]                    # "basic" | "pro" | ...
    seat_limit: Mapped[int | None]       # máximo de usuarios, según plan
    billing_email: Mapped[str]
    created_at: Mapped[datetime]
```

```python
class User(Base):
    ...
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True  # null SOLO para super_admin
    )
    role: Mapped[UserRole]  # super_admin | org_admin | teacher | student
```

```python
class Course(Base):
    ...
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
```

---

## 4. El cambio real de trabajo: multi-tenancy en cada query

Esto es lo que más esfuerzo te va a llevar, más que el modelo en sí. Hoy tu require_admin deja pasar a cualquier admin a cualquier curso de cualquier organización (lo vi en policies.py: require_staff_of_course da acceso total si role is admin). Con el nuevo esquema, org_admin debe quedar limitado a course.organization_id == user.organization_id en cada endpoint que hoy asume "admin ve todo". Es decir: coges el patrón que ya tienes bien hecho para teacher (comprobar pertenencia via CourseTeacher) y lo aplicas también a org_admin, pero contra organization_id en vez de una tabla de asignación.

```python
def require_org_scope(db, user, course) -> None:
    if user.role is UserRole.super_admin:
        raise HTTPException(403, "Super admin has no access to academic data")
    if user.role is UserRole.org_admin and course.organization_id != user.organization_id:
        raise HTTPException(404, "Course not found")  # 404, no 403: no reveles que existe
```

Todos los sitios donde hoy if user.role is UserRole.admin: return user, course (acceso total) hay que revisarlos uno por uno. Es mecánico pero no es poco: en tu backend actual eso aparece en require_staff_of_course, require_teacher_of_course, create_course, y probablemente en admin.py completo.

---

## 5. Qué hace super_admin en la práctica

- CRUD de Organization: crear cliente, cambiar plan, suspender por impago, ver fecha de alta.
- Ver métricas agregadas y anónimas: cuántas organizaciones activas, cuántos usuarios totales, uso de almacenamiento por organización — números, nunca contenido.
- Gestionar la plataforma: feature flags, versión desplegada, logs de errores, salud del sistema.
- Facturación: estado de la suscripción de cada organización (si integras Stripe u otro, esto vive aquí).

Y explícitamente no tiene rutas hacia /courses/*, /submissions/*, /messages/*. Ni siquiera de solo lectura. Eso te lo compran las organizaciones cuando dicen "es privado".

---

## 6. Migración de lo que ya tienes

- Crear tabla organizations.
- Crear una organización por defecto (ej. "Dicampus") y migrar ahí todo lo que existe hoy (tu único admin actual pasa a org_admin de esa organización).
- Crearte a ti como el único super_admin, sin organization_id.
- Añadir organization_id a Course (not null) y a User (nullable solo para super_admin).
- Reescribir policies.py para que org_admin filtre por organization_id en vez de tener acceso global.
- Nuevo router admin/organizations.py, accesible solo por super_admin.

---

## 7. Antes de escribirlo: una pregunta que decide el diseño

¿Cómo entra un org_admin nuevo al sistema? Dos caminos típicos:

- Tú lo das de alta manualmente (como super_admin, creas la organización y le mandas las credenciales) — más simple, encaja con "empiezas con pocos clientes".
- Self-signup con periodo de prueba, tipo SaaS clásico (se registran solos, tú apruebas o queda en trial automático) — más escalable, pero te obliga a resolver verificación de email, pagos, y abuso de cuentas de prueba desde ya.

Dado que estás empezando con Dicampus como primer cliente, yo iría con alta manual ahora y dejo el self-signup para cuando tengas 3-4 clientes más y veas si de verdad hace falta automatizarlo. Pero es tu decisión de negocio, no técnica.
