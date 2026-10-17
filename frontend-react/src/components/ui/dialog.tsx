import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

interface ContentProps {
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
  /** "dialog" centres the panel; "sheet" slides it in from the side (mobile navigation, long editors). */
  variant?: "dialog" | "sheet-left" | "sheet-right";
  hideTitle?: boolean;
}

export function DialogContent({ title, description, children, footer, className, variant = "dialog", hideTitle }: ContentProps) {
  const position =
    variant === "dialog"
      ? "left-1/2 top-1/2 max-h-[90dvh] w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg"
      : variant === "sheet-left"
        ? "inset-y-0 left-0 h-dvh w-72 max-w-[85vw] border-r"
        : "inset-y-0 right-0 h-dvh w-[42rem] max-w-full border-l";
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/40 animate-in" />
      <DialogPrimitive.Content
        className={cn("fixed z-50 flex flex-col border bg-surface shadow-xl animate-in focus:outline-none", position, className)}
      >
        <div className={cn("flex items-start justify-between gap-4 border-b px-5 py-3.5", hideTitle && "sr-only")}>
          <div>
            <DialogPrimitive.Title className="text-base font-semibold">{title}</DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="mt-0.5 text-sm text-muted-foreground">{description}</DialogPrimitive.Description>
            ) : (
              <DialogPrimitive.Description className="sr-only">{typeof title === "string" ? title : "Dialog"}</DialogPrimitive.Description>
            )}
          </div>
          <DialogPrimitive.Close className="-mr-1 rounded-md p-1 text-muted-foreground hover:bg-surface-muted hover:text-foreground" aria-label="Close">
            <X className="size-4" />
          </DialogPrimitive.Close>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t px-5 py-3">{footer}</div>}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
