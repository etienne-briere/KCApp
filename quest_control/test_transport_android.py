# -*- coding: utf-8 -*-
"""
Tests de `transport_android.py`, SANS le simulateur `quest_control/simulateur.py`.

Pourquoi un nouveau test plutôt que de brancher l'ancien simulateur : celui-ci
fabrique un faux binaire `adb` invoqué via `subprocess` (voir
`creer_faux_adb`). `QuestAndroid` ne passe justement plus par un `subprocess`
ni par un binaire `adb` — c'est tout l'objet du transport_android.py. Le
simulateur existant n'a donc rien à intercepter : `QuestAndroid` ne l'appelle
jamais.

Ce que ces tests vérifient à la place : le nouveau code, c'est-à-dire la
traduction des appels `_executer(["shell", ...])`, `["pull", ...]`,
`["connect", ...]`, `["devices", "-l"]` vers `adb_shell`, et la gestion des
échecs de connexion — en remplaçant `AdbDeviceTcp` par un faux objet en
mémoire (`FauxDevice`). Le protocole ADB lui-même (poignée de main, signature
RSA, framing) est déjà testé côté bibliothèque `adb_shell` ; inutile de le
retester ici.

Ce que ces tests NE vérifient PAS : le comportement du vrai firmware Horizon
OS. Pour ça, il faut un casque réel en mode TCP — voir la note en bas de
fichier.

Installation :   pip install adb-shell[pythonrsa] pytest
Exécution   :    pytest quest_control/test_transport_android.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quest import ErreurAdb
import transport_android


class FauxDevice:
    """Remplace AdbDeviceTcp : mémorise ce qu'on lui demande, sans réseau."""

    def __init__(self, *args, **kwargs):
        self.connecte = False
        self.commandes = []
        self.reponse_shell = ""
        self.echouer_connexion = False

    def connect(self, rsa_keys=None, auth_timeout_s=None):
        if self.echouer_connexion:
            return False
        self.connecte = True
        return True

    def close(self):
        self.connecte = False

    def shell(self, commande, timeout_s=None):
        self.commandes.append(("shell", commande))
        return self.reponse_shell

    def pull(self, distant, local, timeout_s=None):
        self.commandes.append(("pull", distant, local))


@pytest.fixture
def quest(tmp_path, monkeypatch):
    """QuestAndroid connecté à un FauxDevice au lieu d'un vrai casque."""
    cle = tmp_path / "adbkey"
    cle.write_text("cle-privee-factice")
    cle.with_name("adbkey.pub").write_text("cle-publique-factice")

    # Pas besoin d'une vraie paire RSA : on ne teste pas la signature elle-même.
    monkeypatch.setattr(transport_android, "PythonRSASigner",
                         lambda pub, priv: "signataire-factice")
    monkeypatch.setattr(transport_android, "AdbDeviceTcp",
                         lambda *a, **kw: FauxDevice())

    config = {
        "package": "com.m2s.apexexperiment",
        "activite": "",
        "dossiers_donnees": ["/sdcard/Android/data/{package}/files"],
        "destination_import": str(tmp_path / "donnees_recuperees"),
        "port_wifi": 5555,
        "pin_store": "",
    }
    return transport_android.QuestAndroid(
        ip="192.168.1.42", chemin_cle=cle,
        config=config, chemin_config=tmp_path / "config.json")


# -- traduction des commandes --------------------------------------------

def test_shell_relaie_la_commande_et_le_resultat(quest):
    quest._device.reponse_shell = "Quest 2"
    r = quest.shell("getprop ro.product.model")
    assert r.ok
    assert r.sortie == "Quest 2"
    assert quest._device.commandes == [("shell", "getprop ro.product.model")]


def test_pull_transmet_les_bons_chemins(quest, tmp_path):
    local = tmp_path / "session1"
    r = quest._executer(["pull", "/sdcard/session1", str(local)])
    assert r.ok
    assert ("pull", "/sdcard/session1", str(local)) in quest._device.commandes


def test_connect_force_une_nouvelle_authentification(quest):
    r = quest._executer(["connect", "192.168.1.42:5555"])
    assert r.ok
    assert "connected" in r.sortie


def test_tcpip_est_sans_effet_et_ne_leve_pas(quest):
    # Rappel : le casque doit déjà écouter en TCP, ce n'est pas quelque chose
    # que la tablette peut déclencher elle-même.
    r = quest._executer(["tcpip", "5555"])
    assert r.ok


# -- connexion et erreurs --------------------------------------------------

def test_verifier_connexion_ok_quand_le_casque_repond(quest):
    quest.verifier_connexion()  # ne doit pas lever


def test_connexion_echouee_leve_erreur_adb_explicite(quest):
    quest._device.echouer_connexion = True
    with pytest.raises(ErreurAdb):
        quest.verifier_connexion()


def test_connecte_reflete_l_etat_reel(quest):
    assert quest.connecte() is True
    quest._device.echouer_connexion = True
    quest._connecte = False
    assert quest.connecte() is False


def test_appareils_expose_une_forme_compatible_avec_lancer_et_etat(quest):
    """
    `Quest.etat()` et `Quest.diagnostic()` font
    `next(a for a in appareils() if a["etat"] == "device")` : la forme du
    dictionnaire doit rester compatible, même sans énumération réelle.
    """
    appareils = quest.appareils()
    assert len(appareils) == 1
    assert appareils[0]["etat"] == "device"
    assert appareils[0]["wifi"] is True


def test_activer_wifi_refuse_explicitement(quest):
    """Ce n'est pas un oubli : impossible à faire depuis la tablette."""
    with pytest.raises(ErreurAdb):
        quest.activer_wifi()


# -- logique héritée de Quest, non réécrite --------------------------------

def test_lancer_reussit_avec_le_jeu_deja_installe(quest):
    """
    `Quest.lancer()` est héritée telle quelle : elle appelle `self.paquets()`
    puis `self.shell(...)`. Si ce test passe, la logique métier n'a pas été
    cassée par le changement de transport.
    """
    def reponses(commande):
        if "pm list packages" in commande:
            return "package:com.m2s.apexexperiment\n"
        if "monkey -p" in commande:
            return "Events injected: 1\n"
        return ""

    quest._device.shell = lambda commande, timeout_s=None: reponses(commande)
    package = quest.lancer()
    assert package == "com.m2s.apexexperiment"


# ---------------------------------------------------------------------------
# Ce que ces tests ne couvrent pas : validation avec un vrai casque
# ---------------------------------------------------------------------------
#
# Ces tests remplacent AdbDeviceTcp par un objet en mémoire : ils vérifient
# QuestAndroid, pas adb_shell, ni le firmware du casque. Avant la première
# séance réelle, il reste indispensable de refaire ce que fait déjà
# `quest_control/README.md` pour la version PC : une vraie connexion, sur le
# vrai casque, avec la vraie clé — la poignée de main RSA et le comportement
# du firmware Horizon OS ne se simulent pas de façon fiable.