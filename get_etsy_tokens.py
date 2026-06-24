"""
Run this once to get your Etsy access_token and refresh_token.

Usage:
  python get_etsy_tokens.py

It will open your browser for you to authorize, then print the tokens.
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser

import httpx

# ── Paste your credentials here ──────────────────────────────────────────────
ETSY_API_KEY    = input("Paste your Etsy Keystring: ").strip()
ETSY_API_SECRET = input("Paste your Etsy Shared Secret: ").strip()
# ─────────────────────────────────────────────────────────────────────────────

REDIRECT_URI   = "http://localhost:8989/callback"
SCOPES         = "transactions_r transactions_w listings_r listings_w shops_r"
AUTH_URL       = "https://www.etsy.com/oauth/connect"
TOKEN_URL      = "https://api.etsy.com/v3/public/oauth/token"

# PKCE
code_verifier  = secrets.token_urlsafe(64)
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()
state          = secrets.token_hex(16)

auth_code_holder: dict = {}
server_ready     = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code_holder["code"]  = params.get("code",  [None])[0]
        auth_code_holder["state"] = params.get("state", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Authorization complete! You can close this tab.</h2>")
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *_):
        pass


def start_server():
    server = http.server.HTTPServer(("localhost", 8989), CallbackHandler)
    server_ready.set()
    server.serve_forever()


# Start local callback server
t = threading.Thread(target=start_server, daemon=True)
t.start()
server_ready.wait()

# Build authorization URL
params = {
    "response_type":         "code",
    "redirect_uri":          REDIRECT_URI,
    "scope":                 SCOPES,
    "client_id":             ETSY_API_KEY,
    "state":                 state,
    "code_challenge":        code_challenge,
    "code_challenge_method": "S256",
}
url = AUTH_URL + "?" + urllib.parse.urlencode(params)

print("\nOpening your browser for Etsy authorization...")
webbrowser.open(url)
print("If the browser didn't open, go to:\n", url)

# Wait for the callback
t.join()

code = auth_code_holder.get("code")
if not code:
    print("ERROR: No authorization code received.")
    exit(1)

# Exchange code for tokens
response = httpx.post(
    TOKEN_URL,
    data={
        "grant_type":     "authorization_code",
        "client_id":      ETSY_API_KEY,
        "redirect_uri":   REDIRECT_URI,
        "code":           code,
        "code_verifier":  code_verifier,
    },
)

if response.status_code != 200:
    print("ERROR:", response.text)
    exit(1)

tokens = response.json()

print("\n" + "="*60)
print("SUCCESS! Add these to your .env file:")
print("="*60)
print(f"ETSY_API_KEY={ETSY_API_KEY}")
print(f"ETSY_API_SECRET={ETSY_API_SECRET}")
print(f"ETSY_ACCESS_TOKEN={tokens['access_token']}")
print(f"ETSY_REFRESH_TOKEN={tokens['refresh_token']}")
print("="*60)
