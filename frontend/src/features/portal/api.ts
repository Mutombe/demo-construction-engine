/** Hand-written client for the public portal surface.
 *  Deliberately not orval/axios: portal visitors are clients with an opaque
 *  link token, not staff users with JWTs. */

export interface PortalProject {
  id: string;
  code: string;
  name: string;
  status: string;
  city: string | null;
  planned_start: string | null;
  planned_end: string | null;
  contract_value: string | null;
  progress_pct: number;
}

export interface PortalSummary {
  client_name: string;
  company_name: string;
  projects: PortalProject[];
}

export interface PortalPhase {
  name: string;
  sequence: number;
  status: string;
  planned_start: string | null;
  planned_end: string | null;
}

export interface PortalProjectDetail extends PortalProject {
  description: string | null;
  site_address: string | null;
  actual_start: string | null;
  phases: PortalPhase[];
}

export interface PortalValuation {
  id: string;
  doc_number: string;
  valuation_number: number;
  status: "issued" | "paid";
  period_end: string;
  gross_valuation: string;
  retention_amount: string;
  net_certified: string;
  issued_date: string | null;
  paid_date: string | null;
}

export class PortalError extends Error {
  constructor(
    public status: number,
    detail: string,
  ) {
    super(detail);
  }
}

async function portalFetch<T>(token: string, path: string): Promise<T> {
  const res = await fetch(`/api/v1/portal${path}`, {
    headers: { "X-Portal-Token": token },
  });
  if (!res.ok) {
    let detail = "Something went wrong";
    try {
      detail = (await res.json())?.error?.detail ?? detail;
    } catch {
      // non-JSON error body
    }
    throw new PortalError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const fetchSummary = (token: string) => portalFetch<PortalSummary>(token, "/summary");

export const fetchProject = (token: string, projectId: string) =>
  portalFetch<PortalProjectDetail>(token, `/projects/${projectId}`);

export const fetchValuations = (token: string, projectId: string) =>
  portalFetch<PortalValuation[]>(token, `/projects/${projectId}/valuations`);

export async function downloadCertificate(token: string, valuation: PortalValuation) {
  const res = await fetch(`/api/v1/portal/valuations/${valuation.id}/certificate`, {
    headers: { "X-Portal-Token": token },
  });
  if (!res.ok) throw new PortalError(res.status, "Download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${valuation.doc_number}_certificate.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
