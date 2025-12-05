from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot Amazon attivo (Render FREE)")

if __name__ == "__main__":
    port = 10000
    server = HTTPServer(("", port), Handler)
    print(f"Server attivo su porta {port}")
    server.serve_forever()
