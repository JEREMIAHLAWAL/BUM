import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import uuid

AGENTS_ROOT = Path(__file__).resolve().parent.parent
BUM_STATE_DIR = AGENTS_ROOT / ".bum"
RUNS_DIR = BUM_STATE_DIR / "runs"


def generate_run_id() -> str:
    """Generate a unique run ID: run_YYYYMMDD_HHMMSS_<6_hex>."""
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"run_{timestamp_str}_{suffix}"


class EventLogger:
    """
    Structured event logger for pipeline runs.
    Emits events as JSON lines to pipeline/runs/<run_id>/events.jsonl.
    Fail-safe: errors during event writing will never crash the calling code.
    """

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or generate_run_id()
        self.run_dir = RUNS_DIR / self.run_id
        self.events_file = self.run_dir / "events.jsonl"
        self._init_storage()

    def _init_storage(self) -> None:
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            print(f"[WARN] Failed to initialize event directory {self.run_dir}: {exc}", file=sys.stderr)

    def emit(
        self,
        event: str,
        stage: Optional[str] = None,
        cycle: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit a structured JSONL event record.
        """
        try:
            record = {
                "run_id": self.run_id,
                "timestamp": time.time(),
                "event": event,
                "stage": stage,
                "cycle": cycle,
                "payload": payload or {},
            }
            # Ensure target directory exists before writing
            if not self.run_dir.exists():
                self.run_dir.mkdir(parents=True, exist_ok=True)

            with open(self.events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            # Observability must never crash the pipeline
            print(f"[WARN] Failed to emit event '{event}': {exc}", file=sys.stderr)


# Global / default event logger instance accessor
_current_logger: Optional[EventLogger] = None


def get_current_logger() -> Optional[EventLogger]:
    global _current_logger
    return _current_logger


def set_current_logger(logger: Optional[EventLogger]) -> None:
    global _current_logger
    _current_logger = logger


def emit_event(
    event: str,
    stage: Optional[str] = None,
    cycle: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Helper to emit through the currently active EventLogger if one is configured."""
    logger = get_current_logger()
    if logger is not None:
        logger.emit(event=event, stage=stage, cycle=cycle, payload=payload)
