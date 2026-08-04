import { createFileRoute } from "@tanstack/react-router";
import { AssistantChat } from "@/features/ai/AssistantChat";

export const Route = createFileRoute("/_app/assistant")({
  component: AssistantPage,
});

function AssistantPage() {
  // Fills the main area so long conversations get the whole screen rather
  // than a 420px column.
  return (
    <div className="h-[calc(100vh-7.5rem)]">
      <AssistantChat />
    </div>
  );
}
