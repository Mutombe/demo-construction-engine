import { createFileRoute } from "@tanstack/react-router";
import { DownloadSimple, FileXls } from "@phosphor-icons/react";
import { useState, type ReactNode } from "react";
import { toast } from "@/lib/toast";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { downloadFile } from "@/lib/api/download";
import { useListProjects } from "@/lib/api/generated/endpoints";

export const Route = createFileRoute("/_app/reports/")({
  component: ReportsPage,
});

function ExportButtons({
  path,
  params,
  disabled,
  stem,
}: {
  path: string;
  params: Record<string, string>;
  disabled?: boolean;
  stem: string;
}) {
  const [busy, setBusy] = useState(false);
  const run = async (format: "csv" | "xlsx") => {
    setBusy(true);
    try {
      const search = new URLSearchParams({ ...params, format }).toString();
      await downloadFile(`/api/v1/reports/${path}?${search}`, `${stem}.${format}`);
    } catch {
      toast.error("Export failed — check the filters and try again");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex gap-2">
      <Button variant="outline" size="sm" disabled={disabled || busy} onClick={() => void run("csv")}>
        <DownloadSimple /> CSV
      </Button>
      <Button size="sm" disabled={disabled || busy} onClick={() => void run("xlsx")}>
        <FileXls /> Excel
      </Button>
    </div>
  );
}

function ReportCard({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description: string;
  children?: ReactNode;
  footer: ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {children}
        <div className="pt-1">{footer}</div>
      </CardContent>
    </Card>
  );
}

const COST_SOURCES = [
  "",
  "manual",
  "expense",
  "purchase_order",
  "invoice",
  "payroll",
  "inventory_issue",
];

function ReportsPage() {
  const { data: projects } = useListProjects({ page_size: 100 });
  const [costProject, setCostProject] = useState("");
  const [ledgerProject, setLedgerProject] = useState("");
  const [ledgerSource, setLedgerSource] = useState("");
  const [registerProject, setRegisterProject] = useState("");
  const [expenseProject, setExpenseProject] = useState("");
  const [expenseStatus, setExpenseStatus] = useState("");
  const [lowStockOnly, setLowStockOnly] = useState(false);

  const projectOptions = (
    <>
      <option value="">All Projects</option>
      {projects?.items.map((p) => (
        <option key={p.id} value={p.id}>
          {p.code} — {p.name}
        </option>
      ))}
    </>
  );

  return (
    <div>
      <PageHeader
        title="Reports"
        description="Download registers and cost reports as CSV or Excel"
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <ReportCard
          title="Project Cost Report"
          description="Budget vs actual per BOQ line, with variance and unallocated costs."
          footer={
            <ExportButtons
              path="project-cost"
              params={costProject ? { project_id: costProject } : {}}
              disabled={!costProject}
              stem="project_cost_report"
            />
          }
        >
          <div className="space-y-1.5">
            <Label>Project (required)</Label>
            <Select value={costProject} onChange={(e) => setCostProject(e.target.value)}>
              <option value="">Select Project…</option>
              {projects?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} — {p.name}
                </option>
              ))}
            </Select>
          </div>
        </ReportCard>

        <ReportCard
          title="Cost Ledger"
          description="Every cost entry for a project with BOQ codes, source and reference."
          footer={
            <ExportButtons
              path="cost-ledger"
              params={{
                ...(ledgerProject ? { project_id: ledgerProject } : {}),
                ...(ledgerSource ? { source: ledgerSource } : {}),
              }}
              disabled={!ledgerProject}
              stem="cost_ledger"
            />
          }
        >
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label>Project (required)</Label>
              <Select value={ledgerProject} onChange={(e) => setLedgerProject(e.target.value)}>
                <option value="">Select Project…</option>
                {projects?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} — {p.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Source</Label>
              <Select value={ledgerSource} onChange={(e) => setLedgerSource(e.target.value)}>
                {COST_SOURCES.map((s) => (
                  <option key={s} value={s}>
                    {s === "" ? "All Sources" : s.replace("_", " ")}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </ReportCard>

        <ReportCard
          title="Procurement Register"
          description="RFQs, quotes and purchase orders in one register, with statuses."
          footer={
            <ExportButtons
              path="procurement-register"
              params={registerProject ? { project_id: registerProject } : {}}
              stem="procurement_register"
            />
          }
        >
          <div className="space-y-1.5">
            <Label>Project</Label>
            <Select value={registerProject} onChange={(e) => setRegisterProject(e.target.value)}>
              {projectOptions}
            </Select>
          </div>
        </ReportCard>

        <ReportCard
          title="Expense Register"
          description="Expense claims with claimant, approver and approval status."
          footer={
            <ExportButtons
              path="expense-register"
              params={{
                ...(expenseProject ? { project_id: expenseProject } : {}),
                ...(expenseStatus ? { status: expenseStatus } : {}),
              }}
              stem="expense_register"
            />
          }
        >
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label>Project</Label>
              <Select value={expenseProject} onChange={(e) => setExpenseProject(e.target.value)}>
                {projectOptions}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={expenseStatus} onChange={(e) => setExpenseStatus(e.target.value)}>
                <option value="">All Statuses</option>
                {["pending", "approved", "rejected", "cancelled"].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </ReportCard>

        <ReportCard
          title="Stock Valuation"
          description="Store stock at weighted-average cost, with reorder flags."
          footer={
            <ExportButtons
              path="stock-valuation"
              params={lowStockOnly ? { low_stock_only: "true" } : {}}
              stem="stock_valuation"
            />
          }
        >
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={lowStockOnly}
              onChange={(e) => setLowStockOnly(e.target.checked)}
            />
            Low-stock items only
          </label>
        </ReportCard>
      </div>
    </div>
  );
}
