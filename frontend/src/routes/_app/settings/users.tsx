import { zodResolver } from "@hookform/resolvers/zod";
import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, redirect } from "@tanstack/react-router";
import { Plus } from "@phosphor-icons/react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "@/lib/toast";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DEFAULT_PAGE_SIZE, PaginationBar } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { TableSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuthStore } from "@/features/auth/store";
import { can } from "@/features/auth/permissions";
import {
  useCreateUser,
  useListUsers,
  useUpdateUser,
} from "@/lib/api/generated/endpoints";
import { fmtDate, ROLE_LABELS } from "@/lib/format";

const searchSchema = z.object({
  page: z.number().int().min(1).optional().default(1),
});

export const Route = createFileRoute("/_app/settings/users")({
  validateSearch: searchSchema,
  beforeLoad: () => {
    const user = useAuthStore.getState().user;
    if (!can(user?.role, "users:manage")) throw redirect({ to: "/" });
  },
  component: UsersPage,
});

const ROLES = ["admin", "project_manager", "site_manager", "procurement_officer", "viewer"];

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  full_name: z.string().min(1, "Required"),
  password: z.string().min(8, "Min 8 characters"),
  role: z.enum(["admin", "project_manager", "site_manager", "procurement_officer", "viewer"]),
});
type FormValues = z.infer<typeof schema>;

function UsersPage() {
  const { page } = Route.useSearch();
  const navigate = Route.useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useListUsers(
    { page, page_size: DEFAULT_PAGE_SIZE },
    { query: { placeholderData: keepPreviousData } },
  );
  const createMutation = useCreateUser();
  const updateMutation = useUpdateUser();
  const [dialogOpen, setDialogOpen] = useState(false);
  const currentUser = useAuthStore((s) => s.user);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { role: "viewer" },
  });

  const onSubmit = async (values: FormValues) => {
    try {
      await createMutation.mutateAsync({ data: values });
      toast.success("User created");
      await queryClient.invalidateQueries();
      reset();
      setDialogOpen(false);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { error?: { detail?: string } } } })?.response?.data?.error
          ?.detail ?? "Could not create user";
      toast.error(detail);
    }
  };

  const changeRole = async (userId: string, role: string) => {
    try {
      await updateMutation.mutateAsync({ userId, data: { role: role as FormValues["role"] } });
      await queryClient.invalidateQueries();
      toast.success("Role updated");
    } catch {
      toast.error("Update failed");
    }
  };

  const toggleActive = async (userId: string, isActive: boolean) => {
    try {
      await updateMutation.mutateAsync({ userId, data: { is_active: !isActive } });
      await queryClient.invalidateQueries();
    } catch {
      toast.error("Update failed");
    }
  };

  return (
    <div>
      <PageHeader
        title="Users"
        description="Manage workspace members and their roles"
        actions={
          <Button onClick={() => setDialogOpen(true)}>
            <Plus /> Add User
          </Button>
        }
      />

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last Login</TableHead>
              <TableHead className="w-28" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <TableSkeleton columns={6} rows={5} />}
            {data?.items.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.full_name}</TableCell>
                <TableCell className="text-muted-foreground">{u.email}</TableCell>
                <TableCell>
                  <Select
                    className="h-7 w-44 text-xs"
                    value={u.role}
                    disabled={u.id === currentUser?.id}
                    onChange={(e) => void changeRole(u.id, e.target.value)}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABELS[r]}
                      </option>
                    ))}
                  </Select>
                </TableCell>
                <TableCell>
                  {u.is_active ? (
                    <Badge variant="success">Active</Badge>
                  ) : (
                    <Badge variant="destructive">Deactivated</Badge>
                  )}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {u.last_login_at ? fmtDate(u.last_login_at) : "Never"}
                </TableCell>
                <TableCell>
                  {u.id !== currentUser?.id && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void toggleActive(u.id, u.is_active ?? true)}
                    >
                      {u.is_active ? "Deactivate" : "Reactivate"}
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <PaginationBar
          page={page}
          pageSize={DEFAULT_PAGE_SIZE}
          total={data?.total}
          onPageChange={(p) =>
            void navigate({ search: (prev) => ({ ...prev, page: p }), replace: true })
          }
        />
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add User</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="u-name">Full name</Label>
              <Input id="u-name" {...register("full_name")} />
              {errors.full_name && (
                <p className="text-xs text-destructive">{errors.full_name.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="u-email">Email</Label>
              <Input id="u-email" type="email" {...register("email")} />
              {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="u-password">Temporary password</Label>
                <Input id="u-password" type="password" {...register("password")} />
                {errors.password && (
                  <p className="text-xs text-destructive">{errors.password.message}</p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="u-role">Role</Label>
                <Select id="u-role" {...register("role")}>
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {ROLE_LABELS[r]}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating…" : "Create User"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
