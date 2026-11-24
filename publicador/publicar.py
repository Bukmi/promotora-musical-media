#!/usr/bin/env python3
"""Publicador de Instagram para @promotora_musical (API de Instagram con inicio de sesión de Instagram).

Lee el token de la variable de entorno IG_ACCESS_TOKEN. Nunca lo imprime.
Por defecto NO publica: crea el contenedor y comprueba que Instagram acepta el archivo.
Solo publica de verdad con --publicar.

Uso:
  publicar.py perfil
  publicar.py refrescar-token            (muestra solo la nueva caducidad; el token nuevo hay que guardarlo a mano)
  publicar.py reel  --url URL_MP4 --texto "caption" [--portada URL_JPG] [--publicar]
  publicar.py imagen --url URL_JPG --texto "caption" [--publicar]
  publicar.py carrusel --url URL1 --url URL2 ... --texto "caption" [--publicar]
  publicar.py story --url URL_JPG_O_MP4 [--publicar]
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request, urllib.error

API = "https://graph.instagram.com/v21.0"


def token():
    t = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not t:
        sys.exit("Falta la variable de entorno IG_ACCESS_TOKEN.")
    return t


def call(method, path, **params):
    params["access_token"] = token()
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
    return call("GET", "me", fields="user_id,username,account_type,media_count")


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["perfil", "refrescar-token", "reel", "imagen", "carrusel", "story"])
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--texto")
    ap.add_argument("--portada")
    ap.add_argument("--publicar", action="store_true")
    a = ap.parse_args()

    if a.accion == "perfil":
        print(json.dumps(me(), ensure_ascii=False, indent=2))
        return
    if a.accion == "refrescar-token":
        r = call("GET", "https://graph.instagram.com/refresh_access_token", grant_type="ig_refresh_token")
        print(f"Token renovado. Caduca en {r.get('expires_in', 0) // 86400} días. Guarda el nuevo token en IG_ACCESS_TOKEN.")
        return
    if not a.url:
        sys.exit("Falta --url.")
    perfil = me()
    uid = perfil["user_id"]
    print(f"Cuenta: @{perfil.get('username')}")
    cid = contenedor(uid, a.accion, a)
    if not a.publicar:
        print(f"Prueba correcta: Instagram aceptó el {a.accion} (contenedor {cid}). No se ha publicado nada.")
        return
    r = call("POST", f"{uid}/media_publish", creation_id=cid)
    info = call("GET", r["id"], fields="permalink")
    print(f"Publicado: {info.get('permalink')}")


if __name__ == "__main__":
    main()
