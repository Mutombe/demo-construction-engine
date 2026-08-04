import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { Link, createFileRoute, redirect } from "@tanstack/react-router";
import {
  ArrowCounterClockwise,
  ClockCounterClockwise,
  Copy,
  EnvelopeSimple,
  Plus,
  Prohibit,
  TrashSimple,
  UsersThree,
} from "@phosphor-icons/react";
import { useState } from "react";
import { z } from "zod";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
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
import { UsersPanel } from "@/features/admin/UsersPanel";
import { can } from "@/features/auth/permissions";
import { useAuthStore } from "@/features/auth/store";
import { errDetail } from "@/lib/api/errors";
import {
  useCreateInvite,
  useListActivity,
  useListActivityActions,
  useListInvites,
  useListTrash,
  useListTrashTypes,
  usePurgeDeleted,
  useRestoreDeleted,
  useRevokeInvite,
} from "@/lib/api/generated/endpoints";
import { fmtDate, ROLE_LABELS } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

const searchSchema = z.object({
  tab: z.enum(["users", "invites", "activity", "trash"]).optional().default("users"),
  page: z.number().int().min(1).optional().default(1),
});

export const Route = createFileRoute("/_app/admin/")({
  validateSearch: searchSchema,
  beforeLoad: () => {
    // The API refuses non-admins anyway; this just avoids showing a page made
    // entirely of 403s.
    if (!can(useAuthStore.getState().user?.role, "users:manage")) throw redirect({ to: "/" });
  },
  component: AdminPage,
});

const TABS = [
  { key: "users", label: "Users", icon: <UsersThree /> },
  { key: "invites", label: "Invites", icon: <EnvelopeSimple /> },
  { key: "activity", label: "Activity Log", icon: <ClockCounterClockwise /> },
  { key: "trash", label: "Trash", icon: <TrashSimple /> },
] as const;

function AdminPage() {
  const { tab, page } = Route.useSearch();
  const navigate = Route.useNavigate();

  return (
    <div>
      <PageHeader
        title="Administration"
        description="Who has access, who is joining, and what has been done"
      />

      <div className="mb-4 border-b">
        <nav className="-mb-px flex gap-1">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => void navigate({ search: { tab: item.key, page: 1 } })}
              className={cn(
                "flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-sm font-medium transition-colors [&_svg]:size-4",
                tab === item.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
              )}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      {tab === "users" && <UsersPanel />}
      {tab === "invites" && <InvitesPanel />}
      {tab === "activity" && (
        <ActivityPanel
          page={page}
          onPageChange={(next) =>
            void navigate({ search: (prev) => ({ ...prev, page: next }) })
          }
        />
      )}
      {tab === "trash" && (
        <TrashPanel
          page={page}
          onPageChange={(next) =>
            void navigate({ search: (prev) => ({ ...prev, page: next }) })
          }
        />
      )}
    </div>
  );
}

const INVITE_STATUS = {
  pending: "warning",
  accepted: "success",
  revoked: "outline",
  expired: "outline",
} as const;

function InvitesPanel() {
  const queryClient = useQueryClient();
  const { data: invites, isLoading } = useListInvites();
  const revoke = useRevokeInvite();
  const [formOpen, setFormOpen] = useState(false);
  const [issuedLink, setIssuedLink] = useState<string | null>(null);

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["/api/v1/admin/invites"] });

  const cancel = async (invite: { id: string; email: string }) => {
    if (
      !(await confirmDialog({
        title: "Revoke invite",
        message: `Revoke the invite for ${invite.email}? The link stops working immediately.`,
        tone: "danger",
      }))
    )
      return;
    try {
      await revoke.mutateAsync({ inviteId: invite.id });
      await refresh();
      toast.success("Invite revoked");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Button onClick={() => setFormOpen(true)}>
          <Plus /> Invite Someone
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Person</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && <TableSkeleton columns={5} rows={4} />}
              {!isLoading && !invites?.length && (
                <TableRow>
                  <TableCell colSpan={5} className="p-0">
                    <EmptyState
                      icon={<EnvelopeSimple />}
                      title="Nobody has been invited yet"
                      hint="Invite someone by email and they set their own password when they accept."
                    />
                  </TableCell>
                </TableRow>
              )}
              {invites?.map((invite) => (
                <TableRow key={invite.id}>
                  <TableCell>
                    <div className="font-medium">{invite.full_name}</div>
                    <div className="text-xs text-muted-foreground">{invite.email}</div>
                  </TableCell>
                  <TableCell className="text-sm">{ROLE_LABELS[invite.role]}</TableCell>
                  <TableCell>
                    <Badge variant={INVITE_STATUS[invite.status as keyof typeof INVITE_STATUS]}>
                      {invite.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {fmtDate(invite.expires_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    {invite.status === "pending" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive"
                        title="Revoke this invite"
                        onClick={() => void cancel(invite)}
                      >
                        <Prohibit />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <InviteDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        onCreated={async (url) => {
          setFormOpen(false);
          setIssuedLink(url);
          await refresh();
        }}
      />

      <Dialog open={!!issuedLink} onOpenChange={() => setIssuedLink(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Invite link</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground">
            Send this to them. It is shown once and cannot be recovered, because only a hash of
            it is stored.
          </p>
          <div className="flex gap-2">
            <Input readOnly value={issuedLink ?? ""} className="font-mono text-xs" />
            <Button
              variant="outline"
              title="Copy the link"
              onClick={() => {
                void navigator.clipboard.writeText(issuedLink ?? "");
                toast.success("Link copied");
              }}
            >
              <Copy />
            </Button>
          </div>
          <DialogFooter>
            <Button onClick={() => setIssuedLink(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function InviteDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (url: string) => Promise<void>;
}) {
  const create = useCreateInvite();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("site_manager");

  const submit = async () => {
    if (!email.trim() || !fullName.trim()) {
      toast.error("Name and email are both needed");
      return;
    }
    try {
      const invite = await create.mutateAsync({
        data: { email, full_name: fullName, role: role as never },
      });
      setEmail("");
      setFullName("");
      await onCreated(invite.invite_url);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Invite Someone</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          They set their own password when they accept, so you never handle it.
        </p>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Full name</Label>
            <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Email</Label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.com"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Role</Label>
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={create.isPending} onClick={() => void submit()}>
            {create.isPending ? "Creating…" : "Create Invite"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const TRASH_TYPE_LABELS: Record<string, string> = {
  client: "Client",
  project: "Project",
  phase: "Phase",
  task: "Task",
  boq_section: "BOQ Section",
  boq_item: "BOQ Item",
  cost_entry: "Cost Entry",
  diary_entry: "Site Diary",
  document: "Document",
  rfq: "Request For Quotation",
  quote: "Quote",
  valuation: "Valuation",
  pay_item: "Pay Item",
  timesheet: "Timesheet",
  pay_run: "Pay Run",
};

function TrashPanel({
  page,
  onPageChange,
}: {
  page: number;
  onPageChange: (page: number) => void;
}) {
  const queryClient = useQueryClient();
  const [entityType, setEntityType] = useState("");
  const { data: types } = useListTrashTypes();
  const { data, isLoading } = useListTrash(
    { page, page_size: DEFAULT_PAGE_SIZE, entity_type: entityType || undefined },
    { query: { placeholderData: keepPreviousData } },
  );
  const restore = useRestoreDeleted();
  const purge = usePurgeDeleted();

  const refresh = () => queryClient.invalidateQueries();

  const putBack = async (record: { id: string; label: string }) => {
    try {
      await restore.mutateAsync({ recordId: record.id });
      await refresh();
      toast.success(`${record.label} is back`);
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const deleteForever = async (record: { id: string; label: string }) => {
    if (
      !(await confirmDialog({
        title: "Delete permanently",
        message: `${record.label} will be gone for good. There is no way back from this.`,
        confirmLabel: "Delete Permanently",
        tone: "danger",
      }))
    )
      return;
    try {
      await purge.mutateAsync({ recordId: record.id });
      await refresh();
      toast.success("Deleted permanently");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Type:</span>
        <Select
          className="w-56"
          value={entityType}
          onChange={(e) => {
            setEntityType(e.target.value);
            onPageChange(1);
          }}
        >
          <option value="">Everything</option>
          {types?.map((name) => (
            <option key={name} value={name}>
              {TRASH_TYPE_LABELS[name] ?? name.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>What it was</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Deleted</TableHead>
                <TableHead>By</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && !data && <TableSkeleton columns={5} />}
              {!isLoading && !data?.items.length && (
                <TableRow>
                  <TableCell colSpan={5} className="p-0">
                    <EmptyState
                      icon={<TrashSimple />}
                      title="The trash is empty"
                      hint="Anything deleted from the system lands here first, so it can be put back."
                    />
                  </TableCell>
                </TableRow>
              )}
              {data?.items.map((record) => (
                <TableRow key={record.id}>
                  <TableCell className="font-medium">{record.label}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {TRASH_TYPE_LABELS[record.entity_type] ??
                      record.entity_type.replace(/_/g, " ")}
                    {record.row_count > 1 && (
                      <span className="ml-1 text-xs">
                        and {record.row_count - 1} related{" "}
                        {record.row_count === 2 ? "record" : "records"}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                    {fmtDate(record.deleted_at)}
                  </TableCell>
                  <TableCell className="text-sm">{record.deleted_by_name ?? "System"}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!record.restorable || restore.isPending}
                        title={
                          record.restorable
                            ? "Put this back where it was"
                            : "Too much went with this one to keep a copy, so it cannot be put back"
                        }
                        onClick={() => void putBack(record)}
                      >
                        <ArrowCounterClockwise /> Restore
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive"
                        title="Delete permanently"
                        onClick={() => void deleteForever(record)}
                      >
                        <TrashSimple />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <PaginationBar
            page={page}
            pageSize={DEFAULT_PAGE_SIZE}
            total={data?.total}
            onPageChange={onPageChange}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function ActivityPanel({
  page,
  onPageChange,
}: {
  page: number;
  onPageChange: (page: number) => void;
}) {
  const [action, setAction] = useState("");
  const { data: actions } = useListActivityActions();
  const { data, isLoading } = useListActivity(
    { page, page_size: DEFAULT_PAGE_SIZE, action: action || undefined },
    { query: { placeholderData: keepPreviousData } },
  );

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Action:</span>
        <Select
          className="w-56"
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            onPageChange(1);
          }}
        >
          <option value="">Everything</option>
          {actions?.map((name) => (
            <option key={name} value={name}>
              {name.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Who</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>What happened</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && !data && <TableSkeleton columns={4} />}
              {!isLoading && !data?.items.length && (
                <TableRow>
                  <TableCell colSpan={4} className="p-0">
                    <EmptyState
                      icon={<ClockCounterClockwise />}
                      title="Nothing recorded yet"
                      hint="Approvals, issued orders and certificates are recorded here as they happen."
                    />
                  </TableCell>
                </TableRow>
              )}
              {data?.items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                    {fmtDate(entry.created_at)}
                  </TableCell>
                  <TableCell className="text-sm">{entry.user_name ?? "System"}</TableCell>
                  <TableCell>
                    <span className="font-mono text-xs text-muted-foreground">
                      {entry.action}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm">
                    {entry.link_path ? (
                      <Link
                        to={entry.link_path}
                        className="underline-offset-2 hover:text-primary hover:underline"
                      >
                        {entry.summary}
                      </Link>
                    ) : (
                      entry.summary
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
            onPageChange={onPageChange}
          />
        </CardContent>
      </Card>
    </div>
  );
}
