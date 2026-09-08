import { zodResolver } from "@hookform/resolvers/zod";
import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { Plus } from "@phosphor-icons/react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { errDetail } from "@/lib/api/errors";
import { useCreateUser, useListUsers, useUpdateUser } from "@/lib/api/generated/endpoints";
import { fmtDate, ROLE_LABELS } from "@/lib/format";
import { toast } from "@/lib/toast";
import { EntityLink } from "@/components/ui/linked-row";

const ROLES = ["admin", "project_manager", "site_manager", "procurement_officer", "viewer"];

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  full_name: z.string().min(1, "Required"),
  password: z.string().min(8, "Min 8 characters"),
  role: z.enum(["admin", "project_manager", "site_manager", "procurement_officer", "viewer"]),
});
type FormValues = z.infer<typeof schema>;

export function UsersPanel() {
  const [page, setPage] = useState(1);
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
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const changeRole = async (userId: string, role: string) => {
    try {
      await updateMutation.mutateAsync({ userId, data: { role: role as FormValues["role"] } });
      await queryClient.invalidateQueries();
      toast.success("Role updated");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const toggleActive = async (userId: string, isActive: boolean) => {
    try {
      await updateMutation.mutateAsync({ userId, data: { is_active: !isActive } });
      await queryClient.invalidateQueries();
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Everyone with an account. Changing a role takes effect the next time they load a page.
        </p>
        <Button onClick={() => setDialogOpen(true)} title="Create an account directly">
          <Plus /> Add User
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
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
              {isLoading && !data && <TableSkeleton columns={6} />}
              {data?.items.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">
                    {/* The row carries its own controls, so the name is the link
                        rather than the whole row — a click meant for the role
                        picker must not navigate away. */}
                    <EntityLink to="/admin/users/$userId" params={{ userId: u.id }}>
                      {u.full_name}
                    </EntityLink>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{u.email}</TableCell>
                  <TableCell>
                    <Select
                      className="h-7 w-44 text-xs"
                      value={u.role}
                      disabled={u.id === currentUser?.id}
                      title={
                        u.id === currentUser?.id
                          ? "You cannot change your own role"
                          : "Change what this person can do"
                      }
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
                        title={
                          u.is_active
                            ? "Block sign in without deleting the history"
                            : "Let them sign in again"
                        }
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
            onPageChange={setPage}
          />
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add User</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground">
            You will need to hand them the password yourself. Sending an invite instead lets them
            set their own.
          </p>
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
