import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Bank, CheckCircle, Scales } from "@phosphor-icons/react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { useAuth } from "@/features/auth/hooks";
import { errDetail } from "@/lib/api/errors";
import { useGetJournal, usePostJournal } from "@/lib/api/generated/endpoints";
import { fmtDate, moneyExact } from "@/lib/format";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/_app/accounting/journals/$journalId")({
  component: JournalDetail,
});

/** One journal, with both sides of it.
 *
 *  A journal is the thing an auditor asks to see, so it needs an address of
 *  its own rather than existing only as a row in a list. The lines are shown
 *  with their totals because a journal that does not balance is the one fact
 *  about it that matters most. */
function JournalDetail() {
  const { journalId } = Route.useParams();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const query = useGetJournal(journalId);
  const post = usePostJournal();

  const journal = query.data;
  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (!journal) return <PageSkeleton rows={4} />;

  const lines = journal.lines ?? [];
  const debits = lines.reduce((sum, line) => sum + Number(line.debit ?? 0), 0);
  const credits = lines.reduce((sum, line) => sum + Number(line.credit ?? 0), 0);
  const balanced = Math.abs(debits - credits) < 0.005;
  const posted = journal.status === "posted";

  const publish = async () => {
    try {
      await post.mutateAsync({ journalId });
      await queryClient.invalidateQueries();
      toast.success("Posted to the ledger");
    } catch (err) {
      toast.error(errDetail(err));
    }
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Accounting", to: "/accounting", search: { tab: "journals" } },
          { label: journal.doc_number },
        ]}
      />

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">{journal.memo}</h1>
            {posted ? (
              <Badge variant="success">Posted</Badge>
            ) : (
              <Badge variant="warning">Draft</Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-mono">{journal.doc_number}</span> ·{" "}
            {fmtDate(journal.journal_date)} · raised by {journal.source.replace(/_/g, " ")}
          </p>
        </div>
        {/* Posting is admin-only in the books, so the button is not shown to
            anybody else. Offering one that always fails is worse than not
            offering it, because it misstates who is allowed to do this. */}
        {!posted && balanced && user?.role === "admin" && (
            <Button onClick={() => void publish()}>
              <CheckCircle /> Post It
            </Button>
        )}
      </div>

      {!balanced && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          <Scales weight="fill" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            The two sides differ by {moneyExact(Math.abs(debits - credits))}. It cannot be
            posted until they agree.
          </span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Bank /> Lines
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Account</TableHead>
                    <TableHead>Narration</TableHead>
                    <TableHead className="num">Debit</TableHead>
                    <TableHead className="num">Credit</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell>
                        {/* Every line names an account, and the next question is
                            always what else is in it. */}
                        <Link
                          to="/accounting/accounts/$accountId"
                          params={{ accountId: line.account_id }}
                          className="font-medium hover:underline"
                        >
                          {line.account_code}
                        </Link>
                        <div className="text-xs text-muted-foreground">
                          {line.account_name}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {line.description ?? "—"}
                      </TableCell>
                      <TableCell className="num">
                        {Number(line.debit ?? 0) ? moneyExact(line.debit) : "—"}
                      </TableCell>
                      <TableCell className="num">
                        {Number(line.credit ?? 0) ? moneyExact(line.credit) : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow>
                    <TableCell colSpan={2} className="font-medium">
                      Totals
                    </TableCell>
                    <TableCell className="num font-semibold">{moneyExact(debits)}</TableCell>
                    <TableCell className="num font-semibold">{moneyExact(credits)}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">This journal</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Date" value={fmtDate(journal.journal_date)} />
              <Row label="Raised by" value={journal.source.replace(/_/g, " ")} />
              <Row label="Status" value={posted ? "Posted" : "Draft"} />
              <Row label="Balanced" value={balanced ? "Yes" : "No"} />
              {journal.project_id && (
                <div className="border-t pt-2">
                  <Link
                    to="/projects/$projectId"
                    params={{ projectId: journal.project_id }}
                    className="text-sm hover:underline"
                  >
                    Open the project
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>

          {posted && (
            <Card>
              <CardContent className="py-4 text-xs text-muted-foreground">
                A posted journal is not edited. Correcting it means another journal that
                reverses it, so the history of what was believed and when survives.
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
      <span className="truncate text-right font-medium capitalize">{value}</span>
    </div>
  );
}
