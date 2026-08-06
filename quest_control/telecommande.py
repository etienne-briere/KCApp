# -*- coding: utf-8 -*-
"""
Télécommande du casque, depuis un téléphone ou une tablette.

Le pilotage ADB tourne sur le poste de l'investigateur — c'est lui qui parle au
casque. Ce module lui ajoute une petite page web, pensée pour un écran tactile,
que l'on ouvre depuis n'importe quel appareil du même réseau. Aucune
installation côté téléphone : c'est une page, pas une application.

    python quest_control/telecommande.py

**Pourquoi pas une application Android ?** Elle devrait embarquer un client ADB
complet — authentification RSA, protocole binaire, gestion des transports — et
le casque devrait avoir été appairé au préalable par câble de toute façon. À
supposer ce travail fait, il faudrait encore la distribuer, la maintenir et la
faire vivre en parallèle du script Python. Une page web servie par le poste qui
tient déjà la connexion ADB donne le même résultat en quelques centaines de
lignes, et reste utilisable depuis n'importe quel appareil, y compris la
tablette de recueil déjà présente dans la chambre.

Le poste doit rester allumé et connecté au casque : c'est lui qui exécute tout.
Le téléphone n'est qu'un jeu de boutons.
"""

from __future__ import annotations

import argparse
import json
import secrets
import socket
import socketserver
import sys
import threading
import http.server
import webbrowser
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
sys.path.insert(0, str(ICI.parent / "shared"))

from console import configurer_console  # noqa: E402
from quest import ErreurAdb, Quest  # noqa: E402

configurer_console()

VERT, GRIS, JAUNE, ROUGE, RAZ = ("\033[32m", "\033[90m", "\033[33m",
                                 "\033[31m", "\033[0m")

#: Jeton de session, régénéré à chaque démarrage. Sur un réseau hospitalier
#: partagé, une page qui pilote un appareil ne doit pas être atteignable par
#: simple balayage de ports. Ce n'est pas de la sécurité forte — c'est la
#: précaution minimale pour un outil qui ne quitte pas le service.
JETON = secrets.token_urlsafe(8)


PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1f5f8b">
<title>Casque APEX</title>
<style>
  :root {
    --bg:#f4f6f9; --surface:#fff; --border:#dfe4ec; --text:#16202e;
    --muted:#64748b; --primary:#1f5f8b; --ok:#15803d; --ok-soft:#dcfce7;
    --warn:#b45309; --warn-soft:#fef3c7; --danger:#b91c1c; --danger-soft:#fee2e2;
  }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body {
    margin:0; padding:16px 16px 40px;
    font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    background:var(--bg); color:var(--text);
  }
  h1 { font-size:1.25rem; margin:4px 0 2px; }
  .sous { color:var(--muted); font-size:.85rem; margin:0 0 18px; }
  .carte {
    background:var(--surface); border:1px solid var(--border);
    border-radius:14px; padding:14px; margin-bottom:14px;
  }
  .etat { display:grid; grid-template-columns:1fr auto; gap:8px 12px; font-size:.9rem; }
  .etat dt { color:var(--muted); }
  .etat dd { margin:0; text-align:right; font-weight:600; }
  .pastille { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.8rem; }
  .p-ok { background:var(--ok-soft); color:var(--ok); }
  .p-warn { background:var(--warn-soft); color:var(--warn); }
  .p-off { background:var(--danger-soft); color:var(--danger); }
  button {
    display:block; width:100%; min-height:64px; margin-bottom:10px;
    font:inherit; font-weight:600; border-radius:14px; cursor:pointer;
    border:1px solid var(--border); background:var(--surface); color:var(--text);
  }
  button:active { transform:scale(.99); }
  button[disabled] { opacity:.5; }
  .principal {
    background:var(--primary); border-color:var(--primary); color:#fff;
    min-height:84px; font-size:1.1rem;
  }
  .danger { color:var(--danger); }
  .note { color:var(--muted); font-size:.8rem; margin:-4px 0 14px; }
  #journal { font-size:.85rem; white-space:pre-wrap; }
  #journal .l-ok { color:var(--ok); }
  #journal .l-err { color:var(--danger); }
  .charge { opacity:.6; pointer-events:none; }
</style>
</head>
<body>

<h1>Casque APEX</h1>
<p class="sous">Le poste investigateur pilote, ce téléphone commande.</p>

<div class="carte">
  <dl class="etat" id="etat">
    <dt>Connexion</dt><dd id="e-connexion">…</dd>
    <dt>Batterie</dt><dd id="e-batterie">…</dd>
    <dt>Application au premier plan</dt><dd id="e-app">…</dd>
    <dt>Limite de jeu</dt><dd id="e-limite">…</dd>
  </dl>
</div>

<button class="principal" data-action="preparer">
  Préparer la séance
</button>
<p class="note">
  Réveille le casque, neutralise le capteur de proximité et la veille,
  désactive la limite de jeu, puis lance APEX. Casque posé sur la table.
</p>

<div class="carte">
  <button data-action="limite_desactiver">Désactiver la limite de jeu</button>
  <button data-action="limite_activer">Rétablir la limite de jeu</button>
  <button data-action="lancer">Lancer le jeu seulement</button>
  <button data-action="arreter" class="danger">Arrêter le jeu</button>
  <button data-action="etat">Rafraîchir l'état</button>
</div>

<div class="carte">
  <div id="journal">Prêt.</div>
</div>

<script>
const JETON = new URLSearchParams(location.search).get("jeton") || "";

function journal(texte, classe) {
  const el = document.getElementById("journal");
  const ligne = document.createElement("div");
  if (classe) ligne.className = classe;
  const t = new Date().toLocaleTimeString("fr-FR");
  ligne.textContent = t + "  " + texte;
  el.insertBefore(ligne, el.firstChild);
  while (el.childNodes.length > 40) el.removeChild(el.lastChild);
}

function pastille(texte, classe) {
  return '<span class="pastille ' + classe + '">' + texte + "</span>";
}

function afficherEtat(e) {
  document.getElementById("e-connexion").innerHTML = e.connecte
    ? pastille(e.modele || "connecté", "p-ok")
    : pastille("absent", "p-off");
  document.getElementById("e-batterie").textContent =
    e.batterie === null || e.batterie === undefined ? "—" : e.batterie + " %";
  document.getElementById("e-app").textContent = e.application || "—";
  const l = e.limite;
  document.getElementById("e-limite").innerHTML = l === null || l === undefined
    ? "—"
    : (l ? pastille("active", "p-warn") : pastille("désactivée", "p-ok"));
}

let occupe = false;

function appeler(action) {
  if (occupe) return;
  occupe = true;
  document.body.classList.add("charge");
  journal("→ " + action + "…");

  fetch("/action?jeton=" + encodeURIComponent(JETON) + "&nom=" +
        encodeURIComponent(action), { method: "POST" })
    .then((r) => r.json())
    .then((r) => {
      (r.messages || []).forEach((m) => journal("   " + m, r.ok ? "l-ok" : "l-err"));
      journal(r.ok ? "✓ " + action : "✗ " + action + " — " + (r.erreur || ""),
              r.ok ? "l-ok" : "l-err");
      if (r.etat) afficherEtat(r.etat);
    })
    .catch((e) => journal("✗ poste injoignable : " + e.message, "l-err"))
    .finally(() => {
      occupe = false;
      document.body.classList.remove("charge");
    });
}

document.querySelectorAll("[data-action]").forEach((b) => {
  b.addEventListener("click", () => appeler(b.getAttribute("data-action")));
});

appeler("etat");
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def lire_etat(quest: Quest) -> Dict[str, Any]:
    """
    État du casque, sans jamais lever.

    Cette fonction alimente un bandeau consulté en continu depuis la chambre :
    une exception y afficherait un écran vide au lieu d'une information
    partielle. Un champ inconnu vaut mieux qu'une page morte.
    """
    etat: Dict[str, Any] = {"connecte": False, "batterie": None,
                            "modele": "", "application": "", "limite": None}
    try:
        etat["connecte"] = quest.connecte()
    except ErreurAdb:
        return etat
    if not etat["connecte"]:
        return etat

    for cle, action in (("batterie", quest.batterie),
                        ("modele", quest.modele),
                        ("application", quest.application_active)):
        try:
            etat[cle] = action()
        except Exception:                                     # noqa: BLE001
            pass
    try:
        etat["limite"] = quest.limite_etat()["active"]
    except Exception:                                         # noqa: BLE001
        pass
    return etat


def action_preparer(quest: Quest) -> list:
    """Enchaînement complet avant de tendre le casque."""
    messages = []
    etapes = [
        ("Réveil", lambda: quest.reveiller()),
        ("Capteur de proximité neutralisé", lambda: quest.simuler_port(True)),
        ("Veille automatique neutralisée", lambda: quest.maintenir_eveille(True)),
        ("Limite de jeu désactivée", lambda: quest.limite_definir(False)),
        ("Jeu lancé", lambda: quest.lancer()),
    ]
    echecs = []
    for libelle, action in etapes:
        try:
            action()
            messages.append(f"OK — {libelle}")
        except Exception as exc:                              # noqa: BLE001
            premiere = str(exc).splitlines()[0]
            messages.append(f"ÉCHEC — {libelle} : {premiere}")
            echecs.append(libelle)

    # Une étape ratée n'annule pas les autres : mieux vaut un casque
    # partiellement préparé et un message clair qu'un arrêt au premier
    # obstacle, avec un participant qui attend.
    if echecs:
        raise ErreurAdb(f"{len(echecs)} étape(s) en échec : " + ", ".join(echecs))
    return messages


ACTIONS = {
    "etat": lambda q: [],
    "preparer": action_preparer,
    "limite_desactiver": lambda q: q.limite_definir(False)["journal"],
    "limite_activer": lambda q: q.limite_definir(True)["journal"],
    "lancer": lambda q: [f"Application lancée : {q.lancer()}"],
    "arreter": lambda q: [f"Application arrêtée : {q.arreter()}"],
}


# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):

    quest: Quest = None          # type: ignore[assignment]
    verrou = threading.Lock()

    def _repondre(self, code: int, corps: bytes, mime: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def _json(self, code: int, donnees: dict) -> None:
        self._repondre(code, json.dumps(donnees, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

    def _jeton_valide(self, requete) -> bool:
        fourni = parse_qs(requete.query).get("jeton", [""])[0]
        # Comparaison à temps constant : sans intérêt vital ici, mais c'est
        # l'usage et cela ne coûte rien.
        return secrets.compare_digest(fourni, JETON)

    def do_GET(self):
        requete = urlparse(self.path)
        if requete.path in ("/", "/index.html"):
            if not self._jeton_valide(requete):
                self._repondre(403, "Lien invalide ou expiré. Relancez la "
                                    "télécommande sur le poste.".encode("utf-8"),
                               "text/plain; charset=utf-8")
                return
            self._repondre(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        self._repondre(404, b"", "text/plain")

    def do_POST(self):
        requete = urlparse(self.path)
        if requete.path != "/action":
            self._repondre(404, b"", "text/plain")
            return
        if not self._jeton_valide(requete):
            self._json(403, {"ok": False, "erreur": "jeton invalide"})
            return

        nom = parse_qs(requete.query).get("nom", [""])[0]
        action = ACTIONS.get(nom)
        if action is None:
            self._json(400, {"ok": False, "erreur": f"action inconnue : {nom}"})
            return

        # Une seule commande ADB à la fois : deux actions simultanées sur le
        # même casque produiraient des résultats incohérents, et l'interface
        # tactile invite aux appuis répétés.
        with self.verrou:
            try:
                messages = action(self.quest)
                self._json(200, {"ok": True, "messages": messages,
                                 "etat": lire_etat(self.quest)})
            except Exception as exc:                          # noqa: BLE001
                self._json(200, {"ok": False, "erreur": str(exc).splitlines()[0],
                                 "messages": getattr(exc, "messages", []),
                                 "etat": lire_etat(self.quest)})

    def log_message(self, format, *args):
        pass    # le journal utile est celui de la page, pas celui du serveur


def adresse_locale() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Serveur(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--local", action="store_true",
                        help="n'écouter que sur ce poste (pas de téléphone)")
    parser.add_argument("--simulateur", action="store_true",
                        help="casque simulé, pour parcourir l'interface sans "
                             "matériel")
    parser.add_argument("--scenario", default="normal", metavar="NOM",
                        help="comportement du casque simulé : normal, absent, "
                             "jeu_absent, lancement_echoue…")
    args = parser.parse_args()

    if args.simulateur:
        from quest import activer_simulateur
        Handler.quest = activer_simulateur(args.scenario)
    else:
        Handler.quest = Quest()

    hote = "127.0.0.1" if args.local else "0.0.0.0"
    try:
        serveur = Serveur((hote, args.port), Handler)
    except OSError as exc:
        print(f"Impossible d'écouter sur le port {args.port} : {exc}")
        print("Essayez un autre port :  --port 8091")
        return 1

    ip = "127.0.0.1" if args.local else adresse_locale()
    url = f"http://{ip}:{args.port}/?jeton={JETON}"

    print("=" * 66)
    print("  Télécommande du casque APEX")
    print("=" * 66)
    print(f"\n  {VERT}Ouvrez cette adresse sur votre téléphone :{RAZ}")
    print(f"\n      {url}\n")
    print(f"  {GRIS}Le téléphone doit être sur le même réseau que ce poste.{RAZ}")
    print(f"  {GRIS}Le poste garde la connexion au casque : ne le fermez pas.{RAZ}")
    print(f"  {GRIS}Le lien change à chaque démarrage.{RAZ}\n")

    if args.simulateur:
        print(f"  {JAUNE}Mode simulateur ({args.scenario}) — aucun casque "
              f"réel n'est piloté.{RAZ}")
        print(f"  {GRIS}Les boutons répondent, l'état évolue, mais rien ne "
              f"sort du poste.{RAZ}\n")

    etat = lire_etat(Handler.quest)
    if etat["connecte"]:
        print(f"  Casque : {VERT}{etat['modele'] or 'connecté'}{RAZ}"
              + (f" · batterie {etat['batterie']} %" if etat["batterie"] else ""))
    else:
        print(f"  Casque : {JAUNE}non détecté{RAZ} — branchez-le en USB, ou "
              f"lancez d'abord")
        print(f"  {GRIS}python quest_control/quest.py connecter --ip <adresse>{RAZ}")

    print(f"\n  {GRIS}Ctrl+C pour arrêter.{RAZ}")
    print("=" * 66 + "\n")

    if args.local:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêté.")
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
