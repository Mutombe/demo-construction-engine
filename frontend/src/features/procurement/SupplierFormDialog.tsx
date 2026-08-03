import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCreateSupplier, useUpdateSupplier } from "@/lib/api/generated/endpoints";
import type { SupplierRead } from "@/lib/api/generated/model";
import { addRow, optimistic, patchRow, tempId } from "@/lib/api/optimistic";

const schema = z.object({
  name: z.string().min(1, "Required"),
  contact_name: z.string().optional(),
  email: z.string().optional(),
  phone: z.string().optional(),
  address: z.string().optional(),
  tax_id: z.string().optional(),
  categories: z.string().optional(),
  notes: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

export function SupplierFormDialog({
  open,
  onOpenChange,
  supplier,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  supplier?: SupplierRead | null;
}) {
  const queryClient = useQueryClient();
  const createMutation = useCreateSupplier({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/suppliers"],
      successToast: "Supplier created",
      apply: (old, vars: { data: Record<string, unknown> }) =>
        addRow(() => ({
          id: tempId(),
          is_active: true,
          created_at: new Date().toISOString(),
          ...vars.data,
        }))(old),
    }),
  });
  const updateMutation = useUpdateSupplier({
    mutation: optimistic(queryClient, {
      prefixes: ["/api/v1/suppliers"],
      successToast: "Supplier updated",
      apply: (old, vars: { supplierId: string; data: Record<string, unknown> }) =>
        patchRow(vars.supplierId, vars.data)(old),
    }),
  });
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (open) {
      reset({
        name: supplier?.name ?? "",
        contact_name: supplier?.contact_name ?? "",
        email: supplier?.email ?? "",
        phone: supplier?.phone ?? "",
        address: supplier?.address ?? "",
        tax_id: supplier?.tax_id ?? "",
        categories: supplier?.categories ?? "",
        notes: supplier?.notes ?? "",
      });
    }
  }, [open, supplier, reset]);

  const onSubmit = (values: FormValues) => {
    const payload = {
      name: values.name,
      contact_name: values.contact_name || null,
      email: values.email || null,
      phone: values.phone || null,
      address: values.address || null,
      tax_id: values.tax_id || null,
      categories: values.categories || null,
      notes: values.notes || null,
    };
    // Optimistic: close now; the row appears/patches instantly and rolls back
    // with an error toast if the server rejects (e.g. duplicate name).
    onOpenChange(false);
    const action = supplier
      ? updateMutation.mutateAsync({ supplierId: supplier.id, data: payload })
      : createMutation.mutateAsync({ data: payload });
    void action.catch(() => undefined);
  };

  const busy = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{supplier ? `Edit ${supplier.name}` : "New Supplier"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="s-name">Company Name</Label>
            <Input id="s-name" {...register("name")} />
            {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="s-contact">Contact Person</Label>
              <Input id="s-contact" {...register("contact_name")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="s-phone">Phone</Label>
              <Input id="s-phone" {...register("phone")} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="s-email">Email</Label>
              <Input id="s-email" type="email" {...register("email")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="s-tax">Tax ID</Label>
              <Input id="s-tax" {...register("tax_id")} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="s-cats">Categories (Comma-Separated)</Label>
            <Input id="s-cats" placeholder="cement, steel, plumbing" {...register("categories")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="s-address">Address</Label>
            <Textarea id="s-address" rows={2} {...register("address")} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : supplier ? "Save Changes" : "Create Supplier"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
