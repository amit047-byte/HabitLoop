#!/usr/bin/env python3
"""
HabitFlow × Ramp — Local Server with Sarvam AI OCR Integration
Serves the application at http://localhost:8080 and proxies Sarvam AI Document Intelligence API.
"""

import os
import sys
import json
import time
import ssl
import gzip
import base64
import uuid
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8080
DEFAULT_SARVAM_KEY = "sk_y6l3slkk_G9xv4vDO8QRMsghTbAe6e4HN"
ctx = ssl._create_unverified_context()

def call_sarvam_digitise(image_bytes, filename="timetable.jpg", api_key=DEFAULT_SARVAM_KEY):
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()
    
    # File part
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(image_bytes)
    body.extend(b"\r\n")
    
    # Language part
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="language"\r\n\r\n')
    body.extend(b"en-IN\r\n")
    
    # End boundary
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }
    
    req = urllib.request.Request("https://api.sarvam.ai/doc-ai/v1/job/digitise", data=bytes(body), headers=headers)
    with urllib.request.urlopen(req, context=ctx) as resp:
        start_res = json.loads(resp.read().decode("utf-8"))
        
    job_id = start_res["job_id"]
    
    # Poll status
    for _ in range(40):
        time.sleep(1)
        req_status = urllib.request.Request(
            f"https://api.sarvam.ai/doc-ai/v1/job/{job_id}/status",
            headers={"api-subscription-key": api_key}
        )
        with urllib.request.urlopen(req_status, context=ctx) as s_resp:
            status_data = json.loads(s_resp.read().decode("utf-8"))
            if status_data.get("status") == "completed":
                break
            elif status_data.get("status") in ["failed", "rejected"]:
                raise RuntimeError(f"Sarvam job failed: {status_data}")
                
    # Fetch results
    req_res = urllib.request.Request(
        f"https://api.sarvam.ai/doc-ai/v1/job/{job_id}/results",
        headers={"api-subscription-key": api_key}
    )
    with urllib.request.urlopen(req_res, context=ctx) as r_resp:
        decompressed = gzip.decompress(r_resp.read()).decode("utf-8")
        raw_json = json.loads(decompressed)
        
    # Extract table HTML and text blocks
    table_html = None
    all_blocks = []
    try:
        pages = raw_json.get("documents", [])[0].get("pages", [])
        for p in pages:
            for b in p.get("blocks", []):
                all_blocks.append({"tag": b.get("layout_tag"), "text": b.get("text", "")})
                if b.get("layout_tag") == "table" and not table_html:
                    table_html = b.get("text")
    except Exception as e:
        print("Block extraction notice:", e)
        
    return {
        "success": True,
        "job_id": job_id,
        "table_html": table_html,
        "blocks": all_blocks,
        "raw": raw_json
    }

class HabitFlowRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS for local development
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, api-subscription-key")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/sarvam/scan":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                post_data = self.rfile.read(content_len)
                payload = json.loads(post_data.decode("utf-8"))
                
                img_val = payload.get("image", "")
                image_bytes = None
                script_dir = os.path.dirname(os.path.abspath(__file__))
                local_candidate = os.path.join(script_dir, img_val) if img_val else ""
                
                if os.path.isfile(img_val):
                    with open(img_val, "rb") as f:
                        image_bytes = f.read()
                elif os.path.isfile(local_candidate):
                    with open(local_candidate, "rb") as f:
                        image_bytes = f.read()
                elif "," in img_val:
                    img_data_b64 = img_val.split(",", 1)[1]
                    image_bytes = base64.b64decode(img_data_b64)
                elif img_val:
                    try:
                        image_bytes = base64.b64decode(img_val)
                    except Exception:
                        pass
                        
                if not image_bytes:
                    raise ValueError("Could not load image bytes from payload.")
                    
                api_key = payload.get("apiKey") or DEFAULT_SARVAM_KEY
                
                result = call_sarvam_digitise(image_bytes, api_key=api_key)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        super().do_POST()

def run():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, HabitFlowRequestHandler)
    print(f"✨ HabitFlow × Ramp Server running at http://localhost:{PORT}")
    print(f"🔗 Sarvam AI OCR proxy active at http://localhost:{PORT}/api/sarvam/scan")
    httpd.serve_forever()

if __name__ == "__main__":
    run()
