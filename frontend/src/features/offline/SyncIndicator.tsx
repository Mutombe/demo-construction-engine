import { Link } from "@tanstack/react-router";
import { CloudSlash, UploadSimple } from "@phosphor-icons/react";
import { useOutbox } from "@/lib/offline/useOutbox";
import { cn } from "@/lib/utils";

/** Silent when there is nothing to say.
 *
 *  It appears only when the connection is gone or something is still sitting
 *  on the device, because a permanent "online" badge trains people to stop
 *  reading it, and then the one time it matters they miss it too. */
export function SyncIndicator() {
  const { online, waiting, rejected } = useOutbox();
  const stuck = waiting.length + rejected.length;

  if (online && stuck === 0) return null;

  return (
    <Link
      to="/field"
      title={online ? "Captures still on this device" : "No connection — work is being saved here"}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium",
        rejected.length
          ? "border-destructive/40 text-destructive"
          : online
            ? "border-input text-muted-foreground hover:bg-accent"
            : "border-warning/40 text-warning",
      )}
    >
      {online ? <UploadSimple className="size-4" /> : <CloudSlash className="size-4" />}
      {stuck > 0 ? stuck : "Offline"}
    </Link>
  );
}
