import type { RunState, RunSummary } from './types';

const API_BASE = import.meta.env.VITE_API_BASE !== undefined ? import.meta.env.VITE_API_BASE : '';

export interface PipelineStatus {
  running: boolean;
  run_id: string | null;
  task: string | null;
  cancellation_requested?: boolean;
}

export interface RunLaunchResponse {
  accepted: boolean;
  run_id: string;
  task: string;
  label?: string | null;
}

export interface StopPipelineResponse {
  accepted: boolean;
  run_id: string;
  status: string;
  already_requested?: boolean;
}

export interface HumanDecisionResponse {
  accepted: boolean;
  run_id: string;
  status: 'APPROVED' | 'REJECTED';
  reason?: string | null;
  event?: any;
}

export interface WorkspaceProject {
  id: string;
  name: string;
  path: string;
  exists: boolean;
  is_active: boolean;
  type: string;
}

export interface ProjectsResponse {
  projects: WorkspaceProject[];
  active_path: string;
  source: string;
}

export interface PromptPreviewResponse {
  file: string;
  resolved_path: string;
  content: string;
  size: number;
}

export async function fetchPromptPreview(file: string): Promise<PromptPreviewResponse> {
  const url = `${API_BASE}/api/prompts/preview?file=${encodeURIComponent(file)}`;
  const res = await fetch(url);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to fetch prompt file (${res.status})`);
  }
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string; service: string }> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) {
    throw new Error(`Health check failed (${res.status})`);
  }
  return res.json();
}

export async function fetchPipelineStatus(): Promise<PipelineStatus> {
  const res = await fetch(`${API_BASE}/api/pipeline/status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch pipeline status (${res.status})`);
  }
  return res.json();
}

export async function stopPipeline(runId?: string | null): Promise<StopPipelineResponse> {
  const url = runId
    ? `${API_BASE}/api/runs/${encodeURIComponent(runId)}/stop`
    : `${API_BASE}/api/pipeline/stop`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to stop pipeline (${res.status})`);
  }

  return res.json();
}

export async function resumePipelineRun(runId: string): Promise<RunLaunchResponse> {
  const url = `${API_BASE}/api/runs/${encodeURIComponent(runId)}/resume`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (res.status === 409) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(errorData.message || 'Pipeline already running');
    (err as any).status = 409;
    (err as any).run_id = errorData.run_id;
    throw err;
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to resume run ${runId} (${res.status})`);
  }

  return res.json();
}

export async function retryPipelineRun(runId: string): Promise<RunLaunchResponse> {
  const url = `${API_BASE}/api/runs/${encodeURIComponent(runId)}/retry`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (res.status === 409) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(errorData.message || 'Pipeline already running');
    (err as any).status = 409;
    (err as any).run_id = errorData.run_id;
    throw err;
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to retry run ${runId} (${res.status})`);
  }

  return res.json();
}

export async function approveRun(runId: string): Promise<HumanDecisionResponse> {
  const url = `${API_BASE}/api/runs/${encodeURIComponent(runId)}/approve`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to approve run ${runId} (${res.status})`);
  }

  return res.json();
}

export async function rejectRun(runId: string, reason?: string | null): Promise<HumanDecisionResponse> {
  const url = `${API_BASE}/api/runs/${encodeURIComponent(runId)}/reject`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ reason: reason || null }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to reject run ${runId} (${res.status})`);
  }

  return res.json();
}


export async function launchPipeline(task: string, label?: string): Promise<RunLaunchResponse> {
  const res = await fetch(`${API_BASE}/api/runs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ task, label: label || undefined }),
  });

  if (res.status === 409) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(errorData.message || 'Pipeline already running');
    (err as any).status = 409;
    (err as any).run_id = errorData.run_id;
    throw err;
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to launch pipeline (${res.status})`);
  }

  return res.json();
}

export async function fetchRuns(): Promise<RunSummary[]> {
  const res = await fetch(`${API_BASE}/api/runs`);
  if (!res.ok) {
    throw new Error(`Failed to fetch runs (${res.status})`);
  }
  const data = await res.json();
  return data.runs || [];
}

export async function fetchRunDetails(runId: string): Promise<RunState> {
  const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch run details for ${runId} (${res.status})`);
  }
  return res.json();
}

export async function purgeRuns(): Promise<{ purged_count: number; status: string }> {
  const res = await fetch(`${API_BASE}/api/runs/purge`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to purge runs (${res.status})`);
  }
  return res.json();
}

export async function deleteRun(runId: string): Promise<{ run_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to delete run ${runId} (${res.status})`);
  }
  return res.json();
}

export async function deleteSingleRun(runId: string): Promise<{ run_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to delete run ${runId} (${res.status})`);
  }
  return res.json();
}

export async function fetchProjects(): Promise<ProjectsResponse> {
  const res = await fetch(`${API_BASE}/api/projects`);
  if (!res.ok) {
    throw new Error(`Failed to fetch workspace projects (${res.status})`);
  }
  return res.json();
}

export async function selectProject(pathOrId: string): Promise<ProjectsResponse> {
  const res = await fetch(`${API_BASE}/api/projects/select`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ path: pathOrId }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Failed to switch project (${res.status})`);
  }
  return res.json();
}

export function subscribeToRunEvents(
  runId: string,
  onEvent: (event: any) => void,
  onClose?: () => void,
  onError?: (err: any) => void
): () => void {
  const url = `${API_BASE}/api/runs/${encodeURIComponent(runId)}/stream`;
  let eventSource: EventSource | null = null;
  let isClosed = false;
  let reconnectTimeout: any = null;
  let retryCount = 0;

  function connect() {
    if (isClosed) return;
    try {
      eventSource = new EventSource(url);

      eventSource.onopen = () => {
        retryCount = 0;
      };

      eventSource.onmessage = (e) => {
        try {
          const parsed = JSON.parse(e.data);
          onEvent(parsed);
        } catch {
          // ignore parsing error for non-json
        }
      };

      eventSource.addEventListener('close', () => {
        if (eventSource) eventSource.close();
        if (onClose) onClose();
      });

      eventSource.onerror = (err) => {
        if (onError) onError(err);
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        if (!isClosed) {
          // Exponential backoff auto-reconnect (1s up to max 10s)
          const delay = Math.min(1000 * Math.pow(1.5, retryCount), 10000);
          retryCount += 1;
          reconnectTimeout = setTimeout(connect, delay);
        }
      };
    } catch (err) {
      if (onError) onError(err);
    }
  }

  connect();

  return () => {
    isClosed = true;
    if (reconnectTimeout) clearTimeout(reconnectTimeout);
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  };
}
