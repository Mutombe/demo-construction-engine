import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { CheckCircle, Warning } from "@phosphor-icons/react";
import { useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Can } from "@/components/layout/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { ErrorState } from "@/components/ui/list-state";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { CommentThread } from "@/features/comments/CommentThread";
import { MediaPanel } from "@/features/media/MediaPanel";
import { errDetail } from "@/lib/api/errors";
import {
  useGetSiteIssue,
  useReopenSiteIssue,
  useResolveSiteIssue,
} from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/_app/site/issues/$issueId")({
  component: SiteIssueDetail,
});

const SEVERITY: Record<string, "outline" | "warning" | "destructive"> = {
  low: "outline",
  medium: "warning",
  high: "destructive",
  critical: "destructive",
};

/** One thing that went wrong on site, with everything about it in one place.
 *
 *  An issue is the record somebody points at months later when the argument is
 *  about who knew what and when, so it needs a page of its own and a thread
 *  attached to it. */
function SiteIssueDetail() {
  const { issueId } = Route.useParams();
  const queryClient = useQueryClient();
  const query = useGetSiteIssue(issueId);
  const resolve = useResolveSiteIssue();
  const reopen = useReopenSiteIssue();
  const [resolution, setResolution] = useState("");
  const [resolving, setResolving] = useState(false);

  const issue = query.data;
  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (!issue) return <PageSkeleton rows={4} />;

  const open = issue.status === "open";

  const close = async () => {
    try {
      await resolve.mutateAsync({
        issueId,
        data: { resolution_notes: resolution || null },
      });
      await queryClient.invalidateQueries();
      setResolving(false);
      setResolution("");
      toast.success("Issue closed");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  const putBack = async () => {
    try {
      await reopen.mutateAsync({ issueId });
      await queryClient.invalidateQueries();
      toast.success("Issue reopened");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Projects", to: "/projects" },
          {
            label: "Site",
            to: "/projects/$projectId/site",
            params: { projectId: issue.project_id },
          },
          { label: issue.title },
        ]}
      />

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">{issue.title}</h1>
            <Badge variant={SEVERITY[issue.severity] ?? "outline"}>{issue.severity}</Badge>
            {open ? (
              <Badge variant="warning">Open</Badge>
            ) : (
              <Badge variant="success">Resolved</Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Raised {fmtDate(issue.raised_date)}
            {issue.resolved_date && <> · closed {fmtDate(issue.resolved_date)}</>}
          </p>
        </div>
        <Can perm="project:write">
          {open ? (
            <Button onClick={() => setResolving(true)}>
              <CheckCircle /> Close It
            </Button>
          ) : (
            <Button variant="outline" onClick={() => void putBack()}>
              Reopen
            </Button>
          )}
        </Can>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Warning /> What happened
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm">
                {issue.description || "No detail was written down beyond the title."}
              </p>
            </CardContent>
          </Card>

          {resolving && (
            <Card>
              <CardContent className="space-y-2 pt-4">
                <Label htmlFor="resolution">How it was put right</Label>
                <Textarea
                  id="resolution"
                  rows={3}
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value)}
                  placeholder="Scaffold tie refitted and the bay re-inspected"
                />
                <p className="text-xs text-muted-foreground">
                  Worth writing. An issue closed with no explanation is one nobody can
                  learn from.
                </p>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setResolving(false)}>
                    Cancel
                  </Button>
                  <Button size="sm" onClick={() => void close()}>
                    Close Issue
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {issue.resolution_notes && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">How it was put right</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm">{issue.resolution_notes}</p>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Photographs</CardTitle>
            </CardHeader>
            <CardContent>
              <MediaPanel entityType="site_issue" entityId={issueId} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Discussion</CardTitle>
            </CardHeader>
            <CardContent>
              <CommentThread entityType="site_issue" entityId={issueId} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Severity" value={issue.severity} />
              <Row label="Status" value={open ? "Open" : "Resolved"} />
              <Row label="Raised" value={fmtDate(issue.raised_date)} />
              <Row
                label="Closed"
                value={issue.resolved_date ? fmtDate(issue.resolved_date) : "Still open"}
              />
              <div className="border-t pt-2">
                <Link
                  to="/projects/$projectId/site"
                  params={{ projectId: issue.project_id }}
                  className="text-sm text-muted-foreground hover:text-foreground hover:underline"
                >
                  All issues on this site
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate text-right font-medium capitalize">{value}</span>
    </div>
  );
}
