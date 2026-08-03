import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ArrowLeft, Buildings, Check, CircleDashed, CircleNotch, DownloadSimple, FileText, HardHat, MapPin, ShieldWarning } from "@phosphor-icons/react";
import { useState } from "react";
import {
  downloadCertificate,
  fetchProject,
  fetchSummary,
  fetchValuations,
  PortalError,
  type PortalProject,
  type PortalValuation,
} from "@/features/portal/api";
import { fmtDate, money, moneyExact } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/portal/$token")({
  component: PortalPage,
});

/* --- shared bits ---------------------------------------------------------- */

function ProgressRing({ pct, size = 64 }: { pct: number; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <svg width={size} height={size} className="shrink-0 -rotate-90">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        strokeWidth={6}
        className="stroke-secondary"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        strokeWidth={6}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c - (c * clamped) / 100}
        className="stroke-primary transition-[stroke-dashoffset] duration-700"
      />
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        className="rotate-90 fill-foreground text-sm font-semibold tabular-nums"
        style={{ transformOrigin: "center" }}
      >
        {Math.round(clamped)}%
      </text>
    </svg>
  );
}

const STATUS_LABEL: Record<string, string> = {
  planning: "Planning",
  active: "In progress",
  on_hold: "On hold",
  completed: "Completed",
  cancelled: "Cancelled",
};

const PHASE_DONE = new Set(["done"]);
const PHASE_ACTIVE = new Set(["in_progress", "blocked"]);

function PortalShell({
  company,
  client,
  children,
}: {
  company?: string;
  client?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-sidebar text-sidebar-foreground">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-5 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <HardHat className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-base font-semibold leading-tight">
              {company ?? "Project portal"}
            </div>
            {client && (
              <div className="truncate text-xs text-sidebar-muted">
                Client portal · {client}
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-5 py-8">{children}</main>
      <footer className="mx-auto max-w-4xl px-5 pb-8 text-center text-xs text-muted-foreground">
        This is a read-only view prepared for you by {company ?? "your contractor"}. Questions?
        Contact your project manager.
      </footer>
    </div>
  );
}

/* --- page ------------------------------------------------------------------ */

function PortalPage() {
  const { token } = Route.useParams();
  const [projectId, setProjectId] = useState<string | null>(null);

  const summaryQuery = useQuery({
    queryKey: ["portal-summary", token],
    queryFn: () => fetchSummary(token),
    retry: false,
    staleTime: 60_000,
  });

  if (summaryQuery.isLoading) {
    return (
      <PortalShell>
        <div className="flex flex-col items-center gap-3 py-24 text-muted-foreground">
          <CircleNotch className="h-6 w-6 animate-spin" />
          Opening your portal…
        </div>
      </PortalShell>
    );
  }

  if (summaryQuery.isError || !summaryQuery.data) {
    const err = summaryQuery.error as PortalError | undefined;
    return (
      <PortalShell>
        <div className="fade-up mx-auto max-w-md rounded-xl border bg-card p-8 text-center shadow-sm">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <ShieldWarning className="h-6 w-6" />
          </div>
          <h1 className="text-lg font-semibold">This link isn't active</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {err?.message ?? "The link may have expired or been replaced."} Please contact your
            project manager for a fresh link.
          </p>
        </div>
      </PortalShell>
    );
  }

  const summary = summaryQuery.data;
  return (
    <PortalShell company={summary.company_name} client={summary.client_name}>
      {projectId ? (
        <ProjectView
          token={token}
          projectId={projectId}
          onBack={() => setProjectId(null)}
        />
      ) : (
        <div className="fade-up space-y-5">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Welcome, {summary.client_name}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {summary.projects.length} project{summary.projects.length === 1 ? "" : "s"} with{" "}
              {summary.company_name}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {summary.projects.map((project, i) => (
              <ProjectCard
                key={project.id}
                project={project}
                onOpen={() => setProjectId(project.id)}
                style={{ animationDelay: `${i * 60}ms` }}
              />
            ))}
          </div>
        </div>
      )}
    </PortalShell>
  );
}

function ProjectCard({
  project,
  onOpen,
  style,
}: {
  project: PortalProject;
  onOpen: () => void;
  style?: React.CSSProperties;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      style={style}
      className="fade-up group flex items-center gap-4 rounded-xl border bg-card p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring motion-reduce:hover:translate-y-0"
    >
      <ProgressRing pct={project.progress_pct} />
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium group-hover:text-primary">{project.name}</div>
        <div className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
          {project.city && (
            <>
              <MapPin className="h-3 w-3" /> {project.city} ·
            </>
          )}{" "}
          {STATUS_LABEL[project.status] ?? project.status}
        </div>
        {project.contract_value && (
          <div className="mt-1 text-xs text-muted-foreground">
            Contract {money(project.contract_value)}
          </div>
        )}
      </div>
    </button>
  );
}

function ProjectView({
  token,
  projectId,
  onBack,
}: {
  token: string;
  projectId: string;
  onBack: () => void;
}) {
  const projectQuery = useQuery({
    queryKey: ["portal-project", token, projectId],
    queryFn: () => fetchProject(token, projectId),
    retry: false,
  });
  const valuationsQuery = useQuery({
    queryKey: ["portal-valuations", token, projectId],
    queryFn: () => fetchValuations(token, projectId),
    retry: false,
  });
  const [downloading, setDownloading] = useState<string | null>(null);

  const project = projectQuery.data;
  if (!project) {
    return (
      <div className="flex justify-center py-24 text-muted-foreground">
        <CircleNotch className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  const download = async (valuation: PortalValuation) => {
    setDownloading(valuation.id);
    try {
      await downloadCertificate(token, valuation);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="fade-up space-y-6">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> All projects
      </button>

      <div className="flex flex-wrap items-center gap-5 rounded-xl border bg-card p-5 shadow-sm">
        <ProgressRing pct={project.progress_pct} size={88} />
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold tracking-tight">{project.name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {project.site_address ?? project.city ?? ""}
          </p>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
            <span>
              <Buildings className="mr-1 inline h-3 w-3" />
              {STATUS_LABEL[project.status] ?? project.status}
            </span>
            {project.planned_end && <span>Target completion {fmtDate(project.planned_end)}</span>}
            {project.contract_value && <span>Contract {money(project.contract_value)}</span>}
          </div>
        </div>
      </div>

      {project.description && (
        <p className="text-sm leading-relaxed text-muted-foreground">{project.description}</p>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Programme
        </h2>
        <ol className="space-y-0">
          {project.phases.map((phase, i) => {
            const done = PHASE_DONE.has(phase.status);
            const active = PHASE_ACTIVE.has(phase.status);
            return (
              <li key={phase.sequence} className="relative flex gap-3 pb-4">
                {i < project.phases.length - 1 && (
                  <span
                    className={cn(
                      "absolute left-[11px] top-6 h-full w-0.5",
                      done ? "bg-primary/50" : "bg-border",
                    )}
                  />
                )}
                <span
                  className={cn(
                    "z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 bg-background",
                    done && "border-primary bg-primary text-primary-foreground",
                    active && "border-primary text-primary",
                    !done && !active && "border-border text-muted-foreground",
                  )}
                >
                  {done ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <CircleDashed className="h-3 w-3" />
                  )}
                </span>
                <div className="min-w-0 pt-0.5">
                  <div
                    className={cn(
                      "text-sm",
                      active ? "font-semibold" : done ? "font-medium" : "text-muted-foreground",
                    )}
                  >
                    {phase.name}
                    {active && (
                      <span className="ml-2 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase text-primary">
                        current
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {fmtDate(phase.planned_start)} → {fmtDate(phase.planned_end)}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Payment certificates
        </h2>
        {(valuationsQuery.data?.length ?? 0) === 0 ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            No certificates issued yet.
          </p>
        ) : (
          <div className="space-y-2">
            {valuationsQuery.data?.map((valuation) => (
              <div
                key={valuation.id}
                className="flex flex-wrap items-center gap-3 rounded-lg border bg-card p-3.5 shadow-sm"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <FileText className="h-4.5 w-4.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">
                    Valuation {valuation.valuation_number}
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      {valuation.doc_number}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Period to {fmtDate(valuation.period_end)}
                    {valuation.status === "paid"
                      ? ` · paid ${fmtDate(valuation.paid_date)}`
                      : ` · issued ${fmtDate(valuation.issued_date)}`}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold tabular-nums">
                    {moneyExact(valuation.net_certified)}
                  </div>
                  <div
                    className={cn(
                      "text-[10px] font-medium uppercase tracking-wide",
                      valuation.status === "paid" ? "text-success" : "text-primary",
                    )}
                  >
                    {valuation.status === "paid" ? "Paid" : "Awaiting payment"}
                  </div>
                </div>
                <button
                  type="button"
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
                  disabled={downloading === valuation.id}
                  onClick={() => void download(valuation)}
                >
                  {downloading === valuation.id ? (
                    <CircleNotch className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <DownloadSimple className="h-3.5 w-3.5" />
                  )}
                  Certificate
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
