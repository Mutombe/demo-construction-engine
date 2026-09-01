import { Camera, Trash } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { enqueuePhoto } from "@/lib/offline/outbox";
import { toast } from "@/lib/toast";

/** Photographs taken on site, queued like everything else.
 *
 *  They go into their own queue rather than the JSON backlog: a photo is
 *  megabytes and a diary entry is bytes, and one large picture on a bad
 *  connection should never hold up a day of typed records behind it.
 *
 *  The camera is opened directly by the file input's `capture` attribute
 *  rather than through any media API, which means it works with no
 *  permissions prompt, no signal, and on every phone the site actually owns.
 */
export function PhotoForm({ projectId }: { projectId: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [chosen, setChosen] = useState<File[]>([]);
  const [caption, setCaption] = useState("");
  const [previews, setPreviews] = useState<string[]>([]);

  useEffect(() => {
    const urls = chosen.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    // Object URLs hold the whole image in memory until they are revoked, and
    // a foreman photographing all day would otherwise never give it back.
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [chosen]);

  const save = async () => {
    for (const file of chosen) {
      await enqueuePhoto("project", projectId, file, caption);
    }
    toast.success(
      chosen.length === 1 ? "Photo saved on this device" : `${chosen.length} photos saved`,
    );
    setChosen([]);
    setCaption("");
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Camera /> Photographs
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          className="hidden"
          onChange={(e) => setChosen(Array.from(e.target.files ?? []))}
        />

        <Button
          variant="outline"
          className="w-full"
          onClick={() => inputRef.current?.click()}
        >
          <Camera /> Take Photos
        </Button>

        {previews.length > 0 && (
          <>
            <div className="grid grid-cols-3 gap-2">
              {previews.map((url, index) => (
                <div key={url} className="relative">
                  <img
                    src={url}
                    alt=""
                    className="h-24 w-full rounded-md border object-cover"
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Remove photo"
                    className="absolute right-0.5 top-0.5 h-6 w-6 bg-background/80"
                    onClick={() => setChosen((files) => files.filter((_, i) => i !== index))}
                  >
                    <Trash className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="photo-caption">What this shows</Label>
              <Input
                id="photo-caption"
                placeholder="Rebar fixed to raft, grid A-C"
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Worth typing now. A month later nobody can tell one pour from another.
              </p>
            </div>

            <Button className="w-full" onClick={() => void save()}>
              Save {chosen.length === 1 ? "Photo" : `${chosen.length} Photos`}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
