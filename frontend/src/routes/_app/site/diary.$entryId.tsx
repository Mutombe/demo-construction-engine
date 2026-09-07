import { createFileRoute, Link } from "@tanstack/react-router";
import { CloudSun, NotePencil, UsersThree } from "@phosphor-icons/react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/list-state";
import { PageSkeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CommentThread } from "@/features/comments/CommentThread";
import { MediaPanel } from "@/features/media/MediaPanel";
import { useGetDiaryEntry } from "@/lib/api/generated/endpoints";
import { fmtDate } from "@/lib/format";

export const Route = createFileRoute("/_app/site/diary/$entryId")({
  component: DiaryEntryDetail,
});

function weatherLabel(weather: string | undefined) {
  return weather ? (WEATHER_LABELS[weather] ?? weather) : "Not recorded";
}

const WEATHER_LABELS: Record<string, string> = {
  sunny: "Sunny",
  cloudy: "Cloudy",
  rain: "Rain",
  storm: "Storm",
  extreme_heat: "Extreme heat",
};

/** One day on site, on its own page.
 *
 *  A diary entry is the record that gets quoted back years later in a delay
 *  claim, so it needs somewhere to live that can be linked to — not a row that
 *  can only be read inside a list. */
function DiaryEntryDetail() {
  const { entryId } = Route.useParams();
  const query = useGetDiaryEntry(entryId);
  const entry = query.data;

  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (!entry) return <PageSkeleton rows={4} />;

  const labour = entry.labour ?? [];
  const totalHours = labour.reduce((sum, line) => sum + Number(line.quantity ?? 0), 0);
  const overtime = labour.reduce(
    (sum, line) => sum + Number(line.overtime_quantity ?? 0),
    0,
  );

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Projects", to: "/projects" },
          {
            label: "Site",
            to: "/projects/$projectId/site",
            params: { projectId: entry.project_id },
          },
          { label: fmtDate(entry.entry_date) },
        ]}
      />

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            Site diary — {fmtDate(entry.entry_date)}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <CloudSun className="h-3.5 w-3.5" />
              {weatherLabel(entry.weather)}
            </span>
            <span className="inline-flex items-center gap-1">
              <UsersThree className="h-3.5 w-3.5" />
              {entry.labour_headcount ?? 0} on site
            </span>
          </p>
        </div>
        <Link
          to="/projects/$projectId/site"
          params={{ projectId: entry.project_id }}
          className="text-sm text-muted-foreground hover:text-foreground hover:underline"
        >
          Back to the site log
        </Link>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <NotePencil /> Work done
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm">{entry.work_done}</p>
            </CardContent>
          </Card>

          {entry.delays && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Delays</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm">{entry.delays}</p>
              </CardContent>
            </Card>
          )}

          {labour.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Who was on</CardTitle>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Counted once here rather than again on a timesheet.
                </p>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Worker</TableHead>
                      <TableHead>Trade</TableHead>
                      <TableHead className="num">Hours</TableHead>
                      <TableHead className="num">Overtime</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {labour.map((line) => (
                      <TableRow key={line.id}>
                        <TableCell className="font-medium">
                          {line.worker_id ? (
                            <Link
                              to="/payroll/workers/$workerId"
                              params={{ workerId: line.worker_id }}
                              className="hover:underline"
                            >
                              {line.worker_name ?? "Worker"}
                            </Link>
                          ) : (
                            (line.worker_name ?? "Worker")
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {line.trade ?? "—"}
                        </TableCell>
                        <TableCell className="num">{Number(line.quantity)}</TableCell>
                        <TableCell className="num text-muted-foreground">
                          {Number(line.overtime_quantity ?? 0) || "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Photographs</CardTitle>
            </CardHeader>
            <CardContent>
              <MediaPanel entityType="diary_entry" entityId={entryId} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Discussion</CardTitle>
            </CardHeader>
            <CardContent>
              <CommentThread entityType="diary_entry" entityId={entryId} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">The day</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Date" value={fmtDate(entry.entry_date)} />
              <Row
                label="Weather"
                value={weatherLabel(entry.weather)}
              />
              <Row label="Headcount" value={String(entry.labour_headcount ?? 0)} />
              {labour.length > 0 && (
                <>
                  <Row label="Hours worked" value={totalHours.toLocaleString()} />
                  {overtime > 0 && (
                    <Row label="Overtime" value={overtime.toLocaleString()} />
                  )}
                </>
              )}
              {entry.plant_equipment && (
                <div className="border-t pt-2">
                  <div className="text-muted-foreground">Plant on site</div>
                  <div className="mt-0.5 whitespace-pre-wrap">{entry.plant_equipment}</div>
                </div>
              )}
            </CardContent>
          </Card>

          {entry.notes && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Notes</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm">{entry.notes}</p>
              </CardContent>
            </Card>
          )}

          {labour.length === 0 && (
            <Card>
              <CardContent className="py-4 text-sm text-muted-foreground">
                Nobody was recorded by name on this day. Only the headcount was written
                down, so there is nothing to push to timesheets.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate text-right font-medium">{value}</span>
    </div>
  );
}
