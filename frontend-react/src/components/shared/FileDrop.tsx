import { Upload } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";
import { cn } from "@/lib/utils";

export interface FileRules {
  /** Lower-case extensions including the dot, e.g. [".pdf", ".docx"]. */
  extensions: string[];
  maxBytes: number;
}

/** Client-side pre-check only, for fast feedback. The API validates every upload again. */
export function checkFile(file: File, rules: FileRules): string | null {
  const name = file.name.toLowerCase();
  if (!rules.extensions.some((ext) => name.endsWith(ext))) {
    return `Unsupported file type. Use ${rules.extensions.join(", ")}.`;
  }
  if (file.size === 0) return "The file is empty.";
  if (file.size > rules.maxBytes) {
    return `The file is too large (${(file.size / 1_000_000).toFixed(1)} MB). The limit is ${rules.maxBytes / 1_000_000} MB.`;
  }
  return null;
}

export function FileDrop({
  rules,
  onFile,
  label,
  hint,
  disabled,
}: {
  rules: FileRules;
  onFile: (file: File) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const accept = (file: File | undefined) => {
    if (!file) return;
    const problem = checkFile(file, rules);
    setError(problem);
    if (!problem) onFile(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (!disabled) accept(e.dataTransfer.files[0]);
  };

  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
          dragging ? "border-primary bg-primary-soft/50" : "hover:bg-surface-muted/60",
          disabled && "pointer-events-none opacity-60",
        )}
      >
        <Upload className="size-5 text-muted-foreground" aria-hidden />
        <span className="text-sm font-medium">{label}</span>
        <span className="text-xs text-muted-foreground">
          Drag and drop, or click to browse. {hint ?? `${rules.extensions.join(", ")} up to ${rules.maxBytes / 1_000_000} MB.`}
        </span>
      </label>
      <input
        ref={input}
        id={id}
        type="file"
        className="sr-only"
        accept={rules.extensions.join(",")}
        disabled={disabled}
        onChange={(e) => {
          accept(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {error && (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
