"""Lightweight stop helper: no config, camera or MediaPipe imports."""
import sys
from lifecycle import request_stop

if __name__ == "__main__":
    try:
        sys.exit(request_stop())
    except Exception as exc:
        print(f"Shutdown request failed: {exc}", file=sys.stderr)
        sys.exit(1)
