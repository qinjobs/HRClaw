export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = text;
  }
  if (!response.ok) {
    const message =
      typeof payload === "object" && payload && "error" in payload
        ? String((payload as { error?: string }).error || `请求失败(${response.status})`)
        : `请求失败(${response.status})`;
    throw new ApiError(message, response.status, payload);
  }
  return payload as T;
}

export function getJson<T>(path: string) {
  return request<T>(path, { method: "GET", headers: {} });
}

export function postJson<T>(path: string, payload?: unknown) {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}
