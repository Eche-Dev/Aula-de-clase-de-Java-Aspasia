# Chuleta de arranque express (SQLite ya configurado)

> Manual completo: [COMANDOS_DE_LA_APP.md](COMANDOS_DE_LA_APP.md) · Presentación: [README.md](../../README.md) · Índice de docs: [Explicacion_de_Cada_ARCHIVO.md](../Explicacion_de_Cada_ARCHIVO.md)

## 1. Arrancar la app (2 terminales)

**Terminal 1 — API (backend)**

```powershell
cd D:\ADEV\ProyectosVScode\Aula-de-clase-de-Java-Aspasia\backend
$env:DATABASE_URL="sqlite:///./dev.db"
$env:DEBUG="true"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Swagger (API interactiva): <http://localhost:8000/docs>
- `DATABASE_URL` apunta a SQLite (`backend/dev.db`); sin esa línea intenta
  PostgreSQL y la app no arranca. Si PowerShell bloquea scripts al activar el
  venv: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.

**Terminal 2 — Frontend**

```powershell
cd D:\ADEV\ProyectosVScode\Aula-de-clase-de-Java-Aspasia\frontend
npm run dev
```

- App: <http://localhost:5173> (habla con la API de `localhost:8000`).

## 2. Cuentas de prueba (solo local, ¡cámbialas en producción!)

| Rol | Email | Contraseña |
|---|---|---|
| org_admin | `admin@aspasia.test` | `AdminAspasia-2026` (restaurada) |
| super_admin | `root@aspasia.test` | `SuperAspasia-2026` |
| profesor (seed) | `profe@demo.test` | `profe-demo-pass` |
| alumnos | `student01` … `student15` | PIN del seed (curso `JAVA`) |

### Super admin y su 2FA (obligatorio)

- Se entra por <http://localhost:5173/plataforma/acceso> (esa pantalla **no**
  está enlazada en la web pública).
- Primera vez: contraseña → te muestra un **secreto** → mételo en tu app
  authenticator (2FAS, Google Authenticator…) → introduce su código de 6
  dígitos. Sin app en el móvil, genera el código aquí:

```powershell
cd D:\ADEV\ProyectosVScode\Aula-de-clase-de-Java-Aspasia\backend
$env:DATABASE_URL="sqlite:///./dev.db"
.\.venv\Scripts\python.exe -m scripts.totp_code --email root@aspasia.test
```

- Panel: <http://localhost:5173/plataforma> (métricas, organizaciones,
  suscripciones, 2FA).

### ¿Olvidaste la contraseña de un admin?

```powershell
cd D:\ADEV\ProyectosVScode\Aula-de-clase-de-Java-Aspasia\backend
$env:DATABASE_URL="sqlite:///./dev.db"
.\.venv\Scripts\python.exe -m scripts.create_admin --role org_admin --email admin@aspasia.test --password NUEVA-CONTRASENA --reset
```

## 3. Comandos útiles (tests y migraciones)

**Backend** (siempre con `$env:DATABASE_URL="sqlite:///./dev.db"` en esa terminal):

```powershell
.\.venv\Scripts\python.exe -m ruff check .                    # lint
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-fail-under=80   # tests + cobertura (177)
$env:ALEMBIC_DATABASE_URL="sqlite:///./dev.db"; .\.venv\Scripts\python.exe -m alembic upgrade head   # migraciones
.\.venv\Scripts\python.exe -m alembic current                 # ¿está en el head?
```

**Frontend:**

```powershell
npm run lint        # eslint
npm run test        # vitest (85)
```

---
[Volver al manual](COMANDOS_DE_LA_APP.md) · [README](../../README.md) · [CHANGELOG](../../CHANGELOG.md)
