"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";
import type { UserRead, UserRole } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { Pencil, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";

interface UserForm {
  email: string;
  password: string;
  role: UserRole;
  is_active: boolean;
}
const emptyForm: UserForm = { email: "", password: "", role: "analyst", is_active: true };

export function UserWorkspace() {
  const [users, setUsers] = useState<UserRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<UserRead | null>(null);
  const [form, setForm] = useState<UserForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const toast = useToast();
  useEffect(() => {
    let active = true;
    apiFetch<UserRead[]>("/users")
      .then((items) => active && setUsers(items))
      .catch(
        (caught: unknown) =>
          active && setError(caught instanceof Error ? caught.message : "Ошибка загрузки"),
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);
  function create() {
    setEditing(null);
    setForm(emptyForm);
    setFormError(null);
    setOpen(true);
  }
  function edit(user: UserRead) {
    setEditing(user);
    setForm({ email: user.email, password: "", role: user.role, is_active: user.is_active });
    setFormError(null);
    setOpen(true);
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!editing && form.password.length < 12) {
      setFormError("Для новой учётной записи нужен пароль не короче 12 символов.");
      return;
    }
    if (editing && form.password && form.password.length < 12) {
      setFormError("Новый пароль должен содержать не менее 12 символов.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const payload = editing
        ? {
            role: form.role,
            is_active: form.is_active,
            ...(form.password ? { password: form.password } : {}),
          }
        : { email: form.email, password: form.password, role: form.role };
      const saved = await apiFetch<UserRead>(editing ? `/users/${editing.id}` : "/users", {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      setUsers((items) =>
        editing ? items.map((item) => (item.id === saved.id ? saved : item)) : [saved, ...items],
      );
      setOpen(false);
      toast(editing ? "Пользователь обновлён" : "Пользователь создан");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Изменения не сохранены";
      setFormError(message);
      toast(message, "error");
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Administration"
        title="Пользователи"
        description="Учётные записи и ролевой доступ к платформе."
        actions={
          <Button icon={<UserPlus />} onClick={create}>
            Добавить пользователя
          </Button>
        }
      />
      {loading ? (
        <LoadingState label="Загружаем пользователей" />
      ) : error ? (
        <ErrorState message={error} />
      ) : !users.length ? (
        <EmptyState title="Пользователей нет" description="Создайте первую учётную запись." />
      ) : (
        <Table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Роль</th>
              <th>Состояние</th>
              <th>Создан</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>
                  <strong>{user.email}</strong>
                  <small className="table-subline mono">{user.id}</small>
                </td>
                <td>
                  <Badge>{user.role}</Badge>
                </td>
                <td>
                  <Badge tone={user.is_active ? "completed" : "critical"}>
                    {user.is_active ? "Активен" : "Отключён"}
                  </Badge>
                </td>
                <td>{formatDate(user.created_at)}</td>
                <td>
                  <Button variant="ghost" icon={<Pencil />} onClick={() => edit(user)}>
                    Изменить
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? "Изменить пользователя" : "Новый пользователь"}
        description={
          editing
            ? editing.email
            : "Создайте учётную запись и назначьте минимально необходимую роль."
        }
      >
        <form onSubmit={save}>
          {!editing ? (
            <Input
              id="user-email"
              label="Email"
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          ) : null}
          <Input
            id="user-password"
            label={editing ? "Новый пароль" : "Пароль"}
            type="password"
            autoComplete="new-password"
            required={!editing}
            minLength={12}
            value={form.password}
            hint={editing ? "Оставьте пустым, чтобы не менять." : "Минимум 12 символов."}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <Select
            id="user-role"
            label="Роль"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
          >
            <option value="admin">Admin</option>
            <option value="analyst">Analyst</option>
            <option value="viewer">Viewer</option>
          </Select>
          {editing ? (
            <label className="checkbox-control">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              />
              <span>
                <strong>Активная учётная запись</strong>
                <small>Отключённый пользователь не сможет войти.</small>
              </span>
            </label>
          ) : null}
          {formError ? (
            <p className="login-error" role="alert">
              {formError}
            </p>
          ) : null}
          <div className="modal-actions">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button type="submit" loading={saving}>
              Сохранить
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
