# -*- coding: utf-8 -*-
"""
Panneau de contrôle du casque Meta Quest — interface graphique.

Habille les fonctions de `quest.py` (diagnostic, connexion Wi-Fi, préparation
de séance, arrêt, récupération des données) dans une petite fenêtre à
boutons, pour ne pas avoir à ouvrir un terminal. Conçu pour être packagé en
.exe autonome avec PyInstaller — voir `construire_exe.bat`.

L'exécutable doit rester dans le dossier `quest_control`, à côté de
`config.json` : c'est là que sont lus/écrits la configuration et les
dossiers de données récupérées.
"""

from __future__ import annotations

import queue
import sys
import threading
import types
from pathlib import Path
from tkinter import (
    BOTH, DISABLED, END, LEFT, NORMAL, RIGHT, TOP, X, Y,
    Tk, Frame, Label, Button, Entry, StringVar, Scrollbar,
    Text, messagebox, simpledialog,
)

# ---------------------------------------------------------------------------
# Localisation de quest.py, avec ou sans empaquetage PyInstaller.
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # .exe PyInstaller : le dossier qui contient réellement l'exécutable.
    DOSSIER_QUEST_CONTROL = Path(sys.executable).resolve().parent
else:
    DOSSIER_QUEST_CONTROL = Path(__file__).resolve().parent

# `quest.py` importe `from console import configurer_console` en croyant
# trouver `shared/console.py` à côté du dépôt. Ce module ne fait qu'activer
# les couleurs ANSI dans un terminal — inutile ici, la sortie va dans un
# widget Tk. On fournit un module de remplacement plutôt que de dépendre de
# l'arborescence du dépôt, absente une fois empaqueté en .exe.
if "console" not in sys.modules:
    _stub = types.ModuleType("console")
    _stub.configurer_console = lambda: None
    sys.modules["console"] = _stub

sys.path.insert(0, str(DOSSIER_QUEST_CONTROL))
import quest as qc  # noqa: E402

# `quest.py` calcule CONFIG_PATH et RACINE à partir de son propre __file__,
# qui pointe dans l'archive temporaire de PyInstaller une fois empaqueté —
# pas dans le dossier où vit réellement config.json. On les recale sur
# l'emplacement effectif de l'exécutable / du script.
qc.CONFIG_PATH = DOSSIER_QUEST_CONTROL / "config.json"
qc.RACINE = DOSSIER_QUEST_CONTROL.parent


# ---------------------------------------------------------------------------
# Fenêtre
# ---------------------------------------------------------------------------

class PanneauQuest:

    def __init__(self, root: Tk):
        self.root = root
        self.root.title("APEX — Pilotage du casque")
        self.root.geometry("720x520")
        self.file_evenements: "queue.Queue[tuple]" = queue.Queue()
        self.boutons: list[Button] = []

        self._construire()
        self._journaliser("Prêt. Casque à connecter, puis « Préparer la séance ».")
        self.root.after(150, self._depiler_evenements)

    # -- construction --------------------------------------------------

    def _construire(self) -> None:
        barre = Frame(self.root, padx=8, pady=8)
        barre.pack(side=TOP, fill=X)

        Label(barre, text="IP du casque :").pack(side=LEFT)
        self.var_ip = StringVar(value=qc.charger_config().get("derniere_ip", ""))
        Entry(barre, textvariable=self.var_ip, width=16).pack(side=LEFT, padx=(4, 12))
        self._bouton(barre, "Connecter", self._connecter).pack(side=LEFT, padx=2)
        self._bouton(barre, "État", self._etat).pack(side=LEFT, padx=2)
        self._bouton(barre, "Diagnostic", self._diagnostic).pack(side=LEFT, padx=2)

        principal = Frame(self.root, padx=8, pady=4)
        principal.pack(side=TOP, fill=X)
        self._bouton(principal, "Préparer la séance", self._preparer,
                     gras=True).pack(side=LEFT, padx=2)
        self._bouton(principal, "Lancer le jeu", self._lancer).pack(side=LEFT, padx=2)
        self._bouton(principal, "Arrêter le jeu", self._arreter).pack(side=LEFT, padx=2)

        limite = Frame(self.root, padx=8, pady=4)
        limite.pack(side=TOP, fill=X)
        Label(limite, text="Limite de jeu :").pack(side=LEFT)
        self._bouton(limite, "État", self._limite_etat).pack(side=LEFT, padx=2)
        self._bouton(limite, "Désactiver", self._limite_desactiver).pack(side=LEFT, padx=2)
        self._bouton(limite, "Activer", self._limite_activer).pack(side=LEFT, padx=2)

        donnees = Frame(self.root, padx=8, pady=4)
        donnees.pack(side=TOP, fill=X)
        self._bouton(donnees, "Récupérer les données",
                     self._recuperer).pack(side=LEFT, padx=2)

        zone = Frame(self.root, padx=8, pady=8)
        zone.pack(side=TOP, fill=BOTH, expand=True)
        defilement = Scrollbar(zone)
        defilement.pack(side=RIGHT, fill=Y)
        self.texte = Text(zone, wrap="word", yscrollcommand=defilement.set,
                          state=DISABLED, bg="#111", fg="#ddd",
                          insertbackground="#ddd")
        self.texte.pack(side=LEFT, fill=BOTH, expand=True)
        defilement.config(command=self.texte.yview)

    def _bouton(self, parent, libelle, commande, gras: bool = False) -> Button:
        police = ("Segoe UI", 9, "bold") if gras else ("Segoe UI", 9)
        b = Button(parent, text=libelle, command=commande, font=police)
        self.boutons.append(b)
        return b

    # -- journal ----------------------------------------------------------

    def _journaliser(self, message: str) -> None:
        self.texte.config(state=NORMAL)
        self.texte.insert(END, message.rstrip() + "\n")
        self.texte.see(END)
        self.texte.config(state=DISABLED)

    # -- exécution en tâche de fond -----------------------------------------

    def _lancer_tache(self, libelle: str, action) -> None:
        """
        Exécute `action` (sans argument, renvoie une chaîne à journaliser) dans
        un thread séparé, pour ne pas geler la fenêtre pendant qu'ADB répond.
        """
        for b in self.boutons:
            b.config(state=DISABLED)
        self._journaliser(f"\n→ {libelle}…")

        def travail():
            try:
                resultat = action()
                self.file_evenements.put(("ok", resultat))
            except qc.ErreurAdb as exc:
                self.file_evenements.put(("erreur", str(exc)))
            except Exception as exc:  # noqa: BLE001
                self.file_evenements.put(("erreur", f"Erreur inattendue : {exc}"))

        threading.Thread(target=travail, daemon=True).start()

    def _depiler_evenements(self) -> None:
        try:
            while True:
                nature, message = self.file_evenements.get_nowait()
                self._journaliser(message)
                for b in self.boutons:
                    b.config(state=NORMAL)
        except queue.Empty:
            pass
        self.root.after(150, self._depiler_evenements)

    # -- actions ----------------------------------------------------------

    def _quest(self) -> "qc.Quest":
        return qc.Quest()

    def _connecter(self) -> None:
        ip = self.var_ip.get().strip()

        def action():
            quest = self._quest()
            if ip:
                cible = quest.connecter_wifi(ip)
            else:
                cible = quest.activer_wifi()
            return f"Connecté à {cible}."

        self._lancer_tache("Connexion", action)

    def _etat(self) -> None:
        def action():
            quest = self._quest()
            appareils = quest.appareils()
            if not appareils:
                return "Aucun casque détecté (câble débranché ou Wi-Fi perdu)."
            if not quest.connecte():
                etats = ", ".join(f"{a['serie']} ({a['etat']})" for a in appareils)
                return f"Casque détecté mais pas prêt : {etats}"
            etat = quest.etat()
            sessions = quest.lister_sessions()
            lignes = [
                f"Modèle            : {etat['modele']}",
                f"Liaison           : {etat['liaison']}",
                f"Batterie          : {etat['batterie']} %"
                if etat["batterie"] is not None else "Batterie          : inconnue",
                f"Jeu installé      : {'oui' if etat['jeu_installe'] else 'non'}",
                f"Application active: {etat['application_active'] or '(aucune)'}",
                f"Sessions présentes: {len(sessions)}",
            ]
            return "\n".join(lignes)

        self._lancer_tache("Lecture de l'état", action)

    def _diagnostic(self) -> None:
        def action():
            quest = self._quest()
            etapes = quest.diagnostic()
            lignes = []
            for e in etapes:
                marque = "OK  " if e["ok"] else "ECHEC"
                lignes.append(f"[{marque}] {e['titre']}")
                if e["detail"]:
                    lignes.append(f"        {e['detail']}")
                if not e["ok"] and e["remede"]:
                    lignes.append(f"        -> {e['remede']}")
            manques = sum(1 for e in etapes if not e["ok"])
            lignes.append("")
            lignes.append(f"{manques} point(s) à régler." if manques
                          else "Tout est en place.")
            return "\n".join(lignes)

        self._lancer_tache("Diagnostic", action)

    def _preparer(self) -> None:
        def action():
            quest = self._quest()
            etapes = []

            def etape(libelle, fonction):
                try:
                    fonction()
                    etapes.append((libelle, True, ""))
                except Exception as exc:  # noqa: BLE001
                    etapes.append((libelle, False, str(exc).splitlines()[0]))

            etape("Réveil de l'appareil", quest.reveiller)
            etape("Simulation du port", lambda: quest.simuler_port(True))
            etape("Veille neutralisée", lambda: quest.maintenir_eveille(True))
            etape("Limite de jeu désactivée", lambda: quest.limite_definir(False))
            etape("Jeu lancé", quest.lancer)

            lignes = []
            for libelle, ok, detail in etapes:
                lignes.append(f"[{'OK  ' if ok else 'ECHEC'}] {libelle}"
                              + (f" — {detail}" if detail else ""))
            rates = [e for e in etapes if not e[1]]
            lignes.append("")
            lignes.append(
                f"{len(rates)} étape(s) en échec — vérifiez avant de tendre le casque."
                if rates else
                "Casque prêt. Vous pouvez le tendre au participant.")
            return "\n".join(lignes)

        self._lancer_tache("Préparation de la séance", action)

    def _lancer(self) -> None:
        def action():
            quest = self._quest()
            quest.reveiller()
            quest.maintenir_eveille(True)
            package = quest.lancer()
            return f"Jeu lancé : {package}"

        self._lancer_tache("Lancement du jeu", action)

    def _arreter(self) -> None:
        def action():
            quest = self._quest()
            package = quest.arreter()
            return f"Jeu arrêté : {package}"

        self._lancer_tache("Arrêt du jeu", action)

    def _limite_etat(self) -> None:
        def action():
            quest = self._quest()
            etat = quest.limite_etat()
            return (
                f"Limite de jeu : {'ACTIVE' if etat['active'] else 'désactivée'}\n"
                f"  propriété debug.oculus.guardian_pause : "
                f"{'posée' if etat['pause_propriete'] else 'absente'}\n"
                + (f"  services de test Horizon : disable_guardian = "
                   f"{etat['desactivee_services']}"
                   if etat["services_disponibles"] else
                   "  services de test Horizon : indisponibles")
            )

        self._lancer_tache("Lecture de la limite de jeu", action)

    def _limite_desactiver(self) -> None:
        def action():
            quest = self._quest()
            resultat = quest.limite_definir(False)
            return "Limite désactivée.\n" + "\n".join(
                f"  {l}" for l in resultat["journal"])

        self._lancer_tache("Désactivation de la limite", action)

    def _limite_activer(self) -> None:
        def action():
            quest = self._quest()
            resultat = quest.limite_definir(True)
            return "Limite réactivée.\n" + "\n".join(
                f"  {l}" for l in resultat["journal"])

        self._lancer_tache("Réactivation de la limite", action)

    def _recuperer(self) -> None:
        participant = simpledialog.askstring(
            "Récupérer les données",
            "Code participant (ex. APEX_001) :", parent=self.root)
        if participant is None:
            return
        effacer = messagebox.askyesno(
            "Effacer du casque ?",
            "Effacer les données du casque après copie ?\n"
            "À ne faire qu'après avoir vérifié l'import dans l'eCRF — "
            "suppression définitive.",
            parent=self.root)

        def action():
            quest = self._quest()
            rapport = quest.recuperer(participant=participant, effacer=effacer)
            lignes = [f"{len(rapport['recuperes'])} session(s) récupérée(s) "
                     f"dans {rapport['destination']}"]
            lignes += [f"  - {n}" for n in rapport["recuperes"]]
            lignes += [f"  ECHEC {e}" for e in rapport["echecs"]]
            return "\n".join(lignes)

        self._lancer_tache("Récupération des données", action)


def main() -> int:
    root = Tk()
    PanneauQuest(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
