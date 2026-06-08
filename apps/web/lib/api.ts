export type FileRef = {
  id: string;
  name: string;
};

export type PrepareResponse = {
  session_id: string;
  state: string;
  message?: string | null;
  questions: string[];
  plan_text?: string | null;
  limitation_message?: string | null;
};

export type OutputResponse = {
  label: string;
  display_type: string;
  value: unknown;
};

export type ActivityResponse = {
  title: string;
  status: string;
  error_message?: string | null;
};

export type RunResponse = {
  session_id: string;
  run_id: string;
  state: string;
  status: string;
  version: number;
  outputs: OutputResponse[];
  activities: ActivityResponse[];
  error_message?: string | null;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  return parseResponse<T>(response);
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : "请求处理失败。";
    throw new Error(detail);
  }
  return payload as T;
}

export async function createSession(): Promise<{ session_id: string; state: string }> {
  return requestJson("/api/sessions", { method: "POST" });
}

export async function uploadFiles(sessionId: string, files: File[]): Promise<FileRef[]> {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/uploads`, {
    method: "POST",
    body
  });
  const payload = await parseResponse<{ files: FileRef[] }>(response);
  return payload.files;
}

export async function prepareRequest(
  sessionId: string,
  userRequest: string,
  files: FileRef[]
): Promise<PrepareResponse> {
  return requestJson(`/api/sessions/${sessionId}/prepare`, {
    method: "POST",
    body: JSON.stringify({ user_request: userRequest, files })
  });
}

export async function executePrepared(
  sessionId: string,
  userText: string,
  files: FileRef[]
): Promise<RunResponse> {
  return requestJson(`/api/sessions/${sessionId}/execute`, {
    method: "POST",
    body: JSON.stringify({ user_text: userText, files })
  });
}

export async function submitFeedback(
  sessionId: string,
  feedback: string
): Promise<PrepareResponse> {
  return requestJson(`/api/sessions/${sessionId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback })
  });
}

export async function submitFollowUp(
  sessionId: string,
  userText: string,
  files: FileRef[]
): Promise<RunResponse> {
  return requestJson(`/api/sessions/${sessionId}/follow-up`, {
    method: "POST",
    body: JSON.stringify({ user_text: userText, files })
  });
}
