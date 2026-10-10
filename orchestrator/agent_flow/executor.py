import threading
from typing import Any, Callable, Dict, Optional
from orchestrator.events import generate_run_id
from orchestrator.cancellation import CancellationToken


class PipelineExecutionManager:
    """
    Thread-safe execution manager for running the Trayne orchestrator pipeline.
    Ensures strictly one active pipeline execution at a time and tracks active run status.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._current_run_id: Optional[str] = None
        self._current_task: Optional[str] = None
        self._token: Optional[CancellationToken] = None
        self._thread: Optional[threading.Thread] = None

    def get_status(self) -> Dict[str, Any]:
        """Return the current pipeline execution status."""
        with self._lock:
            cancellation_req = self._token.is_cancelled() if self._token else False
            return {
                "running": self._running,
                "run_id": self._current_run_id,
                "task": self._current_task,
                "cancellation_requested": cancellation_req,
            }

    def request_stop(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Request cancellation of the active pipeline.
        Raises ValueError if no pipeline is running, or if run_id does not match active run.
        """
        with self._lock:
            if not self._running or not self._token:
                raise ValueError("No pipeline is currently running.")

            if run_id and self._current_run_id != run_id:
                raise ValueError(f"Run ID mismatch: active run is '{self._current_run_id}', not '{run_id}'.")

            already_requested = not self._token.request_cancel()
            return {
                "accepted": True,
                "run_id": self._current_run_id,
                "status": "cancellation_requested",
                "already_requested": already_requested,
            }

    def start_pipeline(
        self,
        task: str,
        pipeline_func: Optional[Callable[..., Any]] = None,
        retry_of: Optional[str] = None,
        label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Start a new pipeline run asynchronously in a worker thread.
        Raises ValueError if task is empty/whitespace.
        Raises RuntimeError (conflict) if a pipeline is already running.
        Returns metadata including the assigned run_id and lineage.
        """
        clean_task = task.strip() if task else ""
        if not clean_task:
            raise ValueError("Task description cannot be empty or whitespace.")

        clean_label = label.strip() if label and label.strip() else None

        with self._lock:
            if self._running:
                raise RuntimeError(f"Pipeline already running with run_id: {self._current_run_id}")

            assigned_run_id = generate_run_id()
            token = CancellationToken(run_id=assigned_run_id)
            self._running = True
            self._current_run_id = assigned_run_id
            self._current_task = clean_task
            self._token = token

        if pipeline_func is None:
            from orchestrator.pipeline import run_pipeline
            def _target_runner(t_text, r_id, c_token):
                return run_pipeline(t_text, run_id=r_id, cancellation_token=c_token, retry_of=retry_of, label=clean_label)
            target_func = _target_runner
        else:
            target_func = pipeline_func

        def _worker():
            try:
                target_func(clean_task, assigned_run_id, token)
            except Exception as exc:
                print(f"[ERROR] Pipeline worker execution failed for {assigned_run_id}: {exc}")
            finally:
                with self._lock:
                    self._running = False
                    self._current_run_id = None
                    self._current_task = None
                    self._token = None

        thread = threading.Thread(
            target=_worker,
            name=f"pipeline-worker-{assigned_run_id}",
            daemon=True,
        )
        self._thread = thread
        thread.start()

        res_payload = {
            "accepted": True,
            "run_id": assigned_run_id,
            "task": clean_task,
        }
        if clean_label:
            res_payload["label"] = clean_label
        if retry_of:
            res_payload["retry_of"] = retry_of

        return res_payload


# Global instance
execution_manager = PipelineExecutionManager()
