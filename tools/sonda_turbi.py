"""Sonda temporária: Open-Meteo histórico (ERA5) e sazonal (ECMWF SEAS5)."""
import json
import requests

r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={"latitude": "-22.78,-12.7", "longitude": "-43.3,-38.3",
                 "start_date": "2015-01-01", "end_date": "2026-11-10", "daily": "precipitation_sum", "timezone": "America/Sao_Paulo"}, timeout=120)
print("ARCHIVE", r.status_code, len(r.content), r.text[:300])
try:
    js = r.json(); js = js if isinstance(js, list) else [js]
    t = js[0]["daily"]["time"]; v = js[0]["daily"]["precipitation_sum"]; print("ARCH last", t[-8:], v[-8:])
except Exception as e:
    print("ARCH parse", e)
for params in [{"daily": "precipitation_sum", "forecast_days": 183}, {"monthly": "precipitation_sum"}, {"monthly": "precipitation_mean,precipitation_anomaly"}]:
    r = requests.get("https://seasonal-api.open-meteo.com/v1/seasonal", params={"latitude": "-22.78,-12.7", "longitude": "-43.3,-38.3", "timezone": "America/Sao_Paulo", **params}, timeout=120)
    print("SEASONAL", params, r.status_code, len(r.content), r.text[:1500])
r = requests.get("https://climate-api.open-meteo.com/v1/climate", params={"latitude": "-22.78", "longitude": "-43.3", "start_date": "2026-11-01", "end_date": "2027-04-30", "models": "EC_Earth3P_HR", "daily": "precipitation_sum"}, timeout=120)
print("CLIMATE", r.status_code, r.text[:200])
