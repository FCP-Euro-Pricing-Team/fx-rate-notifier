"""Simple healthcheck endpoint for Cloud Run container."""
import os
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

logger = logging.getLogger(__name__)

PORT = int(os.getenv("HEALTHCHECK_PORT", 8080))
VERSION = "0.1.0"


class HealthHandler(BaseHTTPRequestHandler):
    """Handles GET /health requests."""

    def do_GET(self):
        if self.path == "/health":
            response = {
                "status": "ok",
                "version": VERSION,
                "timestamp": str(datetime.now()),
                "environment": os.getenv("ENVIRONMENT", "development"),
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        logger.info(format, *args)


def start_server():
    """Start the healthcheck HTTP server."""
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Healthcheck server running on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    start_server()
