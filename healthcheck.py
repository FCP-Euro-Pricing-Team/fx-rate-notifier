"""Simple healthcheck endpoint for Cloud Run container."""
import os
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_port() -> int:
    """Parse HEALTHCHECK_PORT env var, falling back to 8080 on invalid values."""
    port_str = os.getenv("HEALTHCHECK_PORT", "8080")
    try:
        port = int(port_str)
    except ValueError:
        logger.warning("Invalid HEALTHCHECK_PORT '%s', using default 8080", port_str)
        return 8080
    if not 1 <= port <= 65535:
        logger.warning(
            "HEALTHCHECK_PORT '%s' out of range (1-65535), using default 8080",
            port_str,
        )
        return 8080
    return port


PORT = _get_port()
VERSION = "0.1.0"


class HealthHandler(BaseHTTPRequestHandler):
    """Handles GET /health requests."""

    def do_GET(self) -> None:
        if self.path == "/health":
            response = {
                "status": "ok",
                "version": VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "environment": os.getenv("ENVIRONMENT", "development"),
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        logger.info(format, *args)


def start_server() -> None:
    """Start the healthcheck HTTP server.

    Listens on 0.0.0.0 at the port specified by HEALTHCHECK_PORT
    environment variable (default: 8080). Responds with JSON health
    status at GET /health.
    """
    try:
        server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    except OSError:
        logger.error("Failed to bind port %d", PORT, exc_info=True)
        raise
    logger.info("Healthcheck server running on port %d", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Healthcheck server shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    start_server()
