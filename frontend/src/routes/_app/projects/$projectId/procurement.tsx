import { createFileRoute } from "@tanstack/react-router";
import { Plus } from "@phosphor-icons/react";
import { useState } from "react";
import { Can } from "@/components/layout/Can";
import { Button } from "@/components/ui/button";
import { PoList, RfqList } from "@/features/procurement/ProcurementLists";
import { RfqWizard } from "@/features/procurement/RfqWizard";

export const Route = createFileRoute("/_app/projects/$projectId/procurement")({
  component: ProjectProcurementTab,
});

function ProjectProcurementTab() {
  const { projectId } = Route.useParams();
  const [wizardOpen, setWizardOpen] = useState(false);

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Can perm="procurement:write">
          <Button onClick={() => setWizardOpen(true)}>
            <Plus /> New RFQ from BOQ
          </Button>
        </Can>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <RfqList projectId={projectId} />
        <PoList projectId={projectId} />
      </div>
      <RfqWizard open={wizardOpen} onOpenChange={setWizardOpen} projectId={projectId} />
    </div>
  );
}
