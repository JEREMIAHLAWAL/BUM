export type CanonicalRunStatus =
  | 'running'
  | 'awaiting_human_approval'
  | 'approved'
  | 'rejected'
  | 'blocked'
  | 'failed'
  | 'cancelled'
  | 'interrupted'
  | 'empty';

export interface RunSummary {
  run_id: string;
  label?: string | null;
  started_at: number | null;
  finished_at: number | null;
  task: string | null;
  retry_of?: string | null;
  final_status: CanonicalRunStatus | string;
  cycles_used: number;
  total_duration_sec: number | null;
  is_running: boolean;
  events_count: number;
}

export type StageStatus = 'waiting' | 'running' | 'complete' | 'failed' | 'blocked' | 'cancelled';

export interface StageAttempt {
  type?: 'initial' | 'repair';
  cycle?: number;
  status: StageStatus;
  started_at: number | null;
  completed_at: number | null;
  duration_sec: number | null;
  provider?: string | null;
  model?: string | null;
  output?: string | null;
  files?: {
    created: string[];
    modified: string[];
    deleted: string[];
  } | null;
}

export interface SingleStageState {
  status: StageStatus;
  started_at: number | null;
  completed_at: number | null;
  duration_sec: number | null;
  provider?: string | null;
  model?: string | null;
  output?: string | null;
  error?: string | null;
}

export interface MultiAttemptStageState {
  status: StageStatus;
  attempts: StageAttempt[];
}

export interface CommandResult {
  command: string;
  returncode: number;
  stdout: string;
  stderr: string;
  timed_out: boolean;
}

export interface TestEntry {
  timestamp: number;
  stage: string;
  cycle: number | null;
  commands: CommandResult[];
}

export interface GitState {
  timestamp?: number;
  diff_stat?: string;
  changed_files?: string[];
  untracked_files?: string[];
  git_results?: Array<{
    command: string;
    returncode: number;
    stdout: string;
    stderr: string;
    timed_out: boolean;
  }>;
}

export interface ReviewState {
  timestamp?: number;
  cycle?: number;
  verdict?: 'APPROVE' | 'CHANGES REQUIRED' | string;
  frontend_fix_required?: boolean;
  backend_fix_required?: boolean;
  dependency_fix_required?: boolean;
  human_decision?: {
    timestamp: number;
    decision: 'APPROVE' | 'REJECT' | string;
    reason?: string | null;
    source?: string;
  } | null;
}

export interface RetryEntry {
  timestamp: number;
  from_cycle: number;
  to_cycle: number;
  target_agents: string[];
}

export interface FileOpEntry {
  path: string;
  op: 'write' | 'patch' | 'delete' | string;
  stage: string;
  status: 'in_progress' | 'verified' | 'failed' | string;
  bytes?: number;
  timestamp: number;
  completed_at?: number | null;
}

export interface FilesHistoryEntry {
  timestamp: number;
  role: string;
  cycle: number | null;
  parsed_count: number;
  executed_count: number;
  created: string[];
  modified: string[];
  deleted: string[];
}

export interface AgentConfig {
  provider?: string | null;
  model?: string | null;
  instructions?: string | null;
}

export interface RunState {
  run_id: string | null;
  label?: string | null;
  task: string | null;
  retry_of?: string | null;
  status: CanonicalRunStatus | string;
  current_cycle: number;
  max_review_cycles: number;
  agent_configs?: Record<string, AgentConfig>;
  started_at: number | null;
  finished_at: number | null;
  total_duration_sec: number | null;
  reason: string | null;
  stages: {
    preflight: SingleStageState;
    planner: SingleStageState;
    frontend: MultiAttemptStageState;
    backend: MultiAttemptStageState;
    tester: MultiAttemptStageState;
    reviewer: MultiAttemptStageState;
  };
  files_changed: {
    created: string[];
    modified: string[];
    deleted: string[];
    history: FilesHistoryEntry[];
    operations?: FileOpEntry[];
  };
  tests: TestEntry[];
  git: GitState;
  review: ReviewState;
  retries: RetryEntry[];
}
