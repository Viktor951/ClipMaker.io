import os
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

canary_hits = []

class CanaryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        canary_hits.append({
            "path": self.path,
            "headers": dict(self.headers),
            "time": time.time()
        })
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"CANARY_OK")

    def do_HEAD(self):
        canary_hits.append({
            "path": self.path,
            "headers": dict(self.headers),
            "time": time.time()
        })
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Silencia logs padrao no stdout
        pass

def start_canary_server(port=8888):
    server = HTTPServer(("127.0.0.1", port), CanaryHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
