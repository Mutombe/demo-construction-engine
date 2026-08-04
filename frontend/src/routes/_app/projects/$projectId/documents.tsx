import { createFileRoute } from "@tanstack/react-router";
import { Files, ImagesSquare } from "@phosphor-icons/react";
import { useState } from "react";
import { MediaPanel } from "@/features/media/MediaPanel";
import { PhotoTimeline } from "@/features/media/PhotoTimeline";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/projects/$projectId/documents")({
  component: DocumentsTab,
});

const VIEWS = [
  { key: "files", label: "Files", icon: <Files /> },
  { key: "timeline", label: "Photo Timeline", icon: <ImagesSquare /> },
] as const;

function DocumentsTab() {
  const { projectId } = Route.useParams();
  const [view, setView] = useState<"files" | "timeline">("files");

  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-md border p-1 sm:w-fit">
        {VIEWS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setView(item.key)}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors sm:flex-none",
              view === item.key
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </div>

      {view === "files" ? (
        <MediaPanel entityType="project" entityId={projectId} />
      ) : (
        <PhotoTimeline entityType="project" entityId={projectId} />
      )}
    </div>
  );
}
