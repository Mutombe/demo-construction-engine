import { ArrowCounterClockwise, Camera, CameraRotate, Check } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "@/lib/toast";

/** Live camera preview -> capture to JPEG -> hand the file to the caller.
 *  Uses the rear camera when available (site phones); front/rear can be
 *  toggled. Falls back to a clear error state when getUserMedia is denied. */
export function CameraCaptureDialog({
  open,
  onOpenChange,
  onCapture,
  uploading,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCapture: (file: File, caption: string | null) => Promise<void>;
  uploading: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [facing, setFacing] = useState<"environment" | "user">("environment");
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<{ blob: Blob; url: string } | null>(null);
  const [caption, setCaption] = useState("");

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    if (!open || snapshot) return;
    let cancelled = false;
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser does not support camera access");
      return;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: facing }, audio: false })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          void videoRef.current.play().catch(() => undefined);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Camera unavailable — check browser permissions and try again");
        }
      });
    return () => {
      cancelled = true;
      stopStream();
    };
  }, [open, facing, snapshot, stopStream]);

  useEffect(() => {
    if (!open) {
      stopStream();
      if (snapshot) URL.revokeObjectURL(snapshot.url);
      setSnapshot(null);
      setCaption("");
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const takePhoto = () => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          toast.error("Could not capture the frame");
          return;
        }
        stopStream();
        setSnapshot({ blob, url: URL.createObjectURL(blob) });
      },
      "image/jpeg",
      0.9,
    );
  };

  const confirm = async () => {
    if (!snapshot) return;
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const file = new File([snapshot.blob], `photo-${stamp}.jpg`, { type: "image/jpeg" });
    await onCapture(file, caption.trim() || null);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Take Photo</DialogTitle>
        </DialogHeader>

        <div className="relative overflow-hidden rounded-md border bg-black">
          {snapshot ? (
            <img src={snapshot.url} alt="captured" className="max-h-[55vh] w-full object-contain" />
          ) : error ? (
            <div className="flex h-56 items-center justify-center px-8 text-center text-sm text-white/80">
              {error}
            </div>
          ) : (
            <video
              ref={videoRef}
              playsInline
              muted
              className="max-h-[55vh] w-full object-contain"
            />
          )}
          {!snapshot && !error && (
            <Button
              variant="outline"
              size="icon"
              title="Switch camera"
              className="absolute right-2 top-2 bg-black/40 text-white hover:bg-black/60"
              onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))}
            >
              <CameraRotate />
            </Button>
          )}
        </div>

        {snapshot && (
          <Input
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            placeholder="Caption (optional) — e.g. First floor slab poured"
            maxLength={255}
          />
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          {snapshot ? (
            <>
              <Button
                variant="outline"
                disabled={uploading}
                onClick={() => {
                  URL.revokeObjectURL(snapshot.url);
                  setSnapshot(null);
                  setCaption("");
                }}
              >
                <ArrowCounterClockwise /> Retake
              </Button>
              <Button disabled={uploading} onClick={() => void confirm()}>
                <Check /> {uploading ? "Uploading…" : "Use Photo"}
              </Button>
            </>
          ) : (
            <Button disabled={!!error} onClick={takePhoto}>
              <Camera /> Capture
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
