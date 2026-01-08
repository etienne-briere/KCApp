from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.logger import Logger
from kivy.uix.togglebutton import ToggleButton
import logging
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.uix.anchorlayout import AnchorLayout
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.graphics import Line, Color, InstructionGroup
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle
from libs.kivy_garden.graph import Graph, MeshLinePlot, LinePlot # récupérée en local
from kivy.uix.slider import Slider
from kivy.graphics.texture import Texture
from kivy.uix.floatlayout import FloatLayout
from kivy.properties import NumericProperty, DictProperty
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView

from kivy.core.window import Window
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.animation import Animation
from kivy.clock import Clock

import time
import asyncio
import bleak
import socket
import websockets
from functools import partial
import csv
from pathlib import Path
import pandas as pd
import os
import sys

logging.Logger.manager.root = Logger

# Définir la couleur de fond globale (gris foncé = dark mode)
Window.clearcolor = (0.1, 0.1, 0.1, 1)

# UUID (standard BLE)
HEART_RATE_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
CHAR_BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"  # UUID du service battery level

TARGET_DEVICES = ["Forerunner", "Polar", "vívoactiv" , "Instinct"]  # Filtre pour les marques ciblées

# Paramètres WebSocket
clients = set()
HOST = "0.0.0.0"
PORT = 8765

# Paramètres UDP
UDP_PORT = 5003
BROADCAST_IP = "255.255.255.255"

def create_rounded_button(text, on_press, size_hint=(1, None), background_color=(0.2, 0.6, 0.86, 1)):
    ''' Créer un bouton stylisé'''
    return Button(
        text=text,
        size_hint=size_hint, # prend toute la largeur (1=largeur totale, None = hauteur)
        height=100, # hauteur fixe de 100px
        background_normal='', # permet de mettre une image de fond
        background_color=background_color, # bleu
        color=(1, 1, 1, 1), # texte blanc
        font_size=25, # taille police
        on_press=on_press, # action au clic
        pos_hint={'center_x': 0.5}
    )

def create_label(text, size_hint=(1, None), font_size=24):
    ''' Créer un label avec un style propre'''
    return Label(
        text=text,
        font_size=font_size, # police personnalisée
        color=(1, 1, 1, 1), # blanc
        size_hint=size_hint, # toute la largeur
        height=40
    )

def create_icon_label_row(icon_path, label_text, screen_instance=None, font_size=40, icon_size=(40, 40), is_dynamic=False, ref=None):
    # Layout horizontal centré
    outer_layout = AnchorLayout(
        anchor_x='center',
        anchor_y='center',
        size_hint=(1, None)
    )

    # Row horizontale : icon + label
    row = BoxLayout(
        orientation='horizontal',
        spacing=dp(10), # espacement = 10 pixels adaptés à la densité de l'écran
        size_hint=(None, None),
    )

    # Icône
    icon = Image(
        source=icon_path,
        size_hint=(None, None),
        size=icon_size
    )

    # Label (centré verticalement)
    label = Label(
        text=label_text,
        font_size=font_size,
        size_hint=(None, None),
        halign='left',
        valign='middle'
    )

    # Ajuster automatiquement le taille du label à la taille de son contenu
    label.bind(texture_size=lambda inst, val: setattr(inst, 'size', val))
    label.text_size = (None, None)

    # Ajout dans la row
    row.add_widget(icon)
    row.add_widget(label)

    # Ajuste automatiquement la taille de la row
    def update_row_size(*args):
        row.width = icon.width + dp(10) + label.width
        row.height = max(icon.height, label.height)
        outer_layout.height = row.height

    icon.bind(size=update_row_size)
    label.bind(size=update_row_size)

    # Appelle une fois au début
    update_row_size()

    outer_layout.add_widget(row)

    # Stocker une référence dynamique si besoin
    if is_dynamic and ref and screen_instance:
        setattr(screen_instance, ref, label)
        # setattr(outer_layout, ref, label)

    return outer_layout


def create_icon_slider(icon_left_path, icon_right_path, min_val, max_val, icon_size=(40, 40), step=1, initial=None, unit="", sync_key=None):
    '''
    Crée un composant personnalisé contenant :
    - Deux icônes (gauche et droite) encadrant un Slider horizontal.
    - Un label flottant affichant dynamiquement la valeur du Slider.
    - La possibilité de synchroniser ce Slider avec un autre via une clé de synchronisation.
    '''
    container = AnchorLayout(
        anchor_x='center',
        anchor_y='center',
        size_hint=(1, None)
    )

    # --- Horizontal layout pour icônes + slider ---
    slider_row = BoxLayout(
        orientation='horizontal',
        spacing=dp(10),
        size_hint=(0.8, None)
    )

    # Icônes
    icon_left = Image(source=icon_left_path,
                      size_hint=(None, None),
                      size=icon_size
                      )

    icon_right = Image(source=icon_right_path,
                       size_hint=(None, None),
                       size=icon_size
                       )

    # --- Slider + label dynamiques ---
    slider_container = FloatLayout(size_hint=(1, None))


    # Crée slider
    slider = Slider(
        min=min_val,
        max=max_val,
        value=initial if initial is not None else min_val,
        step=step,
        size_hint=(1, None),
        height=icon_size[1],
        pos_hint={'center_y': 0.2, 'center_x': 0.5}
    )

    # Crée label
    value_label = Label(
        text=f"{int(initial)}{unit}",
        size_hint=(None, None),
        font_size=20,
        color=(1, 1, 1, 1),
        pos_hint={'center_y': 0.5},
        bold=True, # gras
        pos=(slider.value_pos[0], slider.value_pos[1])
    )

    def update_label_pos(instance, value):
        ''' Mettre à jour la position du label'''
        # Récupère la position du curseur global
        if slider.value_pos:
            slider_x, _ = slider.to_widget(*slider.value_pos)
            value_label.center_x = slider_x
        value_label.text = f"{int(value)}{unit}"

    # Changer la valeur du label quand la valeur du curseur change
    slider.bind(value=update_label_pos)

    # Recalcule la position du label si la taille du slider change (ex : redimensionnement de page)
    slider.bind(size=lambda *a: update_label_pos(slider, slider.value))

    # Ajout dans le slider_container
    slider_container.add_widget(value_label)
    slider_container.add_widget(slider)

    # Ajout dans le slider_row
    slider_row.add_widget(icon_left)
    slider_row.add_widget(slider_container)
    slider_row.add_widget(icon_right)

    # Ajout dans le container
    container.add_widget(slider_row)

    # Synchronisation activée si sync_key est fourni
    if sync_key:
        app = App.get_running_app()

        # Initialise la valeur si elle n'existe pas
        if sync_key not in app.shared_slider_values:
            app.shared_slider_values[sync_key] = slider.value

        # Quand le slider change → mettre à jour la valeur partagée
        def on_slider_change(instance, value):
            if app.shared_slider_values.get(sync_key) != value:
                app.shared_slider_values[sync_key] = value

        # Quand la valeur partagée change → mettre à jour ce slider
        def on_shared_change(instance, shared_values):
            new_value = shared_values.get(sync_key)
            if new_value is not None and slider.value != new_value:
                slider.value = new_value

        slider.bind(value=on_slider_change)
        app.bind(shared_slider_values=on_shared_change)


    # expose le slider si besoin
    container.slider = slider
    container.value_label = value_label

    return container



class HomeScreen(Screen):
    ''' ÉCRAN D’ACCUEIL '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initialisation des variables
        self.last_bpm = None
        self.websocket_server = None
        self.seconds_elapsed = 0
        self.chrono_event = None

        # listes vides pour les timestamps
        self.list_timestamp_envoi = list()
        self.list_timestamp_recep = list()
        self.list_latence = list()
        self.list_count = list()
        self.ID_message_recep = None
        self.ID_message_envoi = 0
        self.list_ID_message_recep = list()
        self.list_perte = list()
        self.list_size_message = list()
        self.list_bandwidth = list()

        # Conteneur principal
        main_layout = BoxLayout(
            orientation='vertical',
            spacing=20,
            padding=40)

        # --- TOP: Logo et titre ---
        top_section = create_icon_label_row(
            "images/heart-rate-monitor.png",
            "Heart Rate Monitor",
            font_size=40
        )
        main_layout.add_widget(top_section)

        # --- MIDDLE : Data ---
        data_section = AnchorLayout(
            anchor_x='center',
            anchor_y='center',
            size_hint=(1, 0.4)
        )

        data_box = BoxLayout(
            orientation='vertical',
            spacing=dp(50),
            size_hint=(None, None)
        )

        # Crée la zone pour les data bpm
        bpm_box = BoxLayout(
            orientation='horizontal',
            spacing=dp(100),
            size_hint=(None, None),
            pos_hint={'center_x': 0.5}  # CENTRAGE horizontal
        )

        # Crée les paires icône + label
        heart_row = create_icon_label_row(
            "images/heart.png",
            "-- bpm",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="heart_rate_label"
        )

        send_heart_row = create_icon_label_row(
            "images/letter.png",
            "-- bpm",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="heart_send_label"
        )

        chrono_row = create_icon_label_row(
            "images/chrono.png",
            "00:00",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="chrono_label"
        )

        statut_row = create_icon_label_row(
            "images/chain.png",
            "Unity déconnecté",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="statut_label"
        )

        # Ajoute les deux data bpm à bpm_box
        bpm_box.add_widget(heart_row)
        bpm_box.add_widget(send_heart_row)

        # On calcule dynamiquement la taille de bpm_box en fonction du contenu
        bpm_box.width = heart_row.width + send_heart_row.width + bpm_box.spacing
        bpm_box.height = max(heart_row.height, send_heart_row.height)

        # Ajoute à data_box
        data_box.add_widget(bpm_box)
        data_box.add_widget(chrono_row)
        data_box.add_widget(statut_row)


        # Ajoute à data section
        data_section.add_widget(data_box)

        main_layout.add_widget(data_section)


        # --- BOTTOM: Boutons ---
        bottom_section = AnchorLayout(
            anchor_x='center',
            anchor_y='bottom',
            size_hint=(1, 0.2)
        )
        btn_box = BoxLayout(
            orientation='vertical',
            spacing=20,
            size_hint=(0.8, None)
        )

        # ToggleButton START/STOP
        self.start_ws_button = ToggleButton(
            text="START",
            background_normal='',
            background_down='',
            size_hint=(1, None),
            height=100,
            background_color=get_color_from_hex("#388E3C"), # vert doux
            font_size=25
        )
        self.start_ws_button.bind(on_press=self.on_toggle)
        btn_box.add_widget(self.start_ws_button)

        # Autres boutons
        btn_box.add_widget(create_rounded_button("Connexion du capteur", self.go_to_scan))
        btn_box.add_widget(create_rounded_button("Evolution de la FC", self.go_to_progress))
        btn_box.add_widget(create_rounded_button("Paramètres", self.go_to_settings))

        btn_box.add_widget(create_rounded_button("Save Data", self.save_data_button_callback))


        bottom_section.add_widget(btn_box)

        main_layout.add_widget(bottom_section)

        # Ajouter tous les widgets au conteneur principal
        self.add_widget(main_layout)


    def on_toggle(self, instance):
        instance.text = "STOP" if instance.state == 'down' else "START"

        if instance.state == 'down':
            print("🟢 Serveur activé")
            instance.background_color = get_color_from_hex("#C62828") # Rouge
            self.start_server_asyn()
            self.start_measurement()
        else:
            print("🔴 Serveur désactivé")
            instance.background_color = get_color_from_hex("#388E3C")  # Vert
            self.stop_server()
            self.update_send_hr("--")
            self.stop_measurement()

    def start_server_asyn(self):
        asyncio.ensure_future(self.start_server())

    async def start_server(self): # lance le serveur WS
        if self.websocket_server is None:
            self.websocket_server = await websockets.serve(
                partial(self.websocket_handler, path="/"), HOST, PORT
            )
            print("✅ Serveur WebSocket démarré")
        else:
            print("⚠️ Serveur déjà actif")

    async def stop_server(self):
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()
            self.websocket_server = None
            print("🛑 Serveur WebSocket arrêté")
        else:
            print("⚠️ Aucun serveur à arrêter")

    def start_measurement(self, *args):
        self.seconds_elapsed = 0
        self.update_chrono_label(0)
        self.chrono_event = Clock.schedule_interval(
            self.update_chrono,
            1
        )

    def stop_measurement(self, *args):
        if self.chrono_event:
            self.chrono_event.cancel()
            self.chrono_event = None
        self.chrono_label.text = "00:00"

    def update_chrono(self, dt):
        self.seconds_elapsed += 1
        self.update_chrono_label(self.seconds_elapsed)

    def update_chrono_label(self, seconds):
        minutes = seconds // 60
        seconds = seconds % 60
        self.chrono_label.text = f"{minutes:02d}:{seconds:02d}"

    async def websocket_handler(self, websocket, path): # appelé quand un cient WS se connecte
        clients.add(websocket)
        try:
            async for message in websocket: # ecoute les messages entrant de Unity
                print(f"📩 Message reçu depuis Unity : {message}")

                # 1ère partie du message = ID
                self.ID_message_recep = int(message.split(":")[0])

                # 2ème partie du message = timestamp reception
                self.timestamp_recep = float(message.split(":")[1])

                if self.ID_message_recep == self.ID_message_envoi:

                    # ajout du moment de l'envoie à la liste
                    self.list_timestamp_envoi.append(self.timestamp_envoi)
                    print(f"nb timestamp envoi : {len(self.list_timestamp_envoi)}")

                    # ajout de l'ID du message reçu dans Unity à la liste
                    self.list_ID_message_recep.append(self.ID_message_recep)

                    # ajout du moment de réception dans Unity à la liste
                    self.list_timestamp_recep.append(self.timestamp_recep)
                    print (f"nb timestamp reception : {len(self.list_timestamp_recep)}")

                    # ajout du taux de perte à la liste
                    self.list_perte.append(((self.ID_message_envoi-len(self.list_timestamp_recep))/self.ID_message_envoi)*100)

                    # Ajout de la taille des messages envoyés à la liste
                    self.list_size_message.append(self.message_size_kbits)
                    print (f"taille message : {self.message_size_kbits} kbit")

                    # Ajout de la bande passante (kbit) à la liste
                    self.list_bandwidth.append(self.message_size_kbits/(self.timestamp_recep-self.timestamp_envoi))
                    print (f"bande passante : {self.list_bandwidth[-1]} kbit/s")


        except websockets.ConnectionClosed as e:
            print(f"⚠️ Unity s'est déconnecté : {e}")
        finally:
            clients.remove(websocket) # retire le client une fois déconnecté

    def send_ip(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            message = f"IP:{self.get_ip()}"
            message = message.encode()
            sock.sendto(message, (BROADCAST_IP, UDP_PORT))
            print(f"📡 Message envoyé en broadcast : {message.decode()} vers {BROADCAST_IP}:{UDP_PORT}")
        except Exception as e:
            print(f"⚠️ Erreur lors de l'envoi UDP : {e}")

    def get_ip(self): # récupère l'IP locale en se connectivement fictivement à un serveur externe
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip

    async def send_data_to_clients(self, heart_rate):
        if not clients:
            print("❌ Aucun client WebSocket connecté !")
            self.update_send_hr("--")
            self.statut_label.text = 'Unity déconnecté'

            # Envoie de l'adresse IP de l'appareil maître à Unity via UDP
            self.send_ip()
            return

        if clients:

            # Incrémente de 1 l'ID message envoyé
            self.ID_message_envoi += 1
            message = f"{str(self.ID_message_envoi)}:{str(heart_rate)}"

            message_size_bytes = len(message.encode("utf-8"))  # taille en octets
            self.message_size_kbits = (message_size_bytes * 8) / 1000  # taille en kilobits
            message_size_mbits = self.message_size_kbits / 1000  # taille en mégabits
            print(f"Taille du message : {message_size_bytes} octets ≈ {self.message_size_kbits:.3f} kb")


            # Calcul du moment de l'envoi
            self.timestamp_envoi = time.time()

            print(f"{message} bpm, timestamp_envoi : {self.timestamp_envoi}")

            # Mise à jour sur l'écran d'accueil
            self.update_send_hr(message)
            self.statut_label.text = 'Unity connecté'

            # Envoie du message à Unity via WebSocket
            await asyncio.gather(*[client.send(message) for client in clients])

    def start_ble_scan(self, instance):
        asyncio.ensure_future(self.scan_ble())

    def go_to_scan(self, instance):
        ''' Change l'écran affiché par le ScreenManger'''
        self.manager.current = 'scan'

    def go_to_progress(self, instance):
        ''' Change l'écran affiché par le ScreenManger'''
        self.manager.current = 'progress'

    def go_to_settings(self, instance):
        ''' Change l'écran affiché par le ScreenManger'''
        self.manager.current = 'settings'

    def update_heart_rate(self, bpm):
        self.heart_rate_label.text = f"{bpm} bpm"

        if not bpm == "--":
            if self.last_bpm is not None:
                if bpm > self.last_bpm:
                    # Clignote en rouge (augmentation)
                    anim = Animation(color=(1, 0, 0, 1), duration=0.2) + Animation(color=(1, 1, 1, 1), duration=0.5)
                elif bpm < self.last_bpm:
                    # Clignote en bleu (diminution)
                    anim = Animation(color=(0.2, 0.5, 1, 1), duration=0.2) + Animation(color=(1, 1, 1, 1), duration=0.5)
                else:
                    # Pas de changement → pas d'animation
                    anim = None

                if anim:
                    anim.start(self.heart_rate_label)

            self.last_bpm = bpm

    def update_send_hr(self, bpm):
        self.heart_send_label.text = f"{bpm} bpm"


    def open_save_dialog(self, on_select_callback):
        """ Ouvre une popup pour choisir un dossier de sauvegarde """
        content = BoxLayout(orientation='vertical', spacing=10)

        file_chooser = FileChooserListView(path='.', dirselect=True)
        content.add_widget(file_chooser)

        def on_validate(instance):
            if file_chooser.selection:
                selected_folder = file_chooser.selection[0]
                popup.dismiss()
                on_select_callback(selected_folder)

        validate_button = Button(text="Choisir ce dossier", size_hint=(1, None), height=50)
        validate_button.bind(on_release=on_validate)

        content.add_widget(validate_button)

        popup = Popup(title="Choisir un dossier de sauvegarde",
                      content=content,
                      size_hint=(0.9, 0.9))
        popup.open()

    # Exemple de fonction à appeler pour sauvegarder
    def save_data_button_callback(self, instance):
        def save_to_folder(folder_path):

            # Calcul de la latence et mise en liste
            latences = [(recep - envoi) * 1000 for envoi, recep in
                        zip(self.list_timestamp_envoi, self.list_timestamp_recep)]

            nb_timestamp_envoi = len(self.list_timestamp_envoi)
            nb_timestamp_recep = len(self.list_timestamp_recep)

            print(f"nb timestamp envoi : {nb_timestamp_envoi}")
            print(f"nb timestamp recep : {nb_timestamp_recep}")
            print(f"nb liste latence : {len(latences)}")
            print(f"nb liste perte : {len(self.list_perte)}")
            print(f"nb liste ID message reçu : {len(self.list_ID_message_recep)}")
            print(f"nb liste taille message : {len(self.list_size_message)}")
            print(f"nb liste bande passante : {len(self.list_bandwidth)}")


            # Création du DataFrame
            df = pd.DataFrame({
                "Timestamp Envoi (s)": self.list_timestamp_envoi,
                "Timestamp Reception (s)": self.list_timestamp_recep,
                "Latence (ms)": latences,
                "ID ordre reception":self.list_ID_message_recep,
                "Taux de perte (%)": self.list_perte,
                "Taille du message (kbit)": self.list_size_message,
                "Bande passante (kbit/s)": self.list_bandwidth
            })

            # Nom de base du fichier
            base_filename = "results_perfs_websocket"
            file_ext = ".csv"
            i = 1

            # Cherche un nom de fichier disponible
            while True:
                file_path = os.path.join(folder_path, f"{base_filename}_{i}{file_ext}")
                if not os.path.exists(file_path):
                    break
                i += 1

            # Sauvegarde CSV avec le nom incrémenté
            df.to_csv(file_path, index=False, float_format='%.6f')
            print(f"Données sauvegardées dans : {file_path}")

        self.open_save_dialog(save_to_folder)

class ScanScreen(Screen):
    ''' ECRAN DU SCAN BLUETOOTH '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initialisation des variables
        self.device_spinner = None  # menu déroulant pour afficher les appareils détectés
        self.last_bpm = None
        self.devices = None
        self.client = None
        self.heart_rate_data = 50 # valeur par defaut

        # Conteneur principal
        main_layout = BoxLayout(
            orientation='vertical',
            padding=40,
            spacing=20
        )

        # --- TOP: Logo et titre ---
        top_section = create_icon_label_row(
            "images/bluetooth.png",
            "Scan Bluetooth",
            font_size=30
        )
        main_layout.add_widget(top_section)

        # --- MIDDLE 1: Data FC et Battery ---
        data_section = AnchorLayout(
            anchor_x='center',
            anchor_y='center',
            size_hint=(1, 0.2)
        )
        data_box = BoxLayout(
            orientation='horizontal',
            spacing=dp(100),
            size_hint=(None, None),
        )

        # Crée les paires icône + label
        heart_row = create_icon_label_row(
            "images/heart.png",
            "-- bpm",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="heart_rate_label"
        )

        battery_row = create_icon_label_row(
            "images/battery.png",
            "-- %",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="battery_label"
        )

        # Ajoute les deux blocs à data_box
        data_box.add_widget(heart_row)
        data_box.add_widget(battery_row)

        # On calcule dynamiquement la taille de data_box en fonction du contenu
        data_box.width = heart_row.width + battery_row.width + data_box.spacing
        data_box.height = max(heart_row.height, battery_row.height)

        # Ajoute à data_section
        data_section.add_widget(data_box)
        main_layout.add_widget(data_section)

        # --- BOTTOM: Boutons ---
        bottom_section = AnchorLayout(
            anchor_x='center',
            anchor_y='bottom',
            size_hint=(1, 0.2)
        )
        bottom_box = BoxLayout(
            orientation='vertical',
            spacing=200,
            size_hint=(0.8, None)
        )

        btn_scan_box = BoxLayout(
            orientation='vertical',
            spacing=20,
            size_hint=(1, None)
        )

        # Crée boutons
        scan_button = create_rounded_button("SCAN", self.start_ble_scan, background_color=get_color_from_hex("#388E3C"))
        self.device_spinner = Spinner(
            text="...",
            values=[],
            size_hint=(1, None),
            font_size=20
            # background_normal='',  # enlève l'image de fond par défaut
            # background_color=get_color_from_hex("#66BB6A")  # Indigo par exemple
        )
        self.device_spinner.bind(text=self.on_device_selected)
        back_button = create_rounded_button("Retour", self.go_back)

        # Ajoute au btn_box
        btn_scan_box.add_widget(scan_button)
        btn_scan_box.add_widget(self.device_spinner)

        # Ajoute au bottom_box
        bottom_box.add_widget(btn_scan_box)
        bottom_box.add_widget(back_button)

        # Ajoute au bottom_section
        bottom_section.add_widget(bottom_box)

        main_layout.add_widget(bottom_section)

        self.add_widget(main_layout)


    def go_back(self, instance):
        self.manager.current = 'home'

    def start_ble_scan(self, instance):
        asyncio.ensure_future(self.scan_ble())

    def update_ui_after_scan(self):
        if not self.devices:
            self.device_spinner.text = "Aucun appareil trouvé. Réessayez"
            self.device_spinner.values = []
        else:
            self.device_spinner.text = f"{len(self.devices)} appareil(s) trouvé(s)"
            self.device_spinner.values = [f"{d.name} ({d.address})" for d in self.devices]

    async def scan_ble(self):
        if self.client :
            self.device_spinner.text = "Déconnexion en cours..."
            await self.client.disconnect()

            self.update_heart_rate("--")
            self.update_battery("--")

            # Mise à jour sur l'écran d'accueil
            home_screen = self.manager.get_screen('home')
            home_screen.update_heart_rate("--")

        self.device_spinner.text = "Scan en cours..."
        scanned_devices = await bleak.BleakScanner.discover(3)
        self.devices = [d for d in scanned_devices if any(brand in (d.name or "") for brand in TARGET_DEVICES)]
        self.update_ui_after_scan()

    def on_device_selected(self, spinner, text):
        if text and self.devices:
            selected_device = next((d for d in self.devices if f"{d.name} ({d.address})" == text), None)
            if selected_device:
                asyncio.create_task(self.connect_to_device(selected_device))

    async def connect_to_device(self, device):
        self.device_spinner.text = f"Connexion en cours à {device.name}..."

        try:
            async with bleak.BleakClient(device) as self.client:
                self.device_spinner.text = f"Connexion à {device.name} réussie !"

                if HEART_RATE_UUID in [char.uuid for service in self.client.services for char in
                                       service.characteristics]:
                    print(f"🔊 {device.name} diffuse des données de FC !")

                    # Vérification de la présence de la caractéristique BATTERY_LEVEL
                    if CHAR_BATTERY_LEVEL in [char.uuid for service in self.client.services for char in
                                              service.characteristics]:
                        battery_level = await self.client.read_gatt_char(CHAR_BATTERY_LEVEL)
                        battery_percentage = battery_level[0]  # Le niveau de la batterie est un octet
                        print(f"🔋 {battery_percentage}%")
                        self.update_battery(battery_percentage)

                    async def callback(sender, data):
                        heart_rate = int(data[1])
                        print(f"❤️ {heart_rate} BPM")

                        # Mise à jour sur l'écran d'accueil
                        home_screen = self.manager.get_screen('home')
                        home_screen.update_heart_rate(heart_rate)
                        # Mise à jour sur l'écran actuel et sur le graphique
                        self.update_heart_rate(heart_rate)

                        if home_screen.start_ws_button.state == 'down':
                            print("✅ Websocket activé.")
                            home_screen.send_ip()
                            await home_screen.send_data_to_clients(heart_rate)
                        else:
                            print("❌ WebSocket désactivé")


                    await self.client.start_notify(HEART_RATE_UUID, callback)

                    # Boucle infinie pour garder la connexion active
                    while True:
                        await asyncio.sleep(1)
                else:
                    self.device_spinner.text = f"{device.name} ne diffuse pas de données de FC !"
        except bleak.exc.BleakError as e:
            self.device_spinner.text = f"Erreur : {e}"

    def update_heart_rate(self, bpm):
        self.heart_rate_label.text = f"{bpm} bpm"
        self.heart_rate_data = bpm # pour le graphique
        if not bpm == "--":
            if self.last_bpm is not None:
                if bpm > self.last_bpm:
                    # Clignote en rouge (augmentation)
                    anim = Animation(color=(1, 0, 0, 1), duration=0.2) + Animation(color=(1, 1, 1, 1), duration=0.5)
                elif bpm < self.last_bpm:
                    # Clignote en bleu (diminution)
                    anim = Animation(color=(0.2, 0.5, 1, 1), duration=0.2) + Animation(color=(1, 1, 1, 1), duration=0.5)
                else:
                    # Pas de changement → pas d'animation
                    anim = None

                if anim:
                    anim.start(self.heart_rate_label)

            self.last_bpm = bpm

    def update_battery(self, level):
        self.battery_label.text = f"{level} %"

class ProgressScreen(Screen):
    def __init__(self, scan_screen, **kwargs):
        super().__init__(**kwargs)

        # Conteneur principal
        main_layout = BoxLayout(
            orientation='vertical',
            padding=40,
            spacing=20
        )

        # --- TOP: Logo et titre ---
        top_section = create_icon_label_row(
            "images/discount.png",
            "Evolution de la FC",
            font_size=30
        )
        main_layout.add_widget(top_section)

        # --- MIDDLE : Graphique ---
        graph_section = AnchorLayout(
            anchor_x='center',
            anchor_y='center',
            size_hint=(1, 0.4)
        )

        # Graphique (class RealTimeGraph)
        self.graph = RealTimeGraph(scan_screen)

        graph_section.add_widget(self.graph)

        main_layout.add_widget(graph_section)

        # --- BOTTOM : Button ---
        back_button = create_rounded_button("Retour", self.go_back, size_hint=(0.8, None))

        main_layout.add_widget(back_button)

        # Ajout du main_layout à l'écran
        self.add_widget(main_layout)

    def go_back(self, instance):
        self.manager.current = 'home'


class RealTimeGraph(BoxLayout):
    ''' GRAPHIQUE EN TEMPS REEL DE LA FC'''
    def __init__(self, scan_screen, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.scan_screen = scan_screen  # 🔗 lien vers ScanScreen

        # Initialisation des variables
        self.data_hr = [] # liste des données FC en temps reel
        self.data_target_hr = []
        self.time = 0
        self.target_hr = 50  # 🎯 %FCMax cible (par defaut)
        self.last_bpm = None
        self.age = 25
        self.maxHR = 211 - (self.age * 0.64) # demander à Jos pour la formule

        # Box du graphique (data + graph + Slider)
        graph_box = BoxLayout(
            orientation='vertical',
            spacing=dp(30),
            size_hint=(1, 0.5)
        )

        # Crée la zone pour les data bpm
        bpm_box = BoxLayout(
            orientation='horizontal',
            spacing=dp(100),
            size_hint=(None, None),
            pos_hint={'center_x': 0.5}  # CENTRAGE horizontal
        )

        # Crée les paires icône + label
        heart_row = create_icon_label_row(
            "images/heart.png",
            "-- bpm",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="heart_rate_label"
        )

        target_row = create_icon_label_row(
            "images/target3.png",
            "-- bpm",
            screen_instance=self,
            font_size=40,
            icon_size=(45, 45),
            is_dynamic=True,
            ref="target_label"
        )

        # Ajoute les deux data bpm à bpm_box
        bpm_box.add_widget(heart_row)
        bpm_box.add_widget(target_row)

        # On calcule dynamiquement la taille de bpm_box en fonction du contenu
        bpm_box.width = heart_row.width + target_row.width + bpm_box.spacing
        bpm_box.height = max(heart_row.height, target_row.height)


        ## --- Graphique ---
        self.graph = Graph(xlabel='Time (s)', ylabel='FCmax (%)',
                           size_hint = (1, 1), opacity =1,
                           x_ticks_minor=1, x_ticks_major=60, # intervalles de graduation
                           y_ticks_minor=1, y_ticks_major=10, # intervalles de graduation
                           y_grid_label=True, x_grid_label=True, # labels des axes
                           padding=5, # espacement entre axe et label
                           x_grid=False, y_grid=True, # affiche les grilles
                           xmin=0, xmax=600, ymin=0, ymax=100) # plages des axes

        # Crée la courbe FC cible
        self.target_line = LinePlot(color=get_color_from_hex("#42A5F5"), line_width=3)
        self.graph.add_plot(self.target_line)

        # Créé la courbe FC
        self.plot = LinePlot(color=[1, 0, 0, 1], line_width=3)
        self.graph.add_plot(self.plot)

        # --- Slider de %FC cible ---
        hr_target_slider = create_icon_slider(
            icon_left_path="images/snowflake.png",
            icon_right_path="images/hot-deal.png",
            min_val=0,
            max_val=100,
            step=1,
            initial=50,
            unit=" %",
            sync_key="hr_target"
        )
        # Récupère la valeur du slider
        self.target_hr = hr_target_slider.slider.value

        self.target_label.text = f"{self.target_hr:.0f} %"

        # Utiliser la valeur du slider dans une fonction
        hr_target_slider.slider.bind(value=self.on_slider_value_change)

        # ajout au graph_box
        graph_box.add_widget(bpm_box)
        graph_box.add_widget(self.graph)
        graph_box.add_widget(hr_target_slider)

        # ajout du graph au layout
        self.add_widget(graph_box)

        # Appel toutes les secondes
        Clock.schedule_interval(self.update_graph, 1)

    def on_slider_value_change(self, instance, value):
        self.target_hr = value
        self.target_label.text = f"{value:.0f} %"
        # Envoie de FC cible dans Unity via UDP
        self.send_target_hr()

    def send_target_hr(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            message = f"target_hr:{self.target_hr:.0f}"
            print (message)
            message = message.encode()
            sock.sendto(message, (BROADCAST_IP, UDP_PORT))
            print(f"📡 Message envoyé en broadcast : {message.decode()} vers {BROADCAST_IP}:{UDP_PORT}")
        except Exception as e:
            print(f"⚠️ Erreur lors de l'envoi UDP : {e}")

    def update_graph(self, dt): # dt = délai depuis le dernier appel
        '''Fonction appelée pour mettre à jour le graphique'''

        HR = self.scan_screen.heart_rate_data  # 🔄 récupère la FC en temps réel

        # Convertir en % de FCmax
        hr = (HR/self.maxHR)*100

        # Mise à jour du label
        self.update_heart_rate(HR)

        self.data_hr.append((self.time, hr))
        self.time += 1

        # Gestion de la taille de la fenêtre de données
        # Garde seulement les 10 dernières minutes à l'écran
        if len(self.data_hr) > 600:
            self.data_hr = self.data_hr[-600:]
            self.graph.xmin = self.data_hr[0][0]
            self.graph.xmax = self.data_hr[-1][0]

        # mise à jour des points affichés dans le graphique
        self.plot.points = self.data_hr

        # Mise à jour de la courbe %FCMax cible
        self.data_target_hr.append((self.time,self.target_hr))
        self.target_line.points = self.data_target_hr


    def update_heart_rate(self, bpm):
        self.heart_rate_label.text = f"{bpm} bpm"
        if not bpm == "--":
            if self.last_bpm is not None:
                if bpm > self.last_bpm:
                    # Clignote en rouge (augmentation)
                    anim = Animation(color=(1, 0, 0, 1), duration=0.2) + Animation(color=(1, 1, 1, 1), duration=0.5)
                elif bpm < self.last_bpm:
                    # Clignote en bleu (diminution)
                    anim = Animation(color=(0.2, 0.5, 1, 1), duration=0.2) + Animation(color=(1, 1, 1, 1), duration=0.5)
                else:
                    # Pas de changement → pas d'animation
                    anim = None

                if anim:
                    anim.start(self.heart_rate_label)

            self.last_bpm = bpm

# class ScrollableGraph(Graph):
#     ''' Permet de scroller dans le graphique'''
#     def __init__(self, **kwargs):
#         super().__init__(**kwargs)
#         self.dragging = False
#         self.last_touch_x = 0
#
#     def on_touch_down(self, touch):
#         if self.collide_point(*touch.pos):
#             self.dragging = True
#             self.last_touch_x = touch.x
#             return True
#         return super().on_touch_down(touch)
#
#     def on_touch_move(self, touch):
#         if self.dragging:
#             dx = touch.x - self.last_touch_x
#             range_x = self.xmax - self.xmin
#             shift = -dx / self.width * range_x  # déplacement proportionnel
#             self.xmin += shift
#             self.xmax += shift
#             self.last_touch_x = touch.x
#             return True
#         return super().on_touch_move(touch)
#
#     def on_touch_up(self, touch):
#         self.dragging = False
#         return super().on_touch_up(touch)



class GradientSlider(Slider):
    ''' WIDGET SLIDER (barre coulissante)'''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gradient_texture = self.create_gradient_texture()
        self.background_horizontal = '' # retire l'image de fond (fond blanc)
        self.background_disabled_horizontal = ''
        self.background_width = 0  # S'assure que rien n'est dessiné par défaut
        self.cursor_image = 'images/target_moove.png'
        self.cursor_size = (150, 150)

    def create_gradient_texture(self):
        '''génère une texture en dégradé bleu vers rouge'''
        # Crée une texture en mémoire de 256 pixels de large, 1 pixel de haut
        texture = Texture.create(size=(256, 1), colorfmt='rgba') # format rouge, vert, bleu, alpha

        # liste pour stocker les valeurs couleurs de chaque pixel
        buf = []
        # Transition fluide du bleu (0,0,255) vers le rouge (255,0,0) sur les 256 pixels
        for x in range(256):
            r = int(255 * (x / 255.0))  # 🔴 Rouge augmente
            g = 0  # 🟢 Vert reste à 0
            b = int(255 * (1 - x / 255.0))  # 🔵 Bleu diminue
            a = 230  # Alpha = opaque
            buf.extend([r, g, b, a])

        buf = bytes(buf)  # ✅ conversion en bytes

        # application des données couleurs à la texture
        texture.blit_buffer(buf, colorfmt='rgba', bufferfmt='ubyte')
        texture.wrap = 'repeat' # permet de répéter la texture si nécessaire
        texture.uvsize = (1, -1) # inverse l'axe vertical

        return texture

    def on_size(self, *args):
        ''' Redimensionne le fond à chaque changement de taille du widget'''
        self.canvas.before.clear() # efface tout

        # Redessine un rectangle qui occupe tout l'espace du slider
        with self.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(1, 1, 1, 1)
            Rectangle(texture=self.gradient_texture, pos=self.pos, size=self.size)


class SettingsScreen(Screen):
    ''' ECRAN PARAMETRES'''
    def __init__(self, scan_screen, **kwargs):
        super().__init__(**kwargs)

        # Conteneur principal
        main_layout = BoxLayout(
            orientation='vertical',
            padding=40,
            spacing=20
        )

        # --- TOP: Logo et titre ---
        top_section = create_icon_label_row(
            "images/workflow.png",
            "Paramètres",
            font_size=30
        )
        main_layout.add_widget(top_section)

        # --- MIDDLE : Data Input ---
        data_section = AnchorLayout(
            anchor_x='center',
            anchor_y='center',
            size_hint=(1, 0.2)
        )

        data_box = BoxLayout(
            orientation='vertical',
            spacing=dp(200),
            size_hint=(1, None)
        )

        perso_box = BoxLayout(
            orientation='vertical',
            spacing=dp(10),
            size_hint=(1, None)
        )

        level_ap_box = BoxLayout(
            orientation='vertical',
            spacing=dp(10),
            size_hint=(1, None)
        )

        # Crée les labels sous-titre
        info_perso_label = Label(
            text='PROFIL',
            bold=True,  # gras
            font_size=30,
            color=(1, 1, 1, 1)
        )

        activity_level_label = Label(
            text="NIVEAU D'ACTIVITE PHYSIQUE",
            bold=True,  # gras
            font_size=30,
            color=(1, 1, 1, 1)
        )


        # Crée les Sliders
        age_slider = create_icon_slider(
            icon_left_path="images/baby.png",
            icon_right_path="images/old-man.png",
            min_val=0,
            max_val=100,
            step=1,
            initial=10,
            unit=" ans"
        )

        poids_slider = create_icon_slider(
            icon_left_path="images/butterfly.png",
            icon_right_path="images/elephant.png",
            min_val=20,
            max_val=100,
            step=1,
            initial=40,
            unit=" kg"
        )

        hr_target_slider = create_icon_slider(
            icon_left_path="images/snowflake.png",
            icon_right_path="images/hot-deal.png",
            min_val=0,
            max_val=100,
            step=1,
            initial=50,
            unit=" %",
            sync_key="hr_target"
        )

        # crée le toggle button (obstacle)
        self.obs_button = ToggleButton(
            text="Obstacle activé",
            background_normal='',
            background_down='',
            size_hint=(0.3, None),
            height=100,
            background_color=get_color_from_hex("#388E3C"), # vert doux
            font_size=25,
            pos_hint={'center_x': 0.5}  # CENTRAGE horizontal
        )
        self.obs_button.bind(on_press=self.on_toggle)

        # Ajout dans perso_box
        perso_box.add_widget(info_perso_label) # sous-titre
        perso_box.add_widget(age_slider) # slider âge
        perso_box.add_widget(poids_slider) # slider poids

        # Ajout dans level_ap_box
        level_ap_box.add_widget(activity_level_label) # sous-titre
        level_ap_box.add_widget(hr_target_slider) # slider de %FCmax cible
        level_ap_box.add_widget(self.obs_button) # bouton option obstacle

        # Ajout à data_box
        data_box.add_widget(perso_box)
        data_box.add_widget(level_ap_box)

        # ajuste automatiquement la taille du data_box
        data_box.bind(minimum_height=data_box.setter('height'))

        # # --- Astuce pour visualiser la zone des box ---
        # with data_box.canvas.before:
        #     Color(0, 1, 0, 0.2)
        #     self.bg_rect = Rectangle(pos=data_box.pos, size=data_box.size)
        #
        # # Met à jour la position/taille du rectangle à chaque changement du box
        # data_box.bind(pos=lambda instance, value: setattr(self.bg_rect, 'pos', value))
        # data_box.bind(size=lambda instance, value: setattr(self.bg_rect, 'size', value))
        # # ----------prend en compte le dernier widget ajouté---------------------

        # Ajout à data_section
        data_section.add_widget(data_box)
        main_layout.add_widget(data_section)

        # --- BOTTOM : Button ---
        back_button = create_rounded_button("Retour", self.go_back, size_hint=(0.8, None))

        main_layout.add_widget(back_button)

        # Ajout du main_layout à l'écran
        self.add_widget(main_layout)

    def on_toggle(self, instance):
        instance.text = "Obstacle désactivé" if instance.state == 'down' else "Obstacle activé"

        if instance.state == 'down':
            print("🔴 Obstacle désactivé")
            instance.background_color = get_color_from_hex("#C62828") # Rouge
            # ajouter ici l'envoie UDP de la commande pour désactiver les obstacles
        else:
            print("🟢 Obstacle activé")
            instance.background_color = get_color_from_hex("#388E3C")  # Vert
            # ajouter ici l'envoie UDP de la commande pour activer les obstacles


    def go_back(self, instance):
        self.manager.current = 'home'



class HeartRateMonitorApp(App):
    ''' CONSTRUCTION DE L'APPLICATION '''
    shared_slider_values = DictProperty({})

    def build(self):
        sm = ScreenManager()

        scan_screen = ScanScreen(name='scan') # utilisé pour envoyer les data hr dans le graphique
        progress_screen = ProgressScreen(scan_screen=scan_screen, name='progress')
        settings_screen = SettingsScreen(scan_screen=scan_screen, name='settings')

        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(scan_screen)
        sm.add_widget(progress_screen)
        sm.add_widget(settings_screen)

        return sm

async def main(app):
    await app.async_run("asyncio")

if __name__ == '__main__':
    Logger.setLevel(logging.DEBUG)
    app = HeartRateMonitorApp()
    asyncio.run(main(app))