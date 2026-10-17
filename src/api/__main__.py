"""Run the local API for the React frontend:  python -m src.api

Binds to 127.0.0.1 only. Prints a link that hands the per-launch session token to the frontend.
"""

from __future__ import annotations

import uvicorn

from src.api.app import create_app
from src.api.config import load_api_config
from src.config import configure_logging, get_settings


def main() -> None:
    configure_logging(get_settings().log_level)
    config = load_api_config()
    app = create_app(config)
    frontend = config.origins[0]
    print(f"Resume Optimizer local API on http://127.0.0.1:{config.port} (this computer only).")
    print(f"Open the frontend with this link to connect it:\n  {frontend}/#token={config.token}")
    print("The token changes every launch unless RESUME_OPTIMIZER_API_TOKEN is set. Ctrl+C to stop.")
    # access_log off: query strings can carry tracker search text, which must not reach the logs.
    uvicorn.run(app, host="127.0.0.1", port=config.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
