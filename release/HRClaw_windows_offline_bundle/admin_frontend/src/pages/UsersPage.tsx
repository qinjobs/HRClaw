import { useEffect, useMemo, useState } from "react";
import { KeyRound, ShieldCheck, UserCog, UserPlus, UsersRound } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { getJson, postJson } from "@/lib/api";
import { getBootstrap } from "@/lib/bootstrap";
import { formatTime } from "@/lib/format";
import type { HrUser } from "@/lib/types";

interface UserListResponse {
  items: HrUser[];
  current_user_id?: string;
}

const defaultCreateForm = {
  username: "",
  display_name: "",
  password: "",
  role: "hr",
  notes: "",
};

function roleLabel(role?: string) {
  return role === "admin" ? "管理员" : "HR";
}

function roleBadge(role?: string) {
  return role === "admin" ? "info" : "neutral";
}

function statusBadge(active?: boolean) {
  return active ? "success" : "warn";
}

export function UsersPage() {
  const bootstrap = getBootstrap();
  const isAdmin = bootstrap.userRole === "admin";
  const { pushToast } = useToast();
  const [users, setUsers] = useState<HrUser[]>([]);
  const [currentUserId, setCurrentUserId] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");
  const [createForm, setCreateForm] = useState(defaultCreateForm);
  const [editForm, setEditForm] = useState({
    display_name: "",
    role: "hr",
    active: true,
    notes: "",
  });
  const [resetPassword, setResetPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState("");

  const selectedUser = useMemo(
    () => users.find((item) => item.id === selectedUserId) ?? null,
    [selectedUserId, users],
  );

  const stats = useMemo(() => {
    const activeCount = users.filter((item) => item.active).length;
    const adminCount = users.filter((item) => item.role === "admin").length;
    return {
      total: users.length,
      active: activeCount,
      admins: adminCount,
    };
  }, [users]);

  const loadUsers = async (preserveSelection = true) => {
    if (!isAdmin) return;
    setLoading(true);
    setError("");
    try {
      const payload = await getJson<UserListResponse>("/api/hr/users");
      setUsers(payload.items || []);
      setCurrentUserId(payload.current_user_id || "");
      setSelectedUserId((current) => {
        if (preserveSelection && current && payload.items.some((item) => item.id === current)) {
          return current;
        }
        return payload.items[0]?.id || "";
      });
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "加载用户失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadUsers(false);
  }, [isAdmin]);

  useEffect(() => {
    if (!selectedUser) {
      setEditForm({
        display_name: "",
        role: "hr",
        active: true,
        notes: "",
      });
      setResetPassword("");
      return;
    }
    setEditForm({
      display_name: selectedUser.display_name || selectedUser.username,
      role: selectedUser.role || "hr",
      active: Boolean(selectedUser.active),
      notes: selectedUser.notes || "",
    });
    setResetPassword("");
  }, [selectedUser]);

  const handleCreate = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreating(true);
    setError("");
    try {
      const payload = await postJson<{ user: HrUser }>("/api/hr/users", {
        username: createForm.username.trim(),
        display_name: createForm.display_name.trim(),
        password: createForm.password,
        role: createForm.role,
        notes: createForm.notes.trim(),
        active: true,
      });
      setCreateForm(defaultCreateForm);
      await loadUsers(false);
      if (payload.user?.id) {
        setSelectedUserId(payload.user.id);
      }
      pushToast({ tone: "success", title: "用户已创建", description: `账号 ${payload.user.username} 已可登录后台。` });
    } catch (createError) {
      const message = createError instanceof Error ? createError.message : "创建用户失败";
      setError(message);
      pushToast({ tone: "error", title: "创建失败", description: message });
    } finally {
      setCreating(false);
    }
  };

  const handleSave = async () => {
    if (!selectedUser) return;
    setSaving(true);
    setError("");
    try {
      const payload = await postJson<{ user: HrUser }>(`/api/hr/users/${selectedUser.id}`, {
        display_name: editForm.display_name.trim(),
        role: editForm.role,
        active: editForm.active,
        notes: editForm.notes.trim(),
      });
      await loadUsers();
      pushToast({
        tone: "success",
        title: "用户已更新",
        description: `已保存 ${payload.user.display_name || payload.user.username} 的最新配置。`,
      });
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : "保存用户失败";
      setError(message);
      pushToast({ tone: "error", title: "保存失败", description: message });
    } finally {
      setSaving(false);
    }
  };

  const handleResetPassword = async () => {
    if (!selectedUser) return;
    setResetting(true);
    setError("");
    try {
      await postJson(`/api/hr/users/${selectedUser.id}/password`, { password: resetPassword });
      setResetPassword("");
      pushToast({
        tone: "success",
        title: "密码已重置",
        description: `请把新密码单独通知给 ${selectedUser.display_name || selectedUser.username}。`,
      });
    } catch (resetError) {
      const message = resetError instanceof Error ? resetError.message : "重置密码失败";
      setError(message);
      pushToast({ tone: "error", title: "重置失败", description: message });
    } finally {
      setResetting(false);
    }
  };

  if (!isAdmin) {
    return (
      <AppShell
        username={bootstrap.username}
        userRole={bootstrap.userRole}
        title="用户管理"
        subtitle="当前账号不是管理员，无法查看或修改 HR 用户。"
      >
        <Card>
          <CardHeader>
            <CardTitle>无权限访问</CardTitle>
            <CardDescription>只有管理员账号可以创建、停用和重置 HR 用户。请联系系统管理员处理。</CardDescription>
          </CardHeader>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell
      username={bootstrap.username}
      userRole={bootstrap.userRole}
      title="用户管理"
      subtitle="统一维护后台登录账号，支持创建 HR 用户、控制启停状态，以及为管理员和值班 HR 分配权限。"
    >
      <section className="grid gap-4 md:grid-cols-3">
        <MetricCard label="账号总数" value={stats.total} hint="包含管理员和 HR 账号" icon={UsersRound} />
        <MetricCard label="启用中" value={stats.active} hint="可正常登录后台的账号数" icon={ShieldCheck} />
        <MetricCard label="管理员" value={stats.admins} hint="建议至少保留 1 个启用中的管理员" icon={UserCog} />
      </section>

      {error ? (
        <Card className="border-rose-200 bg-rose-50/90">
          <CardContent className="pt-7 text-sm text-rose-700">{error}</CardContent>
        </Card>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>创建用户</CardTitle>
            <CardDescription>为新的 HR 或管理员创建后台登录账号。用户名建议使用企业邮箱前缀或统一工号。</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleCreate}>
              <div className="space-y-2">
                <Label htmlFor="user-create-username">用户名</Label>
                <Input
                  id="user-create-username"
                  placeholder="例如 hr.zhang 或 zhangsan@company.com"
                  value={createForm.username}
                  onChange={(event) => setCreateForm((current) => ({ ...current, username: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="user-create-display-name">显示名称</Label>
                <Input
                  id="user-create-display-name"
                  placeholder="例如 张三"
                  value={createForm.display_name}
                  onChange={(event) => setCreateForm((current) => ({ ...current, display_name: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="user-create-password">初始密码</Label>
                <Input
                  id="user-create-password"
                  type="password"
                  placeholder="不少于 3 位"
                  value={createForm.password}
                  onChange={(event) => setCreateForm((current) => ({ ...current, password: event.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="user-create-role">账号角色</Label>
                <NativeSelect
                  id="user-create-role"
                  value={createForm.role}
                  onChange={(event) => setCreateForm((current) => ({ ...current, role: event.target.value }))}
                >
                  <option value="hr">HR</option>
                  <option value="admin">管理员</option>
                </NativeSelect>
              </div>
              <div className="space-y-2">
                <Label htmlFor="user-create-notes">备注</Label>
                <Textarea
                  id="user-create-notes"
                  className="min-h-[120px]"
                  placeholder="可记录部门、岗位职责或值班说明"
                  value={createForm.notes}
                  onChange={(event) => setCreateForm((current) => ({ ...current, notes: event.target.value }))}
                />
              </div>
              <Button type="submit" className="w-full justify-center" disabled={creating}>
                <UserPlus className="size-4" />
                {creating ? "创建中..." : "创建用户"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle>账号列表</CardTitle>
                <CardDescription>点击某一行后，可在下方详情区调整状态、角色、备注和密码。</CardDescription>
              </div>
              <Button variant="secondary" onClick={() => void loadUsers()} disabled={loading}>
                {loading ? "刷新中..." : "刷新列表"}
              </Button>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>账号</TableHead>
                    <TableHead>角色</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>最近登录</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.length ? (
                    users.map((user) => {
                      const selected = user.id === selectedUserId;
                      return (
                        <TableRow
                          key={user.id}
                          data-state={selected ? "selected" : undefined}
                          className="cursor-pointer"
                          onClick={() => setSelectedUserId(user.id)}
                        >
                          <TableCell>
                            <div className="space-y-1">
                              <div className="font-semibold text-slate-950">{user.display_name || user.username}</div>
                              <div className="text-xs text-slate-500">{user.username}</div>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant={roleBadge(user.role)}>{roleLabel(user.role)}</Badge>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <Badge variant={statusBadge(user.active)}>{user.active ? "启用" : "停用"}</Badge>
                              {user.system_managed ? <Badge variant="neutral">系统</Badge> : null}
                            </div>
                          </TableCell>
                          <TableCell>{formatTime(user.last_login_at)}</TableCell>
                        </TableRow>
                      );
                    })
                  ) : (
                    <TableRow>
                      <TableCell colSpan={4} className="py-10 text-center text-slate-500">
                        暂无用户数据
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{selectedUser ? `管理账号：${selectedUser.display_name || selectedUser.username}` : "管理账号"}</CardTitle>
              <CardDescription>
                {selectedUser
                  ? "可以更新显示名称、角色、启停状态和备注；密码重置需要单独提交。"
                  : "先从上面的账号列表中选择一个用户。"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {selectedUser ? (
                <>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="user-edit-display-name">显示名称</Label>
                      <Input
                        id="user-edit-display-name"
                        value={editForm.display_name}
                        onChange={(event) => setEditForm((current) => ({ ...current, display_name: event.target.value }))}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="user-edit-role">账号角色</Label>
                      <NativeSelect
                        id="user-edit-role"
                        value={editForm.role}
                        disabled={Boolean(selectedUser.system_managed)}
                        onChange={(event) => setEditForm((current) => ({ ...current, role: event.target.value }))}
                      >
                        <option value="hr">HR</option>
                        <option value="admin">管理员</option>
                      </NativeSelect>
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_240px]">
                    <div className="space-y-2">
                      <Label htmlFor="user-edit-notes">备注</Label>
                      <Textarea
                        id="user-edit-notes"
                        className="min-h-[120px]"
                        value={editForm.notes}
                        onChange={(event) => setEditForm((current) => ({ ...current, notes: event.target.value }))}
                      />
                    </div>
                    <div className="rounded-[24px] border border-black/[0.06] bg-slate-50/80 p-5">
                      <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">账号状态</div>
                      <div className="mt-3 flex items-center justify-between gap-4">
                        <div>
                          <div className="text-sm font-semibold text-slate-950">{editForm.active ? "已启用" : "已停用"}</div>
                          <div className="mt-1 text-xs leading-5 text-slate-500">
                            停用后该账号将无法再登录后台。
                          </div>
                        </div>
                        <Switch
                          checked={editForm.active}
                          disabled={Boolean(selectedUser.system_managed && editForm.active)}
                          onCheckedChange={(checked) => setEditForm((current) => ({ ...current, active: checked }))}
                        />
                      </div>
                      <div className="mt-5 space-y-2 text-xs text-slate-500">
                        <div>创建时间：{formatTime(selectedUser.created_at)}</div>
                        <div>最近登录：{formatTime(selectedUser.last_login_at)}</div>
                        <div>创建人：{selectedUser.created_by || "-"}</div>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-3">
                    <Button onClick={handleSave} disabled={saving}>
                      {saving ? "保存中..." : "保存用户设置"}
                    </Button>
                    {selectedUser.id === currentUserId ? (
                      <Badge variant="neutral" className="self-center">
                        当前登录账号
                      </Badge>
                    ) : null}
                    {selectedUser.system_managed ? (
                      <Badge variant="info" className="self-center">
                        系统管理员账号受保护
                      </Badge>
                    ) : null}
                  </div>

                  <div className="rounded-[24px] border border-black/[0.06] bg-slate-50/80 p-5">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                      <KeyRound className="size-4" />
                      重置密码
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-500">输入新密码后立即生效，旧密码将失效。</p>
                    <div className="mt-4 flex flex-col gap-3 md:flex-row">
                      <Input
                        type="password"
                        placeholder="不少于 3 位"
                        value={resetPassword}
                        onChange={(event) => setResetPassword(event.target.value)}
                      />
                      <Button onClick={handleResetPassword} disabled={resetting || !resetPassword.trim()}>
                        {resetting ? "提交中..." : "重置密码"}
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="rounded-[24px] border border-dashed border-black/[0.08] bg-slate-50/80 px-6 py-10 text-center text-sm text-slate-500">
                  先从上方选择一个用户，再进行管理操作。
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </section>
    </AppShell>
  );
}

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: number;
  hint: string;
  icon: typeof UsersRound;
}) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between pt-7">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">{label}</div>
          <div className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-slate-950">{value}</div>
          <div className="mt-2 text-sm leading-6 text-slate-500">{hint}</div>
        </div>
        <div className="flex size-11 items-center justify-center rounded-full border border-black/[0.06] bg-slate-50 text-slate-600">
          <Icon className="size-5" />
        </div>
      </CardContent>
    </Card>
  );
}
