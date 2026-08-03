import { createFileRoute } from "@tanstack/react-router";
import { MediaPanel } from "@/features/media/MediaPanel";

export const Route = createFileRoute("/_app/projects/$projectId/documents")({
  component: DocumentsTab,
});

function DocumentsTab() {
  const { projectId } = Route.useParams();
  return <MediaPanel entityType="project" entityId={projectId} />;
}
