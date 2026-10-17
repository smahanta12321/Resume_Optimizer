/**
 * The one HTTP client for the local API. Every call goes through `request`, which adds the
 * session token, normalizes errors into `ApiError`, and never turns a failure into fake data.
 */
import { getToken } from "@/lib/session";

export const TOKEN_HEADER = "X-Resume-Optimizer-Session";
export const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
export const API_BASE = `${API_ORIGIN}/api/v1`;

export interface FieldError {
  loc: string[];
  msg: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field-level errors from validation failures, if the API sent any. */
  get fieldErrors(): FieldError[] {
    return Array.isArray(this.details) ? (this.details as FieldError[]) : [];
  }
}

export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code);
}

/** A user-facing message for any error. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

type Query = Record<string, string | number | boolean | string[] | null | undefined>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: unknown;
  /** Raw body (file uploads). Sent as application/octet-stream unless contentType is given. */
  raw?: Blob | ArrayBuffer | string;
  contentType?: string;
  query?: Query;
  signal?: AbortSignal;
}

export function buildUrl(path: string, query?: Query): string {
  const url = new URL(API_BASE + path);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    for (const v of Array.isArray(value) ? value : [value]) url.searchParams.append(key, String(v));
  }
  return url.toString();
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers[TOKEN_HEADER] = token;
  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.raw !== undefined) {
    headers["Content-Type"] = options.contentType ?? "application/octet-stream";
    body = options.raw;
  }
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body,
      signal: options.signal,
      credentials: "omit",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(
      0,
      "network_error",
      `Can't reach the local app at ${API_ORIGIN}. Start it with \`python -m src.api\` and try again.`,
    );
  }
  if (!response.ok) throw await toApiError(response);
  return response;
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const data: unknown = await response.json();
    const err = (data as { error?: { code?: unknown; message?: unknown; details?: unknown } }).error;
    if (err && typeof err.code === "string" && typeof err.message === "string") {
      return new ApiError(response.status, err.code, err.message, err.details);
    }
  } catch {
    // Not our error shape (e.g. a proxy page): fall through to a generic message.
  }
  return new ApiError(response.status, `http_${response.status}`, `The local app answered with HTTP ${response.status}.`);
}

/** JSON request. Resolves to `undefined` for 204 responses. */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function filenameFrom(response: Response, fallback: string): string {
  const header = response.headers.get("Content-Disposition") ?? "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) return decodeURIComponent(star[1]);
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1] ?? fallback;
}

/** Fetches a file (with the session header) and hands it to the browser as a download. */
export async function download(path: string, fallbackName: string, query?: Query): Promise<string> {
  const response = await send(path, { query });
  const blob = await response.blob();
  const name = filenameFrom(response, fallbackName);
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return name;
}
