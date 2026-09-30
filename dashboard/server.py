"""
Dashboard de cotações B3 em tempo real
--------------------------------------
Servidor local que busca as cotações no Yahoo Finance (endpoint público de
gráfico, sem chave de API) e serve um painel no navegador, no estilo do card
de ação do Google.

Uso:
  pip install -r requirements.txt
  python dashboard/server.py            # abre em http://localhost:8000
  python dashboard/server.py --port 9000
  python dashboard/server.py --demo     # dados simulados (sem internet)

Obs.: a B3 via Yahoo tem atraso de ~15 min em relação ao pregão.
"""

import argparse
import json
import math
import random
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

TICKERS = [
    "MOVI3", "SIMH3", "VAMO3", "JSLG3", "AMOB3", "RAPT3",
    "RAPT4", "RENT3", "FRAS3", "ARML3", "MILL3", "PRNR3",
]

# range -> intervalo de candle aceito pelo Yahoo
RANGES = {
    "1d": "5m",
    "5d": "15m",
    "1mo": "30m",
    "6mo": "1d",
    "ytd": "1d",
    "1y": "1d",
    "5y": "1wk",
}

HERE = Path(__file__).parent
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
YAHOO_HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]

_session = requests.Session()
_session.headers.update(HEADERS)
_cache = {}
_cache_lock = threading.Lock()
DEMO = False


def cached(key, ttl, fn):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def fetch_chart(ticker, rng):
    """Busca o gráfico de um ticker e devolve {meta, points}."""
    if DEMO:
        return demo_chart(ticker, rng)
    params = {"range": rng, "interval": RANGES[rng], "includePrePost": "false"}
    last_err = None
    for host in YAHOO_HOSTS:
        url = f"https://{host}/v8/finance/chart/{ticker}.SA"
        try:
            r = _session.get(url, params=params, timeout=10)
            r.raise_for_status()
            result = r.json()["chart"]["result"][0]
            break
        except Exception as e:  # tenta o próximo host
            last_err = e
    else:
        raise RuntimeError(f"{ticker}: {last_err}")

    meta = result.get("meta", {})
    q = (result.get("indicators", {}).get("quote") or [{}])[0]
    ts = result.get("timestamp") or []
    closes = q.get("close") or []
    points = [[t, round(c, 4)] for t, c in zip(ts, closes) if c is not None]

    opens = [o for o in (q.get("open") or []) if o is not None]
    highs = [h for h in (q.get("high") or []) if h is not None]
    lows = [l for l in (q.get("low") or []) if l is not None]
    vols = [v for v in (q.get("volume") or []) if v is not None]

    price = meta.get("regularMarketPrice") or (points[-1][1] if points else None)
    prev = meta.get("chartPreviousClose") if rng != "1d" else (
        meta.get("previousClose") or meta.get("chartPreviousClose")
    )
    return {
        "symbol": ticker,
        "name": meta.get("longName") or meta.get("shortName") or ticker,
        "currency": meta.get("currency", "BRL"),
        "price": price,
        "previousClose": prev,
        "open": opens[0] if opens else None,
        "dayHigh": meta.get("regularMarketDayHigh") or (max(highs) if highs else None),
        "dayLow": meta.get("regularMarketDayLow") or (min(lows) if lows else None),
        "volume": meta.get("regularMarketVolume") or (sum(vols) if vols else None),
        "high52": meta.get("fiftyTwoWeekHigh"),
        "low52": meta.get("fiftyTwoWeekLow"),
        "marketTime": meta.get("regularMarketTime"),
        "range": rng,
        "points": points,
    }


def get_chart(ticker, rng):
    ttl = 20 if rng == "1d" else 120
    return cached((ticker, rng), ttl, lambda: fetch_chart(ticker, rng))


def get_all_quotes():
    def one(t):
        try:
            return get_chart(t, "1d")
        except Exception as e:
            return {"symbol": t, "error": str(e)}

    with ThreadPoolExecutor(max_workers=len(TICKERS)) as ex:
        return list(ex.map(one, TICKERS))


# ---------------------------------------------------------------- modo demo
DEMO_BASE = {
    "MOVI3": 7.8, "SIMH3": 6.2, "VAMO3": 4.9, "JSLG3": 8.4, "AMOB3": 2.1,
    "RAPT3": 7.1, "RAPT4": 7.6, "RENT3": 44.3, "FRAS3": 21.5,
    "ARML3": 5.3, "MILL3": 9.7, "PRNR3": 13.2,
}


def demo_chart(ticker, rng):
    rnd = random.Random(f"{ticker}-{rng}-{int(time.time() // 30)}")
    base = DEMO_BASE[ticker]
    n = {"1d": 84, "5d": 140, "1mo": 300, "6mo": 125, "ytd": 185, "1y": 250, "5y": 260}[rng]
    step = {"1d": 300, "5d": 900, "1mo": 1800, "6mo": 86400, "ytd": 86400,
            "1y": 86400, "5y": 604800}[rng]
    vol = 0.004 if rng in ("1d", "5d") else 0.018
    end = int(time.time())
    p = base
    pts = []
    for i in range(n):
        p *= 1 + rnd.gauss(0, vol) + 0.0003 * math.sin(i / 9)
        pts.append([end - (n - i) * step, round(p, 2)])
    prev = round(base * (1 + rnd.uniform(-0.02, 0.02)), 2) if rng == "1d" else pts[0][1]
    closes = [c for _, c in pts]
    return {
        "symbol": ticker, "name": f"{ticker} (dados simulados)", "currency": "BRL",
        "price": pts[-1][1], "previousClose": prev, "open": pts[0][1],
        "dayHigh": max(closes), "dayLow": min(closes),
        "volume": rnd.randint(800_000, 12_000_000),
        "high52": round(base * 1.35, 2), "low52": round(base * 0.7, 2),
        "marketTime": end, "range": rng, "points": pts, "demo": True,
    }


# ---------------------------------------------------------------- HTTP
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/quotes":
            return self.send_json({"demo": DEMO, "serverTime": time.time(),
                                   "quotes": get_all_quotes()})
        if url.path == "/api/chart":
            qs = parse_qs(url.query)
            t = qs.get("symbol", [""])[0].upper()
            rng = qs.get("range", ["1d"])[0]
            if t not in TICKERS or rng not in RANGES:
                return self.send_json({"error": "ticker ou período inválido"}, 400)
            try:
                return self.send_json(get_chart(t, rng))
            except Exception as e:
                return self.send_json({"symbol": t, "error": str(e)}, 502)
        if url.path == "/":
            self.path = "/index.html"
        return super().do_GET()


def main():
    global DEMO
    ap = argparse.ArgumentParser(description="Dashboard de cotações B3")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--demo", action="store_true", help="usa dados simulados")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    DEMO = args.demo

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"Dashboard rodando em {url}{'  [DEMO]' if DEMO else ''}  (Ctrl+C para sair)")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
        sys.exit(0)


if __name__ == "__main__":
    main()
