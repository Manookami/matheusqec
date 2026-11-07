"""Servidor de teste local do site (site/dist) sem cache: o navegador sempre mostra a versão mais nova.

Uso: python site/servir.py [porta]
"""
import functools
import http.server
import sys
from pathlib import Path

DIST = Path(__file__).resolve().parent / "dist"


class SemCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()


porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
http.server.ThreadingHTTPServer(("127.0.0.1", porta), functools.partial(SemCache, directory=str(DIST))).serve_forever()
