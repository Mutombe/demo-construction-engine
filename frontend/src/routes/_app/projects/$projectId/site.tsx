import { createFileRoute } from "@tanstack/react-router";
import { CheckCircle2, FileText, Plus, RotateCcw, Sparkles } from "lucide-react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePermission } from "@/features/auth/hooks";
import { DiaryEntryDialog } from "@/features/site/DiaryEntryDialog";
import { RaiseIssueDialog, ResolveIssueDialog } from "@/features/site/IssueDialogs";
import { IssueStatusBadge, SeverityBadge, WeatherBadge } from "@/features/site/StatusBadges";
import { WeeklyReportDialog } from "@/features/site/WeeklyReportDialog";
import {
  useListDiaryEntries,
  useListSiteIssues,
  useReopenSiteIssue,
} from "@/lib/api/generated/endpoints";
import type { DiaryEntryRead } from "@/lib/api/generated/model";
import { fmtDate } from "@/lib/format";

export const Route = createFileRoute("/_app/projects/$projectId/site")({
  component: SiteTab,
});

function SiteTab() {
  const { projectId } = Route.useParams();
  const queryClient = useQueryClient();
  const canWrite = usePermission("site:write");
  const { data: diary } = useListDiaryEntries(projectId, { page_size: 30 });
  const { data: issues } = useListSiteIssues(projectId, { page_size: 50 });
  const reopenMutation = useReopenSiteIssue();

  const [diaryDialog, setDiaryDialog] = useState(false);
  const [editingEntry, setEditingEntry] = useState<DiaryEntryRead | null>(null);
  const [issueDialog, setIssueDialog] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [reportDialog, setReportDialog] = useState(false);

  const reopen = async (issueId: string) => {
    try {
      await reopenMutation.mutateAsync({ issueId });
      await queryClient.invalidateQueries();
    } catch {
      toast.error("Could not reopen issue");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end gap-2">
        <Can perm="site:write">
          <Button variant="outline" onClick={() => setReportDialog(true)}>
            <Sparkles className="text-primary" /> Draft weekly report
          </Button>
          <Button
            variant="outline"
            onClick={() => setIssueDialog(true)}
          >
            <Plus /> Raise issue
          </Button>
          <Button
            onClick={() => {
              setEditingEntry(null);
              setDiaryDialog(true);
            }}
          >
            <FileText /> New diary entry
          </Button>
        </Can>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Daily site diary</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Weather</TableHead>
                <TableHead className="text-right">Labour</TableHead>
                <TableHead>Work done</TableHead>
                <TableHead>Delays</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!diary?.items.length && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                    No diary entries yet.
                  </TableCell>
                </TableRow>
              )}
              {diary?.items.map((entry) => (
                <TableRow
                  key={entry.id}
                  className={canWrite ? "cursor-pointer" : undefined}
                  onClick={
                    canWrite
                      ? () => {
                          setEditingEntry(entry);
                          setDiaryDialog(true);
                        }
                      : undefined
                  }
                >
                  <TableCell className="whitespace-nowrap font-medium">
                    {fmtDate(entry.entry_date)}
                  </TableCell>
                  <TableCell>
                    <WeatherBadge status={entry.weather ?? "sunny"} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {entry.labour_headcount}
                  </TableCell>
                  <TableCell className="max-w-md truncate text-sm">{entry.work_done}</TableCell>
                  <TableCell className="max-w-48 truncate text-sm text-destructive">
                    {entry.delays ?? ""}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Issues & incidents</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Issue</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Raised</TableHead>
                <TableHead>Resolved</TableHead>
                {canWrite && <TableHead className="w-32" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {!issues?.items.length && (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                    No issues raised. 🎉
                  </TableCell>
                </TableRow>
              )}
              {issues?.items.map((issue) => (
                <TableRow key={issue.id}>
                  <TableCell>
                    <div className="font-medium">{issue.title}</div>
                    {issue.resolution_notes && (
                      <div className="max-w-md truncate text-xs text-muted-foreground">
                        {issue.resolution_notes}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <SeverityBadge status={issue.severity ?? "medium"} />
                  </TableCell>
                  <TableCell>
                    <IssueStatusBadge status={issue.status ?? "open"} />
                  </TableCell>
                  <TableCell className="text-sm">{fmtDate(issue.raised_date)}</TableCell>
                  <TableCell className="text-sm">
                    {issue.resolved_date ? fmtDate(issue.resolved_date) : "—"}
                  </TableCell>
                  {canWrite && (
                    <TableCell>
                      {issue.status === "open" ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setResolvingId(issue.id)}
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" /> Resolve
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => void reopen(issue.id)}
                        >
                          <RotateCcw className="h-3.5 w-3.5" /> Reopen
                        </Button>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <DiaryEntryDialog
        open={diaryDialog}
        onOpenChange={setDiaryDialog}
        projectId={projectId}
        entry={editingEntry}
      />
      <RaiseIssueDialog open={issueDialog} onOpenChange={setIssueDialog} projectId={projectId} />
      <ResolveIssueDialog issueId={resolvingId} onClose={() => setResolvingId(null)} />
      <WeeklyReportDialog
        open={reportDialog}
        onOpenChange={setReportDialog}
        projectId={projectId}
      />
    </div>
  );
}
