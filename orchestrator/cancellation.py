import threading
from typing import Optional


class CancellationToken:
    """
    Thread-safe cancellation token for a single pipeline run execution.
    Allows cooperative cancellation at defined safe checkpoints.
    """

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id
        self._lock = threading.Lock()
        self._cancelled = False
        self._reason: Optional[str] = None

    def request_cancel(self, reason: str = "USER_REQUESTED_STOP") -> bool:
        """
        Request cancellation. Returns True if successfully requested (first time),
        or False if already requested.
        """
        with self._lock:
            if self._cancelled:
                return False
            self._cancelled = True
            self._reason = reason
            return True

    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        with self._lock:
            return self._cancelled

    @property
    def reason(self) -> Optional[str]:
        with self._lock:
            return self._reason


class PipelineCancelledException(Exception):
    """Exception raised internally when cancellation is acknowledged at a checkpoint."""

    def __init__(self, reason: str = "USER_REQUESTED_STOP"):
        super().__init__(f"Pipeline execution cancelled: {reason}")
        self.reason = reason
