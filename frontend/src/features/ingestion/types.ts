import type { IngestionItemRead } from "@/lib/api/generated/model";

/** Shape of the JSONB proposed_action the pipeline writes (see backend ingestion/service.py). */
export interface ProposedAction {
  action: string | null;
  params: Record<string, unknown>;
  display: Record<string, unknown>;
  field_confidence: Record<string, number>;
  missing_fields: string[];
  problems: string[];
  confidence_score: number;
  gate_passed: boolean;
  corrections: Record<string, unknown>;
  lineage: {
    posted_type?: string;
    posted_id?: string;
    reference?: string;
    approved_at?: string;
  } | null;
}

export function actionOf(item: IngestionItemRead): ProposedAction | null {
  return (item.proposed_action as ProposedAction | null) ?? null;
}

const SECTION_BY_TYPE: Record<string, string> = {
  supplier_invoice: "invoice",
  expense_receipt: "receipt",
  delivery_note: "delivery_note",
  supplier_quote: "quote",
};

/** Raw extracted value for a field, with any human correction applied on top. */
export function fieldValue(item: IngestionItemRead, field: string): string {
  const action = actionOf(item);
  const corrected = action?.corrections?.[field];
  if (corrected !== undefined && corrected !== null) return String(corrected);
  const section = item.doc_type ? SECTION_BY_TYPE[item.doc_type] : undefined;
  const extraction = item.extraction as Record<string, Record<string, { value?: unknown }>> | null;
  const value = section ? extraction?.[section]?.[field]?.value : undefined;
  return value === undefined || value === null ? "" : String(value);
}

export const DOC_TYPE_LABELS: Record<string, string> = {
  supplier_invoice: "Supplier invoice",
  expense_receipt: "Expense receipt",
  delivery_note: "Delivery note",
  supplier_quote: "Supplier quote",
};

export const ACTION_LABELS: Record<string, string> = {
  create_cost_entry: "Post cost entry (source: invoice)",
  create_expense_claim: "File pending expense claim",
  receive_po: "Receive purchase order",
  create_quote: "Record supplier quote",
};

export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
export const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
