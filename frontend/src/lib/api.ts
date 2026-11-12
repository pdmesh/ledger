// Minimal typed client for the local backend.
//
// Inside the Tauri shell the backend runs as a sidecar on a loopback port with a random
// per-launch token, both obtained from the Rust side via `backend_config`. In a plain
// browser (development) requests go to /api and are proxied by Vite.

type Query = Record<string, string | number | boolean | undefined | null | (string | number)[]>;

interface BackendConfig {
  base: string;
  token: string | null;
}

let configPromise: Promise<BackendConfig> | null = null;

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function backendConfig(): Promise<BackendConfig> {
  if (!configPromise) {
    configPromise = (async () => {
      if (isTauri()) {
        const { invoke } = await import("@tauri-apps/api/core");
        const cfg = await invoke<{ url: string; token: string }>("backend_config");
        return { base: cfg.url, token: cfg.token };
      }
      return { base: "", token: (import.meta.env.VITE_LEDGER_TOKEN as string) || null };
    })();
  }
  return configPromise;
}

export interface BackendStatus {
  url: string;
  running: boolean;
  exit_code: number | null;
  spawn_error: string | null;
  log_tail: string[];
  log_file: string;
}

/** Shell-side view of the backend process (desktop app only). */
export async function backendStatus(): Promise<BackendStatus | null> {
  if (!isTauri()) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<BackendStatus>("backend_status");
}

/** The backend process is not running, so retrying cannot help. */
export class BackendDownError extends Error {
  constructor(public status: BackendStatus) {
    super(
      status.spawn_error ??
        `The local backend stopped${status.exit_code !== null ? ` (exit code ${status.exit_code})` : ""}.`,
    );
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function qs(query?: Query): string {
  if (!query) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)));
    else p.append(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const cfg = await backendConfig();
  const headers: Record<string, string> = {};
  if (cfg.token) headers["Authorization"] = `Bearer ${cfg.token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  // Wait for the backend to come up. A cold first start (creating the Python environment,
  // macOS scanning new native libraries) can take a while, so allow up to ~2 minutes, but
  // stop at once if the shell reports that the process has exited.
  const deadline = Date.now() + 120_000;
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(`${cfg.base}/api${path}${qs(query)}`, { method, headers, body: payload });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const j = await res.json();
          detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        } catch {
          /* not json */
        }
        throw new ApiError(res.status, detail);
      }
      if (res.status === 204) return undefined as T;
      return (await res.json()) as T;
    } catch (e) {
      if (e instanceof ApiError || Date.now() > deadline) throw e;
      if (attempt % 4 === 3) {
        const st = await backendStatus().catch(() => null);
        if (st && !st.running) throw new BackendDownError(st);
      }
      await new Promise((r) => setTimeout(r, 500));
    }
  }
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T>(path: string, body?: unknown, query?: Query) => request<T>("POST", path, body, query),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  async fileUrl(path: string): Promise<string> {
    const cfg = await backendConfig();
    return `${cfg.base}/api${path}${cfg.token ? `?token=${encodeURIComponent(cfg.token)}` : ""}`;
  },
};
