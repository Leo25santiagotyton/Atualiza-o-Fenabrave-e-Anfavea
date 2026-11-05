"""Sonda da vitrine pública de seminovos da Turbi (seminovos.turbi.com.br): estrutura da lista."""
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
s = requests.Session()
s.headers.update(UA)
r = s.get("https://seminovos.turbi.com.br/seminovos", timeout=30)
t = r.text
print("len", len(t))
for pat in [r"__remixContext", r"self\.__next_f", r"application/json", r"__sveltekit", r"astro-island", r"window\.__[A-Z_]+", r"data-props", r"page=\d+", r"pagina", r"total", r"resultados", r"veículos encontrados", r"carros encontrados"]:
    ms = [m.start() for m in re.finditer(pat, t, re.I)]
    print(f"{pat}: {len(ms)}", repr(t[ms[0]-150:ms[0]+250]) if ms else "")
i = t.find("70.990")
print("\nCARD:\n", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", t[i-2500:i+800]))[:2500])
for m in sorted(set(re.findall(r'https?://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._-]+){0,5}', t)))[:60]:
    print("url:", m)
for js in re.findall(r'src="([^"]+\.js)"', t)[:20]:
    u = requests.compat.urljoin(r.url, js)
    try:
        j = s.get(u, timeout=30).text
    except Exception:
        continue
    for m in sorted(set(re.findall(r'["\'](/api/[^"\']+|https?://[a-zA-Z0-9.-]*api[a-zA-Z0-9./_-]*)["\']', j)))[:20]:
        print("js", js[-40:], m)
for q in ["?page=2", "?pagina=2", "?p=2"]:
    r2 = s.get("https://seminovos.turbi.com.br/seminovos" + q, timeout=30)
    ids = re.findall(r'/seminovos/([0-9a-f-]{36})', r2.text)
    print(q, r2.status_code, len(set(ids)), list(dict.fromkeys(ids))[:3])
print("ids pag1", len(set(re.findall(r'/seminovos/([0-9a-f-]{36})', t))), list(dict.fromkeys(re.findall(r'/seminovos/([0-9a-f-]{36})', t)))[:3])
