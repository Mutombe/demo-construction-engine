import {
  ArrowRight,
  ArrowsInSimple,
  ArrowsOutSimple,
  Compass,
  MagnifyingGlass,
  MapPin,
  X,
} from "@phosphor-icons/react";
import { createFileRoute, Link } from "@tanstack/react-router";
import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import iconRetina from "leaflet/dist/images/marker-icon-2x.png";
import iconUrl from "leaflet/dist/images/marker-icon.png";
import shadow from "leaflet/dist/images/marker-shadow.png";
import { PageHeader } from "@/components/layout/AppShell";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ProjectStatusBadge } from "@/features/projects/StatusBadge";
import {
  getGetProjectMapPinsQueryOptions,
  useGetProjectMapPins,
} from "@/lib/api/generated/endpoints";
import type { ProjectMapPin } from "@/lib/api/generated/model";
import { money } from "@/lib/format";
import { cn } from "@/lib/utils";

// Vite fix for Leaflet's missing default marker icon paths
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({ iconRetinaUrl: iconRetina, iconUrl, shadowUrl: shadow });

export const Route = createFileRoute("/_app/map")({
  component: SiteMapPage,
  loader: ({ context: { queryClient } }) =>
    queryClient.ensureQueryData(getGetProjectMapPinsQueryOptions()),
});

const HARARE: [number, number] = [-17.8252, 31.0335];

const STATUS_HEX: Record<string, string> = {
  planning: "#6C757D",
  active: "#2A4B8D",
  on_hold: "#9333EA",
  completed: "#15803D",
  cancelled: "#DC2626",
};

const FILTERS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "planning", label: "Planning" },
  { key: "on_hold", label: "On Hold" },
  { key: "completed", label: "Completed" },
] as const;

/** Status-coloured progress ring with the percentage inside — reads at a glance. */
function buildMarkerIcon(status: string, progress = 0) {
  const color = STATUS_HEX[status] ?? "#2A4B8D";
  const safe = Math.max(0, Math.min(100, Math.round(progress)));
  const size = 42;
  const cx = size / 2;
  const r = 16;
  const c = 2 * Math.PI * r;
  const offset = c - (safe / 100) * c;
  const fontSize = safe >= 100 ? 10 : 11;
  const html = `
    <div style="position:relative;width:${size}px;height:${size}px;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.2));">
      <svg width="${size}" height="${size}" style="position:absolute;inset:0;transform:rotate(-90deg);">
        <circle cx="${cx}" cy="${cx}" r="${r}" fill="white" stroke="rgba(17,17,17,0.1)" stroke-width="3"/>
        <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${color}" stroke-width="3"
          stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${offset}"/>
      </svg>
      <span class="marker-pct" style="font-family:system-ui,sans-serif;font-size:${fontSize}px;color:${color};">${safe}%</span>
    </div>`;
  return L.divIcon({
    className: "erp-map-marker",
    html,
    iconSize: [size, size],
    iconAnchor: [cx, cx],
    popupAnchor: [0, -(cx - 4)],
  });
}

/** Fly to the selected pin; nudge Leaflet after fullscreen resizes. */
function MapController({
  selected,
  fullscreen,
}: {
  selected: ProjectMapPin | null;
  fullscreen: boolean;
}) {
  const map = useMap();
  useEffect(() => {
    if (selected) {
      map.flyTo([Number(selected.latitude), Number(selected.longitude)], 14, {
        duration: 1.2,
      });
    }
  }, [selected, map]);
  useEffect(() => {
    const id = setTimeout(() => map.invalidateSize(), 220);
    return () => clearTimeout(id);
  }, [fullscreen, map]);
  return null;
}

function SiteMapPage() {
  const { data: pins, isLoading } = useGetProjectMapPins();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("all");
  const [selected, setSelected] = useState<ProjectMapPin | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

  // ESC exits fullscreen; lock body scroll while expanded
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [fullscreen]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (pins ?? []).filter((p) => {
      if (filter !== "all" && p.status !== filter) return false;
      if (q) {
        const hay = `${p.name} ${p.code} ${p.client_name ?? ""} ${p.city ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [pins, search, filter]);

  return (
    <div>
      <PageHeader
        title="Site Map"
        description="Every pinned project — colour is status, the ring is live progress"
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Sidebar */}
        <aside className="flex flex-col gap-3 lg:col-span-4">
          <div className="relative">
            <MagnifyingGlass
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, code, client, city…"
              className="pl-8"
            />
          </div>

          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                  filter === f.key
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-card text-muted-foreground hover:border-primary hover:text-primary",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="overflow-hidden rounded-lg border bg-card">
            {isLoading && !pins ? (
              <ul className="divide-y">
                {Array.from({ length: 3 }, (_, i) => (
                  <li key={i} className="space-y-2 px-4 py-3">
                    <Skeleton className="h-3 w-24" />
                    <Skeleton className="h-3 w-2/3" />
                    <Skeleton className="h-1.5 w-full" />
                  </li>
                ))}
              </ul>
            ) : filtered.length === 0 ? (
              <div className="p-8 text-center">
                <MapPin size={28} className="mx-auto text-muted-foreground" />
                <p className="mt-3 text-sm font-medium">
                  {(pins?.length ?? 0) === 0 ? "No projects pinned yet" : "Nothing matches"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {(pins?.length ?? 0) === 0
                    ? "Add latitude/longitude on a project to drop a pin here."
                    : "Try a different search term or status filter."}
                </p>
              </div>
            ) : (
              <ul className="max-h-[560px] divide-y overflow-y-auto">
                {filtered.map((p) => {
                  const isSel = selected?.id === p.id;
                  const dot = STATUS_HEX[p.status] ?? "#2A4B8D";
                  return (
                    <li
                      key={p.id}
                      onClick={() => setSelected(p)}
                      className={cn(
                        "cursor-pointer px-4 py-3 transition-colors",
                        isSel ? "bg-primary/5" : "hover:bg-muted/60",
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <span
                          className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{ background: dot, boxShadow: `0 0 0 3px ${dot}1F` }}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                              {p.code}
                            </p>
                            <Link
                              to="/projects/$projectId"
                              params={{ projectId: p.id }}
                              preload="intent"
                              className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                              onClick={(e) => e.stopPropagation()}
                            >
                              View <ArrowRight size={10} />
                            </Link>
                          </div>
                          <p className="mt-0.5 truncate text-sm font-medium">{p.name}</p>
                          <p className="truncate text-xs text-muted-foreground">
                            {p.client_name ?? "—"}
                            {p.city && <> · {p.city}</>}
                          </p>
                          <div className="mt-2 flex items-center gap-2">
                            <div className="h-1 flex-1 overflow-hidden rounded-full bg-secondary">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${Math.max(0, Math.min(100, p.progress_pct ?? 0))}%`,
                                  background: dot,
                                }}
                              />
                            </div>
                            <span className="w-9 text-right text-[10px] tabular-nums text-muted-foreground">
                              {Math.round(p.progress_pct ?? 0)}%
                            </span>
                          </div>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
            <Compass size={12} /> {filtered.length} of {pins?.length ?? 0} pinned
          </p>
        </aside>

        {/* Map */}
        <section className={fullscreen ? "lg:col-span-12" : "lg:col-span-8"}>
          <div
            className={
              fullscreen
                ? "fixed inset-0 z-[1000] bg-card"
                : "sticky top-20 overflow-hidden rounded-lg border bg-card shadow-sm"
            }
            style={
              fullscreen
                ? { width: "100vw", height: "100vh" }
                : { height: "calc(100vh - 11rem)", minHeight: 420 }
            }
          >
            <button
              type="button"
              onClick={() => setFullscreen((v) => !v)}
              className="absolute right-3 top-3 z-[1100] flex items-center gap-2 rounded-full border bg-card/95 px-3 py-2 text-xs font-medium shadow-md backdrop-blur-sm transition-colors hover:border-primary hover:text-primary"
              title={fullscreen ? "Exit fullscreen (Esc)" : "Expand to fullscreen"}
            >
              {fullscreen ? (
                <ArrowsInSimple size={14} weight="bold" />
              ) : (
                <ArrowsOutSimple size={14} weight="bold" />
              )}
              <span className="hidden sm:inline">
                {fullscreen ? "Exit fullscreen" : "Fullscreen"}
              </span>
            </button>
            {fullscreen && (
              <button
                type="button"
                onClick={() => setFullscreen(false)}
                className="absolute left-3 top-3 z-[1100] flex items-center gap-2 rounded-full border bg-card/95 px-3 py-2 text-xs font-medium shadow-md backdrop-blur-sm transition-colors hover:border-destructive hover:text-destructive"
                aria-label="Close fullscreen"
              >
                <X size={14} weight="bold" />
                <span className="hidden sm:inline">Close</span>
              </button>
            )}
            <MapContainer
              center={HARARE}
              zoom={7}
              scrollWheelZoom
              style={{ width: "100%", height: "100%" }}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <MapController selected={selected} fullscreen={fullscreen} />
              {filtered.map((p) => (
                <Marker
                  key={p.id}
                  position={[Number(p.latitude), Number(p.longitude)]}
                  icon={buildMarkerIcon(p.status, p.progress_pct)}
                  eventHandlers={{ click: () => setSelected(p) }}
                >
                  <Popup>
                    <div style={{ minWidth: 200 }}>
                      <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                        {p.code}
                      </p>
                      <p className="mt-0.5 text-sm font-semibold">{p.name}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {p.client_name}
                        {p.contract_value && <> · {money(p.contract_value)}</>}
                      </p>
                      <div className="mt-2">
                        <ProjectStatusBadge status={p.status} />
                      </div>
                      <div className="mt-2">
                        <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
                          <span>Progress</span>
                          <span>{Math.round(p.progress_pct ?? 0)}%</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${Math.max(0, Math.min(100, p.progress_pct ?? 0))}%`,
                              background: STATUS_HEX[p.status] ?? "#2A4B8D",
                            }}
                          />
                        </div>
                      </div>
                      <Link
                        to="/projects/$projectId"
                        params={{ projectId: p.id }}
                        preload="intent"
                        className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                      >
                        Open project <ArrowRight size={11} />
                      </Link>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          </div>
        </section>
      </div>
    </div>
  );
}
