"""Sonda Vamos Seminovos: como a lista completa (1.724 veículos) chega na página."""
import re
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9"}
s = requests.Session()
s.headers.update(UA)
p = s.get("https://vamos.com.br/seminovos", timeout=40).text
print("cards", p.count('data-mlc-est-card'), "cat", sorted(set(re.findall(r'data-categoria="([^"]+)"', p))))
a = p.find('<article class="est-card"')
print("ART:", p[a:a + 700])
for pat in [r'data-mlc-est-count[^>]*>[^<]*', r'data-mlc-est-more[^>]*', r'data-mlc-est-[a-z]*(?:page|more|load)[a-z-]*', r'supabase\.co/(?:rest|functions)/v1/[a-zA-Z0-9_/-]+', r'eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{10,}']:
    print(pat, sorted(set(re.findall(pat, p)))[:8])
for js in re.findall(r'src="(/_next/static/chunks/[^"]+\.js)"', p)[:40]:
    j = s.get("https://vamos.com.br" + js, timeout=40).text
    for pat in [r'supabase\.co/(?:rest|functions)/v1/[a-zA-Z0-9_/-]+', r'/rest/v1/[a-zA-Z0-9_]+', r'functions/v1/[a-zA-Z0-9_-]+', r'\.from\("([a-z_]+)"\)', r'/api/[a-zA-Z0-9/_-]+', r'mlc-est-[a-z]+']:
        f = sorted(set(re.findall(pat, j)))
        if f:
            print(js[-30:], pat, f[:15])
i = p.find('data-mlc-est-count')
print("COUNT ctx:", p[i - 300:i + 300])
k = p.rfind('</article>')
print("POS ULTIMO CARD:", k, "len", len(p), "fim:", re.sub(r"\s+", " ", p[k:k + 1500]))
