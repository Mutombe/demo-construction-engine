import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  Buildings,
  Check,
  Desktop,
  Moon,
  PlugsConnected,
  ShieldCheck,
  Sun,
  UserCircle,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/features/auth/hooks";
import { ROLE_PERMISSIONS, type Permission } from "@/features/auth/permissions";
import { useAiStatus } from "@/features/ai/useAiStatus";
import { useTheme, type ThemePreference } from "@/features/settings/theme";
import { errDetail } from "@/lib/api/errors";
import {
  useGetSettings,
  useUpdateMe,
  useUpdateSettings,
} from "@/lib/api/generated/endpoints";
import { ROLE_LABELS } from "@/lib/format";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/settings/")({ component: SettingsPage });

const SECTIONS = [
  { key: "profile", label: "Profile", icon: <UserCircle /> },
  { key: "appearance", label: "Appearance", icon: <Sun /> },
  { key: "company", label: "Company", icon: <Buildings /> },
  { key: "integrations", label: "Integrations", icon: <PlugsConnected /> },
  { key: "permissions", label: "Permissions", icon: <ShieldCheck /> },
] as const;

type SectionKey = (typeof SECTIONS)[number]["key"];

const THEMES: { value: ThemePreference; label: string; icon: React.ReactNode; hint: string }[] = [
  { value: "light", label: "Light", icon: <Sun />, hint: "Always light" },
  { value: "dark", label: "Dark", icon: <Moon />, hint: "Always dark" },
  { value: "system", label: "System", icon: <Desktop />, hint: "Follow the device" },
];

function SettingsPage() {
  const [section, setSection] = useState<SectionKey>("profile");

  return (
    <div>
      <PageHeader title="Settings" description="Your account, this company and how the app looks" />

      <div className="flex flex-col gap-5 lg:flex-row">
        <nav className="flex gap-1 overflow-x-auto lg:w-52 lg:shrink-0 lg:flex-col">
          {SECTIONS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setSection(item.key)}
              className={cn(
                "flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors [&_svg]:size-4",
                section === item.key
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>

        <div className="min-w-0 flex-1">
          {section === "profile" && <ProfileSection />}
          {section === "appearance" && <AppearanceSection />}
          {section === "company" && <CompanySection />}
          {section === "integrations" && <IntegrationsSection />}
          {section === "permissions" && <PermissionsSection />}
        </div>
      </div>
    </div>
  );
}

function ProfileSection() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const updateMe = useUpdateMe();
  const [fullName, setFullName] = useState(user?.full_name ?? "");

  useEffect(() => setFullName(user?.full_name ?? ""), [user]);

  const save = async () => {
    try {
      await updateMe.mutateAsync({ data: { full_name: fullName } });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/auth/me"] });
      toast.success("Profile updated");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Your account</CardTitle>
      </CardHeader>
      <CardContent className="max-w-md space-y-4">
        <div className="space-y-1.5">
          <Label>Full name</Label>
          <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>Email</Label>
          <Input value={user?.email ?? ""} disabled />
          <p className="text-xs text-muted-foreground">
            Your email is how you sign in, so an administrator has to change it.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label>Role</Label>
          <div>
            <Badge variant="secondary">
              {user ? ROLE_LABELS[user.role] : ""}
            </Badge>
          </div>
        </div>
        <Button disabled={updateMe.isPending || !fullName.trim()} onClick={() => void save()}>
          {updateMe.isPending ? "Saving…" : "Save Changes"}
        </Button>
      </CardContent>
    </Card>
  );
}

function AppearanceSection() {
  const { preference, setPreference } = useTheme();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Theme</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-3">
          {THEMES.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setPreference(option.value)}
              className={cn(
                "flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors [&_svg]:size-5",
                preference === option.value
                  ? "border-primary bg-primary/5"
                  : "hover:border-border hover:bg-accent",
              )}
            >
              <span className="flex w-full items-center justify-between">
                {option.icon}
                {preference === option.value && <Check className="size-4 text-primary" />}
              </span>
              <span className="text-sm font-medium">{option.label}</span>
              <span className="text-xs text-muted-foreground">{option.hint}</span>
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Saved on this device. Choosing System follows your operating system, including when
          it switches at sunset.
        </p>
      </CardContent>
    </Card>
  );
}

function CompanySection() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { data: company } = useGetSettings();
  const update = useUpdateSettings();
  const canEdit = user?.role === "admin";

  const [form, setForm] = useState({
    name: "",
    currency: "",
    vat_rate_pct: "",
    default_retention_pct: "",
  });

  useEffect(() => {
    if (company) {
      setForm({
        name: company.name ?? "",
        currency: company.currency ?? "",
        vat_rate_pct: String(company.vat_rate_pct ?? ""),
        default_retention_pct: String(company.default_retention_pct ?? ""),
      });
    }
  }, [company]);

  const save = async () => {
    try {
      await update.mutateAsync({ data: form });
      await queryClient.invalidateQueries({ queryKey: ["/api/v1/company-settings"] });
      toast.success("Company settings saved");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Company</CardTitle>
      </CardHeader>
      <CardContent className="max-w-lg space-y-4">
        <div className="space-y-1.5">
          <Label>Company name</Label>
          <Input
            value={form.name}
            disabled={!canEdit}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label>Currency</Label>
            <Input
              value={form.currency}
              disabled={!canEdit}
              maxLength={3}
              onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>VAT %</Label>
            <Input
              type="number"
              step="0.01"
              value={form.vat_rate_pct}
              disabled={!canEdit}
              onChange={(e) => setForm({ ...form, vat_rate_pct: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Retention %</Label>
            <Input
              type="number"
              step="0.01"
              value={form.default_retention_pct}
              disabled={!canEdit}
              onChange={(e) => setForm({ ...form, default_retention_pct: e.target.value })}
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Retention is the default applied to new projects. Changing it here does not alter
          contracts already running.
        </p>
        {canEdit ? (
          <Button disabled={update.isPending} onClick={() => void save()}>
            {update.isPending ? "Saving…" : "Save Changes"}
          </Button>
        ) : (
          <p className="text-xs text-muted-foreground">
            Only an administrator can change these.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function IntegrationsSection() {
  const { aiAvailable: available, loaded } = useAiStatus();

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Claude</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-2">
            <Badge variant={available ? "success" : "outline"}>
              {!loaded ? "Checking" : available ? "Connected" : "Not configured"}
            </Badge>
            <span className="text-sm text-muted-foreground">
              Powers the assistant, document reading and drafting.
            </span>
          </div>
          {loaded && !available && (
            <p className="text-xs text-muted-foreground">
              Add <code className="rounded bg-muted px-1">ANTHROPIC_API_KEY</code> to the
              backend <code className="rounded bg-muted px-1">.env</code> and restart the
              server. The key is never stored in the database or sent to the browser.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">API access</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Everything in this app is a REST endpoint, so accounting and other systems can read
            and write the same data.
          </p>
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="inline-block font-medium text-primary underline-offset-2 hover:underline"
          >
            Open the API reference
          </a>
        </CardContent>
      </Card>
    </div>
  );
}

const PERMISSION_GROUPS: { title: string; match: string }[] = [
  { title: "Projects", match: "project" },
  { title: "Tasks and programme", match: "task" },
  { title: "BOQ and cost", match: "boq" },
  { title: "Procurement", match: "procurement" },
  { title: "Requests", match: "requisition" },
  { title: "Inventory", match: "inventory" },
  { title: "Site", match: "site" },
  { title: "Expenses", match: "expense" },
  { title: "Valuations", match: "valuation" },
  { title: "Payroll", match: "payroll" },
  { title: "Documents", match: "media" },
  { title: "AI", match: "ingestion" },
  { title: "Administration", match: "users" },
];

const ROLES = Object.keys(ROLE_PERMISSIONS) as (keyof typeof ROLE_PERMISSIONS)[];

/** Shows exactly what each role can do, read from the same table the app
 *  enforces, so it cannot drift from reality. */
function PermissionsSection() {
  const allPermissions = Array.from(
    new Set(Object.values(ROLE_PERMISSIONS).flat()),
  ).sort() as Permission[];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">What each role can do</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Permission</th>
                {ROLES.map((role) => (
                  <th key={role} className="px-3 py-2 text-center font-medium">
                    {ROLE_LABELS[role]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PERMISSION_GROUPS.map((group) => {
                const rows = allPermissions.filter((p) => p.startsWith(group.match));
                if (rows.length === 0) return null;
                return (
                  <>
                    <tr key={group.title} className="border-t bg-muted/20">
                      <td
                        colSpan={ROLES.length + 1}
                        className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wide"
                      >
                        {group.title}
                      </td>
                    </tr>
                    {rows.map((permission) => (
                      <tr key={permission} className="border-t">
                        <td className="px-4 py-1.5 font-mono text-xs">{permission}</td>
                        {ROLES.map((role) => (
                          <td key={role} className="px-3 py-1.5 text-center">
                            {ROLE_PERMISSIONS[role].includes(permission) ? (
                              <Check className="mx-auto size-3.5 text-success" />
                            ) : (
                              <span className="text-muted-foreground/40">·</span>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="border-t px-4 py-2 text-xs text-muted-foreground">
          Roles are fixed in this version. Changing someone's access means changing their role
          in Administration.
        </p>
      </CardContent>
    </Card>
  );
}
