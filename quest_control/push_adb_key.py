#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pousse la clé ADB du poste (~/.android/adbkey [.pub]) vers le dossier privé
de l'application KCApp sur une tablette Android, pour que `QuestClient`
(voir `app/network/quest_client.py`, `_chemin_cle_par_defaut()`) trouve la
même clé que celle déjà autorisée par le casque.

Pourquoi cette manip existe : le casque n'autorise pas un appareil, il
autorise une clé cryptographique. La tablette doit donc utiliser la même
clé que le poste (déjà autorisée) pour se connecter au casque sans qu'il
faille remettre le casque et valider manuellement une demande
d'autorisation à chaque fois.

Le dossier de destination est privé à l'application (`app_storage_path()`
côté Android) : un `adb push` direct échoue par manque de permission. La
solution en deux temps, reprise ici :

  1. `adb push` vers /sdcard/ (zone publique, accessible en écriture)
  2. `adb shell run-as <package> cp ...` pour copier depuis /sdcard/ vers le
     dossier privé de l'application, avec les droits de l'application
     elle-même.

À refaire à chaque nouvelle tablette, réinstallation de l'application, ou
effacement des données de l'application — voir la page Notion "Conditions
pour la préparation du casque VR" pour le détail.

Utilisation :

    python quest_control/push_adb_key.py
    python quest_control/push_adb_key.py --package org.m2sapex.apex_manips
    python quest_control/push_adb_key.py --cle ~/.android/adbkey --serial ABC123
    python quest_control/push_adb_key.py --chemin-distant /data/user/0/<package>/files/adbkey

Prérequis :
  - `adb` accessible dans le PATH (ou --adb pour préciser le chemin complet)
  - Une tablette connectée en USB (ou déjà en ADB over Wi-Fi) et autorisée
    (`adb devices` doit l'afficher en état "device", pas "unauthorized")
  - L'application KCApp déjà installée sur la tablette (le dossier privé
    n'existe qu'après le premier lancement)
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

PACKAGE_PAR_DEFAUT = "org.m2sapex.apex_manips"
NOM_FICHIER_CLE_PRIVEE = "adbkey"
NOM_FICHIER_CLE_PUBLIQUE = "adbkey.pub"


class ErreurPoussage(Exception):
    """Erreur lors du dépôt de la clé sur la tablette."""


def executer_adb(args_adb, *, serial: str | None, adb: str, verbeux: bool = True) -> str:
    """Exécute une commande adb et renvoie sa sortie standard (levée si échec)."""
    commande = [adb]
    if serial:
        commande += ["-s", serial]
    commande += args_adb

    if verbeux:
        print(f"  $ {' '.join(shlex.quote(c) for c in commande)}")

    resultat = subprocess.run(commande, capture_output=True, text=True)
    if resultat.returncode != 0:
        raise ErreurPoussage(
            f"Échec de la commande adb : {' '.join(commande)}\n"
            f"stdout: {resultat.stdout.strip()}\n"
            f"stderr: {resultat.stderr.strip()}"
        )
    return resultat.stdout.strip()


def verifier_appareil(serial: str | None, adb: str) -> None:
    """Vérifie qu'une tablette est bien connectée et autorisée."""
    sortie = executer_adb(["devices"], serial=None, adb=adb, verbeux=False)
    lignes = [l for l in sortie.splitlines()[1:] if l.strip()]

    if not lignes:
        raise ErreurPoussage(
            "Aucun appareil détecté par adb. Branchez la tablette en USB, "
            "autorisez le débogage si demandé, puis relancez."
        )

    if serial:
        correspondances = [l for l in lignes if l.split()[0] == serial]
        if not correspondances:
            raise ErreurPoussage(f"Aucun appareil avec le numéro de série {serial!r}.")
        ligne = correspondances[0]
    else:
        if len(lignes) > 1:
            noms = ", ".join(l.split()[0] for l in lignes)
            raise ErreurPoussage(
                f"Plusieurs appareils connectés ({noms}) — précisez "
                f"--serial pour choisir la tablette cible."
            )
        ligne = lignes[0]

    etat = ligne.split()[1] if len(ligne.split()) > 1 else "inconnu"
    if etat != "device":
        raise ErreurPoussage(
            f"Appareil détecté mais dans l'état {etat!r} (attendu : 'device'). "
            f"Si c'est 'unauthorized', acceptez la demande de débogage USB "
            f"affichée sur la tablette."
        )


def pousser_fichier(chemin_local: Path, package: str, nom_distant: str,
                     chemin_distant: str | None, *, serial: str | None,
                     adb: str) -> None:
    """Pousse un fichier local vers le dossier privé de l'application."""
    if not chemin_local.exists():
        raise ErreurPoussage(f"Fichier introuvable sur le poste : {chemin_local}")

    chemin_temporaire_sdcard = f"/sdcard/{nom_distant}"

    print(f"\n→ {chemin_local.name}")

    # 1. Poste -> zone publique de la tablette
    executer_adb(["push", str(chemin_local), chemin_temporaire_sdcard],
                 serial=serial, adb=adb)

    # 2. Zone publique -> dossier privé de l'application (droits de l'appli)
    if chemin_distant:
        destination = chemin_distant
    else:
        destination = nom_distant  # relatif au dossier "files" de run-as

    commande_cp = f"cp {shlex.quote(chemin_temporaire_sdcard)} {shlex.quote(destination)}"
    executer_adb(["shell", "run-as", package, "sh", "-c", commande_cp],
                 serial=serial, adb=adb)

    # 3. Nettoyage de la copie temporaire en zone publique
    executer_adb(["shell", "rm", "-f", chemin_temporaire_sdcard],
                 serial=serial, adb=adb)

    print(f"  ✅ Déposé sous les droits de {package} ({destination})")


def verifier_depot(package: str, nom_distant: str, chemin_distant: str | None,
                    *, serial: str | None, adb: str) -> bool:
    """Confirme que le fichier existe bien côté application après dépôt."""
    destination = chemin_distant or nom_distant
    commande = f"[ -f {shlex.quote(destination)} ] && echo OK || echo ABSENT"
    try:
        sortie = executer_adb(["shell", "run-as", package, "sh", "-c", commande],
                               serial=serial, adb=adb, verbeux=False)
    except ErreurPoussage:
        return False
    return sortie.strip() == "OK"


def analyser_arguments() -> argparse.Namespace:
    parseur = argparse.ArgumentParser(
        description="Pousse la clé ADB du poste vers le dossier privé de "
                    "KCApp sur une tablette Android (push + run-as).")
    parseur.add_argument(
        "--package", default=PACKAGE_PAR_DEFAUT,
        help=f"Nom de paquet de l'APK KCApp (défaut : {PACKAGE_PAR_DEFAUT})")
    parseur.add_argument(
        "--cle", type=Path, default=Path.home() / ".android" / "adbkey",
        help="Chemin de la clé privée sur le poste (défaut : ~/.android/adbkey)")
    parseur.add_argument(
        "--cle-pub", type=Path, default=None,
        help="Chemin de la clé publique sur le poste "
             "(défaut : <clé privée>.pub). Passer --sans-cle-pub pour l'ignorer.")
    parseur.add_argument(
        "--sans-cle-pub", action="store_true",
        help="Ne pousser que la clé privée (adbkey), pas la .pub.")
    parseur.add_argument(
        "--chemin-distant", default=None,
        help="Chemin absolu exact où déposer adbkey dans le dossier privé de "
             "l'application (ex. celui affiché par le log "
             "'📁 Clé ADB attendue ici : ...' dans QuestClient.__init__, via "
             "`adb logcat`). Si omis, dépose sous le nom 'adbkey' relatif au "
             "dossier 'files' de run-as — à ajuster si ça ne correspond pas "
             "à app_storage_path() sur votre build.")
    parseur.add_argument(
        "--serial", default=None,
        help="Numéro de série de la tablette cible (utile si plusieurs "
             "appareils sont connectés ; voir `adb devices`).")
    parseur.add_argument(
        "--adb", default="adb",
        help="Chemin vers l'exécutable adb si absent du PATH.")
    return parseur.parse_args()


def main() -> int:
    args = analyser_arguments()

    cle_privee = args.cle.expanduser()
    cle_publique = None
    if not args.sans_cle_pub:
        cle_publique = (args.cle_pub or cle_privee.with_suffix(cle_privee.suffix + ".pub")).expanduser()

    print("Vérification de la connexion à la tablette...")
    try:
        verifier_appareil(args.serial, args.adb)
    except ErreurPoussage as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    print("✅ Tablette détectée et autorisée.")

    try:
        chemin_distant_prive = None
        chemin_distant_public = None
        if args.chemin_distant:
            chemin_distant_prive = args.chemin_distant
            chemin_distant_public = args.chemin_distant + ".pub"

        pousser_fichier(
            cle_privee, args.package, NOM_FICHIER_CLE_PRIVEE,
            chemin_distant_prive, serial=args.serial, adb=args.adb)

        if cle_publique is not None:
            pousser_fichier(
                cle_publique, args.package, NOM_FICHIER_CLE_PUBLIQUE,
                chemin_distant_public, serial=args.serial, adb=args.adb)

    except ErreurPoussage as exc:
        print(f"\n❌ {exc}", file=sys.stderr)
        return 1

    print("\nVérification du dépôt...")
    ok_privee = verifier_depot(args.package, NOM_FICHIER_CLE_PRIVEE,
                                chemin_distant_prive, serial=args.serial, adb=args.adb)
    if ok_privee:
        print("✅ adbkey bien présent côté application.")
    else:
        print(
            "⚠️ Impossible de confirmer la présence du fichier avec le "
            "chemin utilisé. Vérifiez le chemin réel via le log "
            "'📁 Clé ADB attendue ici : ...' (adb logcat) et relancez avec "
            "--chemin-distant si besoin.",
            file=sys.stderr,
        )
        return 1

    print("\n✅ Terminé.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())