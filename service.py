"""
Service Android minimal, démarré depuis app/app.py (_start_background_tracker)
quand l'app tourne sur Android.

Ne fait aucun travail métier : le BLE (app/ble/ble_manager.py) et l'UDP
(app/network/udp_discovery.py, udp_controller.py) continuent de tourner dans
les threads de l'app principale, inchangés. Ce service existe uniquement
parce que buildozer.spec le déclare avec le flag "foreground" — p4a génère
alors le code Java qui appelle startForeground() avec une notification
persistante pour CE service, ce qui protège tout le process (donc l'app
principale et ses threads BLE/UDP) du gel/de la suppression par Android
quand l'intervenant passe sur une autre app.

Sans ce service, Android peut geler le process de l'app en quelques dizaines
de secondes dès qu'elle n'est plus au premier plan, coupant le suivi FC.
"""

from time import sleep

while True:
    sleep(5)
