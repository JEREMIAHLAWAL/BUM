import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import App from './App';
import * as api from './api';
import type { RunState, RunSummary } from './types';

const mockRunSummaries: RunSummary[] = [
  {
    run_id: 'run_20260825_100000_aaa111',
    started_at: 1000,
    finished_at: 1030,
    task: 'Add workout generator widget',
    final_status: 'approve',
    cycles_used: 1,
    total_duration_sec: 30.5,
    is_running: false,
    events_count: 15,
  },
  {
    run_id: 'run_20260825_110000_bbb222',
    started_at: 2000,
    finished_at: null,
    task: 'Repair broken database adapter',
    final_status: 'running',
    cycles_used: 2,
    total_duration_sec: null,
    is_running: true,
    events_count: 8,
  },
];

const mockRunState: RunState = {
  run_id: 'run_20260825_100000_aaa111',
  task: 'Add workout generator widget',
  status: 'approve',
  current_cycle: 1,
  max_review_cycles: 3,
  started_at: 1000,
  finished_at: 1030,
  total_duration_sec: 30.5,
  reason: 'Approved',
  stages: {
    preflight: {
      status: 'complete',
      started_at: 1000,
      completed_at: 1002,
      duration_sec: 2.0,
      error: null,
    },
    planner: {
      status: 'complete',
      started_at: 1002,
      completed_at: 1006,
      duration_sec: 4.0,
      provider: 'openrouter',
      model: 'google/gemini-2.5-flash',
      output: '### PLANNER SPECIFICATION\n1. Add component widget',
    },
    frontend: {
      status: 'complete',
      attempts: [
        {
          type: 'initial',
          cycle: 0,
          status: 'complete',
          started_at: 1006,
          completed_at: 1012,
          duration_sec: 6.0,
          provider: 'openrouter',
          model: 'qwen/qwen3-coder-next',
          output: '```write:src/components/Widget.tsx\nexport const Widget = () => null;\n```',
          files: { created: ['src/components/Widget.tsx'], modified: [], deleted: [] },
        },
        {
          type: 'repair',
          cycle: 2,
          status: 'complete',
          started_at: 1020,
          completed_at: 1024,
          duration_sec: 4.0,
          provider: 'openrouter',
          model: 'qwen/qwen3-coder-next',
          output: 'Repair patch code',
          files: { created: [], modified: ['src/components/Widget.tsx'], deleted: [] },
        },
      ],
    },
    backend: {
      status: 'complete',
      attempts: [
        {
          type: 'initial',
          cycle: 0,
          status: 'complete',
          started_at: 1012,
          completed_at: 1013,
          duration_sec: 1.0,
          provider: 'openrouter',
          model: 'qwen/qwen3-coder-next',
          output: 'BACKEND TASK: None.',
        },
      ],
    },
    tester: {
      status: 'complete',
      attempts: [
        {
          cycle: 1,
          status: 'complete',
          started_at: 1013,
          completed_at: 1020,
          duration_sec: 7.0,
          provider: 'openrouter',
          model: 'deepseek/deepseek-v4-flash-0731',
          output: 'STATUS: PASS\nAll tests passing.',
        },
      ],
    },
    reviewer: {
      status: 'complete',
      attempts: [
        {
          cycle: 1,
          status: 'complete',
          started_at: 1020,
          completed_at: 1030,
          duration_sec: 10.0,
          provider: 'anthropic',
          model: 'claude-sonnet-5',
          output: 'VERDICT: APPROVE\nLooks great.',
        },
      ],
    },
  },
  files_changed: {
    created: ['src/components/Widget.tsx'],
    modified: ['src/app/index.tsx'],
    deleted: [],
    history: [],
  },
  tests: [
    {
      timestamp: 1015,
      stage: 'tester',
      cycle: 1,
      commands: [
        {
          command: 'npm run ts:check',
          returncode: 0,
          stdout: 'TypeScript passed with 0 errors',
          stderr: '',
          timed_out: false,
        },
        {
          command: 'npm test',
          returncode: 0,
          stdout: '237 passed, 237 total',
          stderr: '',
          timed_out: false,
        },
      ],
    },
  ],
  git: {
    diff_stat: '2 files changed, 40 insertions(+)',
    changed_files: ['src/components/Widget.tsx', 'src/app/index.tsx'],
    untracked_files: [],
  },
  review: {
    cycle: 1,
    verdict: 'APPROVE',
    frontend_fix_required: false,
    backend_fix_required: false,
    dependency_fix_required: false,
  },
  retries: [],
};

describe('BUM Console Dashboard', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchRuns').mockResolvedValue(mockRunSummaries);
    vi.spyOn(api, 'fetchRunDetails').mockResolvedValue(mockRunState);
    vi.spyOn(api, 'fetchPipelineStatus').mockResolvedValue({ running: false, run_id: null, task: null });
    vi.spyOn(api, 'launchPipeline').mockResolvedValue({ accepted: true, run_id: 'run_new_launched_999', task: 'Sample task' });
    vi.spyOn(api, 'subscribeToRunEvents').mockImplementation(() => () => {});
  });

  it('renders header, runs list, prompt textarea, and all 5 pipeline stages', async () => {
    render(<App />);

    // Header branding
    expect(screen.getAllByText(/BUM/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/CONSOLE/i).length).toBeGreaterThan(0);

    // Runs in sidebar
    await waitFor(() => {
      expect(screen.getByText('Add workout generator widget')).toBeInTheDocument();
      expect(screen.getByText('Repair broken database adapter')).toBeInTheDocument();
    });

    // Prompt input section
    expect(screen.getByText(/New development task/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Describe what you want to build/i)).toBeInTheDocument();

    // 5 Stages rendered after state loaded
    await waitFor(() => {
      expect(screen.getByText('Planner')).toBeInTheDocument();
      expect(screen.getByText('Frontend')).toBeInTheDocument();
      expect(screen.getByText('Backend')).toBeInTheDocument();
      expect(screen.getByText('Tester')).toBeInTheDocument();
      expect(screen.getByText('Reviewer')).toBeInTheDocument();
    });
  });

  it('disables Run button when prompt is empty/whitespace', async () => {
    render(<App />);

    const runBtn = screen.getByRole('button', { name: /Launch task/i });
    expect(runBtn).toBeDisabled();

    const textarea = screen.getByPlaceholderText(/Describe what you want to build/i);
    fireEvent.change(textarea, { target: { value: '   ' } });
    expect(runBtn).toBeDisabled();

    fireEvent.change(textarea, { target: { value: 'Build active workout timer' } });
    expect(runBtn).not.toBeDisabled();
  });

  it('submits valid task, invokes launch API, auto-selects new run ID, and clears input', async () => {
    const launchSpy = vi.spyOn(api, 'launchPipeline').mockResolvedValue({
      accepted: true,
      run_id: 'run_20260825_120000_new123',
      task: 'Build active workout timer',
    });

    render(<App />);

    const textarea = screen.getByPlaceholderText(/Describe what you want to build/i);
    fireEvent.change(textarea, { target: { value: 'Build active workout timer' } });

    const runBtn = screen.getByRole('button', { name: /Launch task/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(launchSpy).toHaveBeenCalledWith('Build active workout timer', undefined);
    });

    expect((textarea as HTMLTextAreaElement).value).toBe('');
  });

  it('submits valid task with custom label, invokes launch API with label, and clears input', async () => {
    const launchSpy = vi.spyOn(api, 'launchPipeline').mockResolvedValue({
      accepted: true,
      run_id: 'run_20260825_120000_new123',
      task: 'Build active workout timer',
      label: 'Feature 3',
    });

    render(<App />);

    const labelInput = screen.getByPlaceholderText(/Run label/i);
    const textarea = screen.getByPlaceholderText(/Describe what you want to build/i);

    fireEvent.change(labelInput, { target: { value: 'Feature 3' } });
    fireEvent.change(textarea, { target: { value: 'Build active workout timer' } });

    const runBtn = screen.getByRole('button', { name: /Launch task/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(launchSpy).toHaveBeenCalledWith('Build active workout timer', 'Feature 3');
    });

    expect((textarea as HTMLTextAreaElement).value).toBe('');
    expect((labelInput as HTMLInputElement).value).toBe('');
  });

  it('disables Run button and shows active badge when pipeline is running', async () => {
    vi.spyOn(api, 'fetchPipelineStatus').mockResolvedValue({
      running: true,
      run_id: 'run_20260825_110000_bbb222',
      task: 'Repair broken database adapter',
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Pipeline Running/i })).toBeDisabled();
    });
  });

  it('handles 409 conflict error cleanly and displays message', async () => {
    const conflictError = new Error('Pipeline already running with run_id: run_running_test');
    (conflictError as any).status = 409;
    (conflictError as any).run_id = 'run_running_test';
    vi.spyOn(api, 'launchPipeline').mockRejectedValue(conflictError);

    render(<App />);

    const textarea = screen.getByPlaceholderText(/Describe what you want to build/i);
    fireEvent.change(textarea, { target: { value: 'New conflicting task' } });

    const runBtn = screen.getByRole('button', { name: /Launch task/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(screen.getByText(/Pipeline is already running/i)).toBeInTheDocument();
    });
  });

  it('enables Stop button when running and triggers cancellation request', async () => {
    vi.spyOn(api, 'fetchPipelineStatus').mockResolvedValue({
      running: true,
      run_id: 'run_20260825_110000_bbb222',
      task: 'Repair broken database adapter',
      cancellation_requested: false,
    });
    const stopSpy = vi.spyOn(api, 'stopPipeline').mockResolvedValue({
      accepted: true,
      run_id: 'run_20260825_110000_bbb222',
      status: 'cancellation_requested',
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /STOP PIPELINE/i })).toBeInTheDocument();
    });

    const stopBtn = screen.getByRole('button', { name: /STOP PIPELINE/i });
    expect(stopBtn).not.toBeDisabled();

    fireEvent.click(stopBtn);

    await waitFor(() => {
      expect(stopSpy).toHaveBeenCalled();
    });
  });

  it('enables Retry button for failed/blocked/interrupted runs and triggers retry API', async () => {
    const failedRunSummary: RunSummary = {
      run_id: 'run_20260825_100000_aaa111',
      started_at: 1000,
      finished_at: 1030,
      task: 'Add workout generator widget',
      final_status: 'failed',
      cycles_used: 1,
      total_duration_sec: 30.5,
      is_running: false,
      events_count: 15,
    };
    const failedRunState: RunState = {
      ...mockRunState,
      run_id: 'run_20260825_100000_aaa111',
      status: 'failed',
      reason: 'PROVIDER_TIMEOUT',
    };
    vi.spyOn(api, 'fetchRuns').mockResolvedValue([failedRunSummary]);
    vi.spyOn(api, 'fetchRunDetails').mockResolvedValue(failedRunState);
    const retrySpy = vi.spyOn(api, 'retryPipelineRun').mockResolvedValue({
      accepted: true,
      run_id: 'run_new_retry_999',
      task: 'Add workout generator widget',
      retry_of: 'run_20260825_100000_aaa111',
    } as any);

    render(<App />);

    await waitFor(() => {
      const retryBtn = screen.getByRole('button', { name: /Retry in a new run/i });
      expect(retryBtn).not.toBeDisabled();
      fireEvent.click(retryBtn);
    });

    await waitFor(() => {
      expect(retrySpy).toHaveBeenCalledWith('run_20260825_100000_aaa111');
    });
  });

  it('enables Approve/Reject for AWAITING_HUMAN_APPROVAL runs', async () => {
    const awaitingSummary: RunSummary = {
      run_id: 'run_20260825_170948_74722e',
      started_at: 1000,
      finished_at: 1030,
      task: 'Task awaiting decision',
      final_status: 'AWAITING_HUMAN_APPROVAL',
      cycles_used: 1,
      total_duration_sec: 30.5,
      is_running: false,
      events_count: 10,
    };
    const awaitingState: RunState = {
      ...mockRunState,
      run_id: 'run_20260825_170948_74722e',
      status: 'awaiting_human_approval',
    };
    vi.spyOn(api, 'fetchRuns').mockResolvedValue([awaitingSummary]);
    vi.spyOn(api, 'fetchRunDetails').mockResolvedValue(awaitingState);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Approve & merge/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Request changes/i })).toBeInTheDocument();
    });
  });

  it('triggers Approve API on click and updates state', async () => {
    const awaitingState: RunState = {
      ...mockRunState,
      run_id: 'run_awaiting_test',
      status: 'awaiting_human_approval',
    };
    vi.spyOn(api, 'fetchRuns').mockResolvedValue([{
      run_id: 'run_awaiting_test',
      started_at: 1000,
      finished_at: 1030,
      task: 'Task awaiting decision',
      final_status: 'AWAITING_HUMAN_APPROVAL',
      cycles_used: 1,
      total_duration_sec: 30.5,
      is_running: false,
      events_count: 10,
    }]);
    vi.spyOn(api, 'fetchRunDetails').mockResolvedValue(awaitingState);
    const approveSpy = vi.spyOn(api, 'approveRun').mockResolvedValue({
      accepted: true,
      run_id: 'run_awaiting_test',
      status: 'APPROVED',
    });

    render(<App />);

    await waitFor(() => {
      const approveBtn = screen.getByRole('button', { name: /Approve & merge/i });
      expect(approveBtn).not.toBeDisabled();
      fireEvent.click(approveBtn);
    });

    await waitFor(() => {
      expect(approveSpy).toHaveBeenCalledWith('run_awaiting_test');
    });
  });

  it('opens Reject modal, captures reason, and triggers Reject API', async () => {
    const awaitingState: RunState = {
      ...mockRunState,
      run_id: 'run_awaiting_test',
      status: 'awaiting_human_approval',
    };
    vi.spyOn(api, 'fetchRuns').mockResolvedValue([{
      run_id: 'run_awaiting_test',
      started_at: 1000,
      finished_at: 1030,
      task: 'Task awaiting decision',
      final_status: 'AWAITING_HUMAN_APPROVAL',
      cycles_used: 1,
      total_duration_sec: 30.5,
      is_running: false,
      events_count: 10,
    }]);
    vi.spyOn(api, 'fetchRunDetails').mockResolvedValue(awaitingState);
    const rejectSpy = vi.spyOn(api, 'rejectRun').mockResolvedValue({
      accepted: true,
      run_id: 'run_awaiting_test',
      status: 'REJECTED',
      reason: 'Needs revision',
    });

    render(<App />);

    await waitFor(() => {
      const rejectBtn = screen.getByRole('button', { name: /Request changes/i });
      expect(rejectBtn).not.toBeDisabled();
      fireEvent.click(rejectBtn);
    });

    expect(screen.getByText('Change request')).toBeInTheDocument();
    const textarea = screen.getByPlaceholderText(/What needs to be fixed/i);
    fireEvent.change(textarea, { target: { value: 'Needs revision' } });

    const confirmBtns = screen.getAllByRole('button', { name: /Request changes/i });
    fireEvent.click(confirmBtns[confirmBtns.length - 1]);

    await waitFor(() => {
      expect(rejectSpy).toHaveBeenCalledWith('run_awaiting_test', 'Needs revision');
    });
  });

  it('renders test results in tests panel', async () => {
    render(<App />);

    await waitFor(() => {
      const testsTab = screen.getByRole('tab', { name: /Tests & shell/i });
      fireEvent.click(testsTab);
    });

    expect(screen.getByText(/Verification suite/i)).toBeInTheDocument();
    expect(screen.getByText('npm run ts:check')).toBeInTheDocument();
    expect(screen.getByText('npm test')).toBeInTheDocument();
  });

  it('renders changed files and git status', async () => {
    render(<App />);

    await waitFor(() => {
      const changesTab = screen.getByRole('tab', { name: /Changes/i });
      fireEvent.click(changesTab);
    });

    expect(screen.getByText('Widget.tsx')).toBeInTheDocument();
    expect(screen.getByText('index.tsx')).toBeInTheDocument();
  });

  it('renders review tab with verdicts and findings', async () => {
    render(<App />);

    await waitFor(() => {
      const reviewTab = screen.getByRole('tab', { name: /Review/i });
      fireEvent.click(reviewTab);
    });

    expect(screen.getAllByText(/AUTOMATED VERDICT/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Acceptance criteria satisfied/i)).toBeInTheDocument();
  });

  it('handles switching runs when clicking sidebar', async () => {
    const detailSpy = vi.spyOn(api, 'fetchRunDetails');
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Repair broken database adapter')).toBeInTheDocument();
    });

    const secondRun = screen.getByText('Repair broken database adapter');
    fireEvent.click(secondRun);

    await waitFor(() => {
      expect(detailSpy).toHaveBeenCalledWith('run_20260825_110000_bbb222');
    });
  });
});
