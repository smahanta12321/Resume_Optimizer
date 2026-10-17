import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form-controls";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  loading?: boolean;
  destructive?: boolean;
  /** If set, the user must type this exact text before confirming. */
  typeToConfirm?: string;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  children,
  confirmLabel,
  onConfirm,
  loading,
  destructive,
  typeToConfirm,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState("");
  const blocked = typeToConfirm !== undefined && typed !== typeToConfirm;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setTyped("");
        onOpenChange(next);
      }}
    >
      <DialogContent
        title={title}
        footer={
          <>
            <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>
              Cancel
            </Button>
            <Button variant={destructive ? "danger" : "primary"} onClick={onConfirm} loading={loading} disabled={blocked}>
              {confirmLabel}
            </Button>
          </>
        }
      >
        <div className="space-y-4 text-sm">
          {children}
          {typeToConfirm !== undefined && (
            <Field label={<>Type <strong>{typeToConfirm}</strong> to confirm</>}>
              {(p) => <Input {...p} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />}
            </Field>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
