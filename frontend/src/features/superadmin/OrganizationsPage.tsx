import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { apiGet, apiSend, type OrganizationAdminPublic, type OrgStatus } from "../../lib/api";
import { ErrorState } from "../../components/ui/ErrorState";
import { Spinner } from "../../components/ui/Spinner";

const STATUSES: OrgStatus[] = ["pending_payment", "trialing", "active", "past_due", "canceled"];

type OrgForm = {
  name: string;
  tax_id: string;
  billing_email: string;
  plan_id: string;
  status: OrgStatus;
};

const EMPTY: OrgForm = { name: "", tax_id: "", billing_email: "", plan_id: "", status: "active" };

function toForm(org: OrganizationAdminPublic): OrgForm {
  return {
    name: org.name,
    tax_id: org.tax_id,
    billing_email: org.billing_email,
    plan_id: org.plan_id,
    status: org.status,
  };
}

export function OrganizationsPage() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<string>("");
  const [q, setQ] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<OrgForm>(EMPTY);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<OrgForm>(EMPTY);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const orgs = useQuery({
    queryKey: ["superadmin-orgs", status, appliedQ],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (appliedQ) params.set("q", appliedQ);
      const suffix = params.toString();
      return apiGet<OrganizationAdminPublic[]>(
        `/superadmin/organizations${suffix ? `?${suffix}` : ""}`,
        signal,
      );
    },
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["superadmin-orgs"] });

  const createOrg = useMutation({
    mutationFn: (input: OrgForm) =>
      apiSend<OrganizationAdminPublic>("POST", "/superadmin/organizations", input),
    onSuccess: () => {
      setCreating(false);
      setForm(EMPTY);
      setError(null);
      void invalidate();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "No se pudo crear."),
  });

  const updateOrg = useMutation({
    mutationFn: ({ id, input }: { id: number; input: OrgForm }) =>
      apiSend<OrganizationAdminPublic>("PATCH", `/superadmin/organizations/${id}`, input),
    onSuccess: () => {
      setEditingId(null);
      setError(null);
      void invalidate();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "No se pudo guardar."),
  });

  const deleteOrg = useMutation({
    mutationFn: (id: number) => apiSend<void>("DELETE", `/superadmin/organizations/${id}`),
    onSuccess: () => {
      setConfirmDelete(null);
      setError(null);
      void invalidate();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "No se pudo borrar."),
  });

  const inputClass =
    "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-primary";

  function submitNew(event: FormEvent) {
    event.preventDefault();
    createOrg.mutate(form);
  }

  function submitEdit(event: FormEvent, id: number) {
    event.preventDefault();
    updateOrg.mutate({ id, input: editForm });
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Organizaciones</h1>
          <p className="mt-1 text-sm text-muted">Clientes de la plataforma.</p>
        </div>
        <button
          type="button"
          onClick={() => setCreating((v) => !v)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white"
        >
          {creating ? "Cancelar" : "Nueva organización"}
        </button>
      </div>

      {error ? <ErrorState message={error} /> : null}

      {creating ? (
        <form
          onSubmit={submitNew}
          className="grid gap-3 rounded-lg border border-border bg-surface p-4 sm:grid-cols-2"
        >
          <label className="block space-y-1 text-sm">
            <span className="text-muted">Nombre</span>
            <input
              className={inputClass}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-muted">NIF / CIF</span>
            <input
              className={inputClass}
              value={form.tax_id}
              onChange={(e) => setForm({ ...form, tax_id: e.target.value })}
              required
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-muted">Email de facturación</span>
            <input
              className={inputClass}
              type="email"
              value={form.billing_email}
              onChange={(e) => setForm({ ...form, billing_email: e.target.value })}
              required
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-muted">Plan</span>
            <input
              className={inputClass}
              value={form.plan_id}
              onChange={(e) => setForm({ ...form, plan_id: e.target.value })}
              placeholder="growth"
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-muted">Estado</span>
            <select
              className={inputClass}
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as OrgStatus })}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={createOrg.isPending}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {createOrg.isPending ? "Creando…" : "Crear"}
            </button>
          </div>
        </form>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <select
          className="rounded-md border border-border bg-bg px-3 py-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label="Filtrar por estado"
        >
          <option value="">Todos los estados</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setAppliedQ(q.trim());
          }}
        >
          <input
            className="rounded-md border border-border bg-bg px-3 py-2 text-sm"
            placeholder="Buscar por nombre…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Buscar organización"
          />
          <button type="submit" className="rounded-md border border-border px-3 py-2 text-sm">
            Buscar
          </button>
        </form>
      </div>

      {orgs.isPending ? <Spinner label="Cargando organizaciones" /> : null}
      {orgs.isError ? (
        <ErrorState
          message="No se pudieron cargar las organizaciones."
          onRetry={() => void orgs.refetch()}
        />
      ) : null}

      {orgs.isSuccess ? (
        orgs.data.length === 0 ? (
          <p className="text-sm text-muted">No hay organizaciones con esos filtros.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted">
                  <th className="py-2 pr-3">ID</th>
                  <th className="py-2 pr-3">Nombre</th>
                  <th className="py-2 pr-3">Estado</th>
                  <th className="py-2 pr-3">Plan</th>
                  <th className="py-2 pr-3">Usuarios</th>
                  <th className="py-2 pr-3">Cursos</th>
                  <th className="py-2 pr-3">Trial</th>
                  <th className="py-2">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {orgs.data.map((org) => (
                  <tr key={org.id} className="border-b border-border">
                    <td className="py-2 pr-3 font-mono">{org.id}</td>
                    <td className="py-2 pr-3">
                      {editingId === org.id ? (
                        <form onSubmit={(e) => submitEdit(e, org.id)} className="space-y-1">
                          <input
                            className={inputClass}
                            value={editForm.name}
                            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                            aria-label="Nombre"
                            required
                          />
                          <input
                            className={inputClass}
                            value={editForm.tax_id}
                            onChange={(e) => setEditForm({ ...editForm, tax_id: e.target.value })}
                            aria-label="NIF / CIF"
                            required
                          />
                          <input
                            className={inputClass}
                            type="email"
                            value={editForm.billing_email}
                            onChange={(e) =>
                              setEditForm({ ...editForm, billing_email: e.target.value })
                            }
                            aria-label="Email de facturación"
                            required
                          />
                          <input
                            className={inputClass}
                            value={editForm.plan_id}
                            onChange={(e) => setEditForm({ ...editForm, plan_id: e.target.value })}
                            aria-label="Plan"
                          />
                          <select
                            className={inputClass}
                            value={editForm.status}
                            onChange={(e) =>
                              setEditForm({ ...editForm, status: e.target.value as OrgStatus })
                            }
                            aria-label="Estado"
                          >
                            {STATUSES.map((s) => (
                              <option key={s} value={s}>
                                {s}
                              </option>
                            ))}
                          </select>
                          <div className="flex gap-2">
                            <button
                              type="submit"
                              disabled={updateOrg.isPending}
                              className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-white"
                            >
                              Guardar
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingId(null)}
                              className="rounded-md border border-border px-3 py-1 text-xs"
                            >
                              Cancelar
                            </button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <span className="font-medium">{org.name}</span>
                          <span className="block text-xs text-muted">{org.billing_email}</span>
                        </>
                      )}
                    </td>
                    <td className="py-2 pr-3">{org.status}</td>
                    <td className="py-2 pr-3">{org.plan_id || "—"}</td>
                    <td className="py-2 pr-3">{org.user_count}</td>
                    <td className="py-2 pr-3">{org.course_count}</td>
                    <td className="py-2 pr-3">
                      {org.trial_ends_at ? new Date(org.trial_ends_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="py-2">
                      {editingId === org.id ? null : (
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setEditingId(org.id);
                              setEditForm(toForm(org));
                              setConfirmDelete(null);
                            }}
                            className="rounded-md border border-border px-2 py-1 text-xs"
                          >
                            Editar
                          </button>
                          {confirmDelete === org.id ? (
                            <button
                              type="button"
                              onClick={() => deleteOrg.mutate(org.id)}
                              disabled={deleteOrg.isPending}
                              className="rounded-md bg-danger px-2 py-1 text-xs font-medium text-white"
                            >
                              ¿Seguro? Solo si está vacía
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setConfirmDelete(org.id)}
                              className="rounded-md border border-border px-2 py-1 text-xs"
                            >
                              Borrar
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}
    </section>
  );
}
