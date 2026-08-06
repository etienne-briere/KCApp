# -*- coding: utf-8 -*-
"""
Prépare la clé ADB à embarquer dans l'application Android.

Le casque n'autorise pas un appareil, il autorise une **clé**. Le poste qui
pilote déjà le casque en possède une, acceptée une fois pour toutes lors du
premier branchement USB. Recopier cette clé dans l'application Android revient
donc à lui transmettre l'autorisation : la tablette se connectera du premier
coup, sans que personne n'ait à mettre le casque pour valider une demande.

C'est le point qui rend l'ensemble praticable. Sans cette clé, la première
connexion depuis la tablette afficherait une boîte de dialogue *dans le
casque* — exactement ce qu'on cherche à éviter.

    python quest_android/outils/preparer_cle.py
    python quest_android/outils/preparer_cle.py --sortie ~/chez_le_collegue

Ce que le script fait :

1. localise la clé ADB du poste ;
2. vérifie qu'elle est bien celle que le casque a autorisée ;
3. la recopie sous le nom attendu par l'application.

**La clé est un secret.** Quiconque la détient peut piloter le casque sur le
réseau. Elle n'a pas à circuler par courriel ni à entrer dans un dépôt de code.
Le script le rappelle et refuse d'écrire dans un dossier suivi par Git.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "shared"))

try:
    from console import configurer_console
except ImportError:  # pragma: no cover - utilisable hors du dépôt
    def configurer_console() -> None:
        for flux in (sys.stdout, sys.stderr):
            try:
                flux.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

configurer_console()

VERT, GRIS, JAUNE, ROUGE, RAZ = ("\033[32m", "\033[90m", "\033[33m",
                                 "\033[31m", "\033[0m")

#: Emplacements usuels de la clé ADB, par ordre de vraisemblance.
EMPLACEMENTS = (
    Path.home() / ".android" / "adbkey",
    Path("/root/.android/adbkey"),
)


def trouver_cle() -> Path | None:
    for chemin in EMPLACEMENTS:
        if chemin.exists() and chemin.stat().st_size > 0:
            return chemin
    return None


def empreinte_publique(cle: Path) -> str:
    """Empreinte lisible de la clé, pour la comparer à celle du casque."""
    publique = cle.with_suffix(".pub")
    if not publique.exists():
        return ""
    contenu = publique.read_text(encoding="utf-8", errors="replace").strip()
    # Le fichier .pub se termine par un commentaire « utilisateur@machine »
    # qui identifie le poste d'origine.
    return contenu.split()[-1] if " " in contenu else contenu[-24:]


def casque_autorise(adb: str = "adb") -> tuple[bool, str]:
    """
    Le casque reconnaît-il ce poste ?

    Un appareil « unauthorized » signifie que la clé n'a pas été acceptée : la
    recopier dans l'application ne servirait à rien, il faut d'abord valider la
    demande dans le casque, une fois.
    """
    if shutil.which(adb) is None:
        return False, "adb introuvable sur ce poste."
    try:
        resultat = subprocess.run([adb, "devices"], capture_output=True,
                                  text=True, encoding="utf-8",
                                  errors="replace", timeout=30)
    except Exception as exc:                                  # noqa: BLE001
        return False, f"adb n'a pas répondu ({exc})."

    lignes = [l for l in resultat.stdout.splitlines()[1:] if l.strip()]
    if not lignes:
        return False, "aucun casque détecté (branchez-le, ou lancez « adb connect »)."
    for ligne in lignes:
        if "\tdevice" in ligne:
            return True, ligne.split("\t")[0]
        if "unauthorized" in ligne:
            return False, ("casque détecté mais non autorisé : mettez-le et "
                           "acceptez la demande de débogage, une fois.")
    return False, "casque dans un état inattendu : " + lignes[0]


def dossier_suivi_par_git(dossier: Path) -> bool:
    try:
        resultat = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=dossier, capture_output=True, text=True, timeout=10)
        return resultat.returncode == 0 and "true" in resultat.stdout
    except Exception:                                         # noqa: BLE001
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sortie", default="",
                        help="dossier où déposer la clé (défaut : à côté de ce script)")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--sans-verification", action="store_true",
                        help="ne pas vérifier que le casque autorise cette clé")
    arguments = parser.parse_args()

    print("=" * 68)
    print("  Préparation de la clé ADB pour l'application Android")
    print("=" * 68 + "\n")

    cle = trouver_cle()
    if cle is None:
        print(f"  {ROUGE}Aucune clé ADB trouvée.{RAZ}")
        print(f"  {GRIS}Elle est créée au premier usage d'adb. Branchez le "
              f"casque en USB, lancez « adb devices », acceptez la demande "
              f"dans le casque, puis relancez ce script.{RAZ}\n")
        return 1

    print(f"  Clé trouvée   : {cle}")
    empreinte = empreinte_publique(cle)
    if empreinte:
        print(f"  Origine       : {empreinte}")

    if arguments.sans_verification:
        print(f"  {JAUNE}Vérification ignorée.{RAZ}")
    else:
        autorise, detail = casque_autorise(arguments.adb)
        if autorise:
            print(f"  Casque        : {VERT}autorise cette clé{RAZ} ({detail})")
        else:
            print(f"\n  {ROUGE}Cette clé n'est pas confirmée par le casque.{RAZ}")
            print(f"  {GRIS}{detail}{RAZ}")
            print(f"  {GRIS}La recopier maintenant produirait une application "
                  f"qui ne se connecte pas.{RAZ}")
            print(f"  {GRIS}Relancez avec --sans-verification si vous savez ce "
                  f"que vous faites.{RAZ}\n")
            return 1

    sortie = Path(arguments.sortie).expanduser() if arguments.sortie \
        else Path(__file__).resolve().parent / "cle"
    sortie.mkdir(parents=True, exist_ok=True)

    if dossier_suivi_par_git(sortie):
        print(f"\n  {ROUGE}{sortie} est suivi par Git.{RAZ}")
        print(f"  {GRIS}Une clé de pilotage n'a pas à entrer dans un dépôt de "
              f"code : quiconque la détient peut commander le casque sur le "
              f"réseau. Choisissez un dossier hors du dépôt avec --sortie.{RAZ}\n")
        return 1

    destination = sortie / "adbkey"
    shutil.copy2(cle, destination)
    try:
        destination.chmod(0o600)
    except OSError:
        pass

    print(f"\n  {VERT}Clé écrite : {destination}{RAZ}\n")
    print("  À faire ensuite, dans l'application Android :")
    print("    1. déposer ce fichier dans  app/src/main/assets/adbkey")
    print("    2. appeler ClientCasque.preparerIdentite(context) au démarrage")
    print("    3. vérifier que assets/adbkey figure bien dans le .gitignore\n")
    print(f"  {JAUNE}Ce fichier est un secret.{RAZ}")
    print(f"  {GRIS}Transmettez-le par un canal sûr, pas par courriel. "
          f"Il ne donne accès qu'au casque, mais il y donne un accès "
          f"complet.{RAZ}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
