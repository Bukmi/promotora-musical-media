#!/usr/bin/env python3
"""Publicador de Instagram para @promotora_musical (API de Instagram con inicio de sesión unificado, graph.facebook.com).

Credencial: lo ideal es un Network secret del entorno para graph.facebook.com
(cabecera Authorization: Bearer EAA...), así el script nunca toca el token.
Si existe la variable IG_ACCESS_TOKEN, la usa como respaldo. Nunca lo imprime.
Por defecto NO publica: crea el contenedor y comprueba que Instagram acepta el archivo.
Solo publica de verdad con --publicar.

Uso:
  publicar.py perfil
  publicar.py reel  --url URL_MP4 --texto "caption" [--portada URL_JPG] [--publicar]
  publicar.py imagen --url URL_JPG --texto "caption" [--publicar]
  publicar.py carrusel --url URL1 --url URL2 ... --texto "caption" [--publicar]
  publicar.py story --url URL_JPG_O_MP4 [--publicar]
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request, urllib.error

API = "https://graph.facebook.com/v24.0"
IG_ID = os.environ.get("IG_USER_ID", "17841480397302586")  # cuenta de Instagram @promotora_musical


def token():
    t = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not t:
        return None  # el token lo añade el proxy (Network secret en graph.facebook.com)
    if t.startswith("IG_ACCESS_TOKEN="):
        t = t.split("=", 1)[1].strip()
    t = t.strip("'\"").strip()
    return t


def call(method, path, **params):
    t = token()
    if t:
        params["access_token"] = t
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}" if not path.startswith("http") else path
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit(f"Error {e.code} de Instagram: {body}")


def me():
    r = call("GET", IG_ID, fields="id,username,media_count")
    r["user_id"] = r.get("id", IG_ID)
    return r


def esperar(cid, max_min=10):
    for _ in range(max_min * 6):
        st = call("GET", cid, fields="status_code,status")
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            sys.exit(f"Instagram rechazó el archivo: {st}")
        time.sleep(10)
    sys.exit("Instagram tardó demasiado en procesar el archivo.")


def es_video(u):
    return u.lower().split("?")[0].endswith((".mp4", ".mov"))


def contenedor(uid, tipo, args):
    p = {}
    if tipo == "reel":
        p = dict(media_type="REELS", video_url=args.url[0], caption=args.texto or "", share_to_feed="true")
        if args.portada:
            p["cover_url"] = args.portada
    elif tipo == "imagen":
        p = dict(image_url=args.url[0], caption=args.texto or "")
    elif tipo == "story":
        u = args.url[0]
        p = dict(media_type="STORIES", **({"video_url": u} if es_video(u) else {"image_url": u}))
    elif tipo == "carrusel":
        hijos = []
        for u in args.url:
            hp = dict(is_carousel_item="true", **({"media_type": "VIDEO", "video_url": u} if es_video(u) else {"image_url": u}))
            hid = call("POST", f"{uid}/media", **hp)["id"]
            esperar(hid)
            hijos.append(hid)
        p = dict(media_type="CAROUSEL", children=",".join(hijos), caption=args.texto or "")
    cid = call("POST", f"{uid}/media", **p)["id"]
    esperar(cid)
    return cid


BASE = "https://bukmi.github.io/promotora-musical-media/"


def hoy(a):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    fecha = a.fecha or datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d")
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "calendario.json")
    if os.path.exists(local):
        cal = json.load(open(local))
    else:
        with urllib.request.urlopen(BASE + "calendario.json", timeout=60) as r:
            cal = json.load(r)
    pieza = next((p for p in cal["piezas"] if p["fecha"] == fecha and p.get("franja", "manana") == a.franja), None)
    if not pieza:
        print(f"{fecha} ({a.franja}): no hay pieza en el calendario. No se publica nada.")
        return
    print(f"{fecha}: día {pieza['dia']}, {pieza['tipo']} ({pieza['pilar']}): {pieza['tema']}")
    if pieza.get("variantes"):
        v = next((v for v in pieza["variantes"] if v.get("nombre") == pieza.get("elegida")), None)
        if v:
            pieza = {**pieza, **{k: v[k] for k in ("archivos", "caption", "portada") if k in v}}
    if not pieza.get("aprobado"):
        print("NO APROBADA: Ramón no ha dado el OK a esta pieza. No se publica nada.")
        return
    if pieza.get("publicado"):
        print(f"YA PUBLICADA: {pieza['publicado']}. No se publica de nuevo.")
        return
    if not pieza.get("archivos"):
        print("PIEZA NO LISTA: no tiene archivos subidos. No se publica nada.")
        return
    urls = [cal.get("base_url", BASE) + f for f in pieza["archivos"]]
    tipo = {"reel": "reel", "carrusel": "carrusel", "stories": "story", "imagen": "imagen"}[pieza["tipo"]]
    if tipo == "carrusel" and len(urls) == 1:
        tipo = "imagen"
    lotes = [[u] for u in urls] if tipo == "story" else [urls]
    enlaces = []
    for lote in lotes:
        a.url, a.texto = lote, pieza.get("caption", "")
        a.portada = cal.get("base_url", BASE) + pieza["portada"] if pieza.get("portada") else None
        enlaces.append(publicar_uno(tipo, a))
    if a.publicar and os.path.exists(local):
        for p in cal["piezas"]:
            if p["fecha"] == fecha and p.get("franja", "manana") == a.franja:
                p["publicado"] = enlaces[0] if len(enlaces) == 1 else enlaces
        json.dump(cal, open(local, "w"), ensure_ascii=False, indent=1)


def auto(a):
    """Para GitHub Actions: decide la franja por la hora de Madrid (así no depende del horario de verano)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    h = datetime.now(ZoneInfo("Europe/Madrid")).hour
    a.franja = "manana" if h in (9, 10) else "tarde" if h in (17, 18) else None
    if not a.franja:
        print(f"Hora de Madrid {h}: fuera de las franjas. Nada que hacer.")
        return
    a.publicar = True
    hoy(a)


def publicar_uno(tipo, a):
    perfil = me()
    uid = perfil["user_id"]
    print(f"Cuenta: @{perfil.get('username')}")
    cid = contenedor(uid, tipo, a)
    if not a.publicar:
        print(f"Prueba correcta: Instagram aceptó el {tipo} (contenedor {cid}). No se ha publicado nada.")
        return
    r = call("POST", f"{uid}/media_publish", creation_id=cid)
    info = call("GET", r["id"], fields="permalink")
    print(f"Publicado: {info.get('permalink')}")
    return info.get("permalink")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["perfil", "refrescar-token", "reel", "imagen", "carrusel", "story", "hoy", "auto"])
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--texto")
    ap.add_argument("--portada")
    ap.add_argument("--publicar", action="store_true")
    ap.add_argument("--fecha", help="AAAA-MM-DD; por defecto hoy en Madrid")
    ap.add_argument("--franja", choices=["manana", "tarde"], default="manana", help="hueco del día: manana (~10:00) o tarde (~18:00)")
    a = ap.parse_args()

    if a.accion == "perfil":
        print(json.dumps(me(), ensure_ascii=False, indent=2))
        return
    if a.accion == "refrescar-token":
        sys.exit("Con el inicio de sesión unificado no se usa ig_refresh_token. Renueva el token desde la app de Meta.")
    if a.accion == "hoy":
        return hoy(a)
    if a.accion == "auto":
        return auto(a)
    if not a.url:
        sys.exit("Falta --url.")
    publicar_uno(a.accion, a)


if __name__ == "__main__":
    main()
