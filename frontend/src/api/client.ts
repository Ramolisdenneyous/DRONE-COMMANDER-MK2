const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8004";

export type CommandEnvelope = {
  command_id?: string;
  expected_state_version?: number;
  payload?: Record<string, unknown>;
};

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, body: any, raw: string) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : typeof body?.detail?.msg === "string"
          ? body.detail.msg
          : raw;
    super(detail);
    this.status = status;
    this.body = body;
  }
}

function uuid(): string {
  return crypto.randomUUID();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    let body: any = text;
    try {
      body = JSON.parse(text);
    } catch {
      /* keep text */
    }
    throw new ApiError(res.status, body, text);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ ok: boolean }>("/health"),
  boot: () => request<any>("/api/v1/catalog/boot"),
  createSession: () => request<any>("/api/v1/sessions", { method: "POST" }),
  getSession: (id: string) => request<any>(`/api/v1/sessions/${id}`),
  updatePrep: (id: string, prep: Record<string, unknown>) =>
    request<any>(`/api/v1/sessions/${id}/prep`, {
      method: "PUT",
      body: JSON.stringify({ command_id: uuid(), payload: prep }),
    }),
  deploy: (id: string, seed?: number) =>
    request<any>(`/api/v1/sessions/${id}/deploy`, {
      method: "POST",
      body: JSON.stringify({ command_id: uuid(), payload: seed ? { seed } : {} }),
    }),
  getBattle: (id: string) => request<any>(`/api/v1/battles/${id}`),
  commanderAction: (battleId: string, stateVersion: number, optionId: string) =>
    request<any>(`/api/v1/battles/${battleId}/commander/actions`, {
      method: "POST",
      body: JSON.stringify({
        command_id: uuid(),
        expected_state_version: stateVersion,
        payload: { option_id: optionId },
      }),
    }),
  commanderMove: (battleId: string, stateVersion: number, q: number, r: number) =>
    request<any>(`/api/v1/battles/${battleId}/commander/move`, {
      method: "POST",
      body: JSON.stringify({
        command_id: uuid(),
        expected_state_version: stateVersion,
        payload: { q, r },
      }),
    }),
  commanderRam: (
    battleId: string,
    stateVersion: number,
    abilityId: string,
    extras?: { target_unit_id?: string; q?: number; r?: number }
  ) =>
    request<any>(`/api/v1/battles/${battleId}/commander/ram`, {
      method: "POST",
      body: JSON.stringify({
        command_id: uuid(),
        expected_state_version: stateVersion,
        payload: {
          ability_id: abilityId,
          target_unit_id: extras?.target_unit_id,
          q: extras?.q,
          r: extras?.r,
        },
      }),
    }),
  endActivation: (battleId: string, stateVersion: number) =>
    request<any>(`/api/v1/battles/${battleId}/commander/end-activation`, {
      method: "POST",
      body: JSON.stringify({
        command_id: uuid(),
        expected_state_version: stateVersion,
        payload: {},
      }),
    }),
  controlPhaseAllocate: (battleId: string, stateVersion: number, droneId: string) =>
    request<any>(`/api/v1/battles/${battleId}/control-phase/allocate`, {
      method: "POST",
      body: JSON.stringify({
        command_id: uuid(),
        expected_state_version: stateVersion,
        payload: { drone_id: droneId },
      }),
    }),
  controlPhaseReclaim: (battleId: string, stateVersion: number, droneId: string) =>
    request<any>(`/api/v1/battles/${battleId}/control-phase/reclaim`, {
      method: "POST",
      body: JSON.stringify({
        command_id: uuid(),
        expected_state_version: stateVersion,
        payload: { drone_id: droneId },
      }),
    }),
  controlPhaseComplete: (battleId: string, stateVersion: number) =>
    request<any>(`/api/v1/battles/${battleId}/control-phase/complete`, {
      method: "POST",
      body: JSON.stringify({
        command_id: uuid(),
        expected_state_version: stateVersion,
        payload: {},
      }),
    }),
  resolveNext: (battleId: string, stateVersion: number) =>
    request<any>(`/api/v1/battles/${battleId}/resolve-next`, {
      method: "POST",
      body: JSON.stringify({
        command_id: uuid(),
        expected_state_version: stateVersion,
        payload: {},
      }),
    }),
  setDirective: (
    battleId: string,
    text: string,
    targetUnitId?: string | null,
    extras?: { order_id?: string; target_refs?: Array<{ kind: string; unit_instance_id: string }> }
  ) =>
    request<any>(`/api/v1/battles/${battleId}/directives`, {
      method: "PUT",
      body: JSON.stringify({
        command_id: uuid(),
        payload: {
          text,
          target_unit_id: targetUnitId || null,
          order_id: extras?.order_id ?? null,
          target_refs: extras?.target_refs ?? [],
        },
      }),
    }),
  debrief: (battleId: string) => request<any>(`/api/v1/battles/${battleId}/debrief`),
  submitFeedback: (sessionId: string, message: string, context?: Record<string, unknown>) =>
    request<{ ok: boolean; session_id: string; battle_id?: string }>(`/api/v1/sessions/${sessionId}/feedback`, {
      method: "POST",
      body: JSON.stringify({
        command_id: uuid(),
        payload: { message, context: context || {} },
      }),
    }),
  communications: (battleId: string) => request<any>(`/api/v1/battles/${battleId}/communications`),
  diagnosticsBattle: (battleId: string) => request<any>(`/api/v1/diagnostics/battles/${battleId}`),
  diagnosticsSession: (sessionId: string) => request<any>(`/api/v1/diagnostics/sessions/${sessionId}`),
  diagnosticsSessions: () => request<any>(`/api/v1/diagnostics/sessions`),
};
