#!/usr/bin/env python3
"""Conservative public listing watcher: no logins, no bypasses, never implies a reservation."""
import json
import os
import re
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
LISTINGS = ROOT / "data/listings.json"
SOURCES = ROOT / "data/sources.json"
UA = "DublinRoomRadar/1.0 (research; obeys robots.txt)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
# These are public discovery pages, not official APIs; coverage will be incomplete.
PAGES = [
    ("Rooms in Dublin", "https://roomsindublin.com/listings/?filter-title=March", "/listing/"),
    ("Daft Sharing", "https://www.daft.ie/sharing/dublin", "/share/"),
    ("Rent.ie", "https://www.rent.ie/rooms-to-rent/dublin/dublin/", "/rooms-to-rent/"),
    ("MyHome Share", "https://www.myhome.ie/rentals/dublin/share/shared-accommodation-in-dublin-county", "/rentals/brochure/"),
]
PRICE = re.compile(r"€\s*([\d,]+(?:\.\d+)?)\s*(?:/|per\s*)?(week|weekly|pw|month|monthly|pcm)", re.I)
DATE = re.compile(r"\b(?:(?:0?[1-9]|[12][0-9]|3[01])\s*(?:st|nd|rd|th)?\s*(?:of\s*)?March\s*[, ]+\s*2027|March\s+(?:0?[1-9]|[12][0-9]|3[01])\s*,?\s*2027|2027-03-(?:0[1-9]|[12][0-9]|3[01]))\b", re.I)
AREA = re.compile(r"\b(?:Dublin|D)\s*([1-9]|1[0-9]|2[024])\b", re.I)
PRIVATE = re.compile(r"\b(?:private room|single room|double room|ensuite|en-suite|habitación privada)\b", re.I)
SHARED = re.compile(r"\b(?:shared room|shared bedroom|bedspace|bed space|dormitory)\b", re.I)
DIRECT = ("direct bus to parnell", "direct bus to o'connell", "direct bus to city centre")
GREEN = ("luas green line", "green luas", "green line luas")
STREETS = ("parnell", "o'connell", "oconnell", "drumcondra", "ranelagh",
           "charlemont", "phibsborough", "phibsboro", "broadstone",
           "grangegorman", "dundrum", "broombridge", "harcourt")

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def allowed(session, url, robots_cache):
    root = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    if root not in robots_cache:
        response = session.get(root + "/robots.txt", timeout=15, headers=HEADERS)
        if response.status_code == 200:
            rp = RobotFileParser()
            rp.parse(response.text.splitlines())
            robots_cache[root] = rp
        elif response.status_code in (404, 410):
            robots_cache[root] = None
        else:
            raise RuntimeError(f"robots.txt HTTP {response.status_code}, skipped")
    rp = robots_cache[root]
    return rp is None or rp.can_fetch(UA, url)

def clean(s):
    return re.sub(r"\s+", " ", s).strip()

def score(text, price):
    t = text.lower().replace("’", "'")
    p = 20 if 600 <= price <= 1000 else (15 if price < 600 else max(0, 14 - (price - 1000) / 50))
    location = 18 if any(v in t for v in STREETS) else 0
    transit = 25 if any(v in t for v in GREEN) else 20 if any(v in t for v in DIRECT) else 7 if "luas" in t or "bus" in t else 0
    # Indicative signals; never assign actual travel time from district alone.
    return round(min(100, 28 + p + location + transit))

def transit_note(text):
    t = text.lower().replace("’", "'")
    if any(v in t for v in GREEN):
        return "Anuncio menciona Luas Green Line; parada y tiempo sin comprobar"
    if any(v in t for v in DIRECT):
        return "Anuncio menciona autobús directo; ruta y duración sin comprobar"
    if "luas" in t or "dart" in t or "bus" in t:
        return "Menciona transporte; enlace real con Parnell por confirmar"
    return "Conexión con Parnell/O'Connell por comprobar"

def extract(html, page, marker, source):
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    host = urlparse(page).netloc
    for anchor in soup.select("a[href]"):
        url = urljoin(page, anchor.get("href", ""))
        parsed = urlparse(url)
        if parsed.netloc != host or marker not in parsed.path:
            continue
        if source == "Rooms in Dublin":
            if not re.match(r"^/listing/[a-z0-9-]+/?$", parsed.path, re.I):
                continue
        elif not re.search(r"/\d{5,10}/?$", parsed.path):
            continue
        normalized = parsed.scheme + "://" + parsed.netloc + parsed.path.rstrip("/")
        # Smallest card ancestor that contains enough details.
        block = anchor
        context = clean(block.get_text(" ", strip=True))
        for _ in range(5):
            block = block.parent
            if block is None or not hasattr(block, "get_text"):
                break
            candidate = clean(block.get_text(" ", strip=True))
            if len(candidate) < 1600 and len(candidate) > 30 and ("€" in candidate):
                context = candidate
                if DATE.search(candidate):
                    break
        match = PRICE.search(context)
        if not match:
            continue  # No guessing
        euros = float(match.group(1).replace(",", ""))
        monthly = round(euros * 52 / 12 if match.group(2).lower() in ("week", "weekly", "pw") else euros, 2)
        if SHARED.search(context) and not PRIVATE.search(context):
            continue
        # Strict evidence: date must occur in same listing card, never full page.
        date_match = DATE.search(context)
        march = bool(date_match and re.search(r"\b(?:available|check.in|move.in|start|from|2027-03)\b", context, re.I))
        if date_match and not march:
            # Date without clear availability context is not proof.
            date_label = "Fecha por confirmar"
        else:
            date_label = date_match.group() if march else "Por confirmar"
        name = clean(anchor.get_text(" ", strip=True))[:145] or "Habitación: ver anuncio"
        area_match = AREA.search(context)
        district = "D" + area_match.group(1) if area_match else "Dublín (zona por confirmar)"
        ident = hashlib.sha256(normalized.encode()).hexdigest()[:16]
        found[ident] = {
            "id": ident, "title": name, "area": district,
            "source": source, "url": normalized, "price_monthly": monthly,
            "available": date_label,
            "march_status": "anunciado_marzo" if march else "por_confirmar",
            "room_type": "Habitación (confirmar uso exclusivo)",
            "transit_note": transit_note(context),
            "description": context[:500],
            "costs": "Gastos y depósito por confirmar", "fees": "Comisión por confirmar",
            "first_seen": now(), "last_seen": now(), "score": score(context, monthly),
        }
    return list(found.values())

def scan():
    session = requests.Session()
    robots_cache = {}
    previous = {str(r["id"]): r for r in load(LISTINGS, [])}
    state, candidates = [], []
    for name, page, marker in PAGES:
        report = dict(site=name, page=page, checked_at=now(), found=0, state="error", note="")
        try:
            if not allowed(session, page, robots_cache):
                report.update(state="no permitido", note="robots.txt no autoriza consulta")
            else:
                response = session.get(page, timeout=22, headers=HEADERS)
                if response.status_code in (403, 429):
                    report.update(state="bloqueado", note=f"HTTP {response.status_code}")
                elif response.status_code != 200:
                    report.update(state="error", note=f"HTTP {response.status_code}")
                else:
                    rows = extract(response.text, response.url, marker, name)
                    report.update(state="correcto" if rows else "sin resultados legibles", found=len(rows))
                    for item in rows:
                        prior = previous.get(item["id"])
                        if prior:
                            item["first_seen"] = prior.get("first_seen", item["first_seen"])
                            if prior.get("march_status") in ("anunciado_marzo", "aceptado_marzo") and item["march_status"] == "por_confirmar":
                                # Do not downgrade prior validated evidence on an abbreviated search card.
                                item = {**prior, "last_seen": now()}
                        elif item["march_status"] == "anunciado_marzo":
                            candidates.append(item)
                        if prior and prior.get("march_status") == "por_confirmar" and item["march_status"] == "anunciado_marzo":
                            candidates.append(item)
                        previous[item["id"]] = item
        except Exception as exc:
            report.update(state="error", note=f"{type(exc).__name__}: {str(exc)[:160]}")
        state.append(report)
        print(f"{name}: {report['state']} ({report['found']})", flush=True)
        time.sleep(1)
    save(LISTINGS, sorted(previous.values(), key=lambda x: (x.get("last_seen", ""), x.get("score", 0)), reverse=True)[:2000])
    save(SOURCES, {"last_checked": now(), "new_count": len(candidates), "sources": state,
        "important": "Solo un rastreo experimental: numerosos anuncios no son accesibles por automatización. Las fechas anunciadas NO son una reserva, y cada hallazgo debe reconfirmarse en la ficha."})
    if candidates:
        print("Nuevas fechas marzo 2027 (VERIFICAR ANTES DE CONTACTAR):")
        for c in candidates[:15]:
            print(f"- {c['title']} · {c['price_monthly']} €/mes · {c['url']}")
    return len(candidates)

if __name__ == "__main__":
    import sys
    if "--dry-run" in sys.argv:
        print(json.dumps({"configuration": load(ROOT / "config.json", {}), "known": len(load(LISTINGS, []))}, ensure_ascii=False, indent=2))
    else:
        print(f"Nuevos anuncios para reverificar: {scan()}")
