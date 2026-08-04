import { zodResolver } from "@hookform/resolvers/zod";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { HardHat } from "@phosphor-icons/react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { login } from "@/features/auth/api";
import { errDetail } from "@/lib/api/errors";
import { acceptInvite } from "@/lib/api/generated/endpoints";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/accept-invite/$token")({
  component: AcceptInvitePage,
});

const formSchema = z
  .object({
    password: z.string().min(8, "At least 8 characters"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: "The two passwords do not match",
    path: ["confirm"],
  });
type FormValues = z.infer<typeof formSchema>;

function AcceptInvitePage() {
  const { token } = Route.useParams();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(formSchema) });

  const onSubmit = async (values: FormValues) => {
    setSubmitting(true);
    try {
      const user = await acceptInvite({ token, password: values.password });
      // Straight in, rather than bouncing them to a login form for the
      // password they typed ten seconds ago.
      await login(user.email, values.password);
      toast.success(`Welcome, ${user.full_name}`);
      await navigate({ to: "/" });
    } catch (err) {
      toast.error(errDetail(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-secondary/60 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center pb-2 pt-6 text-center">
          <div className="mb-1 flex h-11 w-11 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <HardHat className="h-6 w-6" />
          </div>
          <CardTitle className="text-lg">Set your password</CardTitle>
          <p className="text-sm text-muted-foreground">
            Choose a password and your account is ready
          </p>
        </CardHeader>
        <CardContent className="pt-4">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                {...register("password")}
              />
              {errors.password && (
                <p className="text-xs text-destructive">{errors.password.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="confirm">Confirm password</Label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                {...register("confirm")}
              />
              {errors.confirm && (
                <p className="text-xs text-destructive">{errors.confirm.message}</p>
              )}
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Setting up…" : "Create My Account"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
