import { Barcode, Keyboard } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

type DetectedBarcode = { rawValue: string };
type BarcodeDetectorLike = {
  detect: (source: CanvasImageSource) => Promise<DetectedBarcode[]>;
};
type BarcodeDetectorCtor = new (options?: { formats?: string[] }) => BarcodeDetectorLike;

const SCAN_FORMATS = [
  "ean_13",
  "ean_8",
  "upc_a",
  "upc_e",
  "code_128",
  "code_39",
  "itf",
  "qr_code",
];

function getDetector(): BarcodeDetectorLike | null {
  const ctor = (globalThis as { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector;
  if (!ctor) return null;
  try {
    return new ctor({ formats: SCAN_FORMATS });
  } catch {
    try {
      return new ctor();
    } catch {
      return null;
    }
  }
}

/** Camera barcode scanner built on the native BarcodeDetector API, with a
 *  manual-entry field for browsers (or wired USB scanners, which type into
 *  the focused input) that can't use live detection. */
export function BarcodeScannerDialog({
  open,
  onOpenChange,
  onDetected,
  title = "Scan Barcode",
  hint,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDetected: (code: string) => void;
  title?: string;
  hint?: string;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [manual, setManual] = useState("");
  const [cameraError, setCameraError] = useState<string | null>(null);
  const detectorSupported = !!getDetector();

  useEffect(() => {
    if (!open) {
      setManual("");
      setCameraError(null);
      return;
    }
    if (!detectorSupported) {
      setCameraError("Live scanning is not supported in this browser — enter the code below");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("No camera access — enter the code below");
      return;
    }

    let stream: MediaStream | null = null;
    let raf = 0;
    let stopped = false;
    const detector = getDetector();
    let lastAttempt = 0;

    const tick = async (now: number) => {
      if (stopped) return;
      // ~5 detects per second is plenty and keeps the main thread light
      if (detector && videoRef.current && videoRef.current.videoWidth > 0 && now - lastAttempt > 200) {
        lastAttempt = now;
        try {
          const codes = await detector.detect(videoRef.current);
          const value = codes.find((c) => c.rawValue)?.rawValue;
          if (value && !stopped) {
            stopped = true;
            onDetected(value);
            return;
          }
        } catch {
          // detect() can throw while the stream warms up — keep trying
        }
      }
      raf = requestAnimationFrame((t) => void tick(t));
    };

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((s) => {
        if (stopped) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        stream = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
          void videoRef.current.play().catch(() => undefined);
        }
        raf = requestAnimationFrame((t) => void tick(t));
      })
      .catch(() => setCameraError("Camera unavailable — enter the code below"));

    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [open, detectorSupported, onDetected]);

  const submitManual = () => {
    const code = manual.trim();
    if (code) onDetected(code);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        {!cameraError ? (
          <div className="relative overflow-hidden rounded-md border bg-black">
            <video ref={videoRef} playsInline muted className="h-56 w-full object-cover" />
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <div className="h-24 w-3/4 rounded-lg border-2 border-white/70 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
            </div>
            <div className="absolute inset-x-0 bottom-2 text-center text-xs text-white/80">
              Point the camera at the barcode
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
            <Barcode className="size-4 shrink-0" />
            {cameraError}
          </div>
        )}

        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Keyboard className="size-3.5" />
            Type or scan with a handheld scanner
          </div>
          <div className="flex gap-2">
            <Input
              autoFocus={!!cameraError}
              value={manual}
              onChange={(e) => setManual(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitManual();
              }}
              placeholder="e.g. 6001234567890"
              className="font-mono"
            />
            <Button disabled={!manual.trim()} onClick={submitManual}>
              Find
            </Button>
          </div>
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
