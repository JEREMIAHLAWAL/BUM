#!/usr/bin/env python3
"""Entrypoint to run the Trayne Agent Flow Control Room service."""
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import uvicorn
from orchestrator.agent_flow.server import app

def main():
    host = os.environ.get("AGENT_FLOW_HOST", "0.0.0.0")
    port = int(os.environ.get("AGENT_FLOW_PORT", "8900"))
    print(f"Starting BUM Control Room on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
