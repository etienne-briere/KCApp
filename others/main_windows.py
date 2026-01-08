from kivy.app import App

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.uix.slider import Slider
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior

from kivy.graphics import Line, Color, InstructionGroup, Rectangle, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.properties import NumericProperty, DictProperty, StringProperty
from kivy.logger import Logger

import logging

from libs.kivy_garden.graph import Graph, MeshLinePlot, LinePlot # récupérée en local

import asyncio
import threading
import io
import bleak
import socket
import websockets
import os
import sys
from PIL import Image as PILImage
import ipaddress
import time
from functools import partial

#=======================================================================================================================
#                                             POUR DEPLOYER SOUS WINDOWS
#=======================================================================================================================
def resource_path(relative_path):
    """
    Récupère le chemin absolu vers un fichier de ressource (image, .kv, etc.),
    compatible avec PyInstaller (notamment en mode --onefile).
    """
    try:
        # PyInstaller stocke les fichiers extraits dans un répertoire temporaire
        base_path = sys._MEIPASS
    except Exception:
        # En développement, on utilise le répertoire courant
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)













#=======================================================================================================================
#                                             INITIALISATION DES PARAMETRES
#=======================================================================================================================
logging.Logger.manager.root = Logger # intérêt ?

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
UDP_PORT_SEND = 5003
UDP_PORT_RECEIVE = 5006

#=======================================================================================================================
#                                                  COMPOSANTS
#=======================================================================================================================
class RoundedButton(ButtonBehavior, BoxLayout):
    '''Créer un bouton personnalisable avec coin arrondis'''

    def __init__(self, text, on_press, background_color=(0.2, 0.6, 0.86, 1), radius=10, **kwargs):
        super().__init__(orientation='vertical', padding=10, **kwargs)
        self.background_color = background_color
        self.radius = radius
        self.label = Label(text=text,
                           color=(1,1,1,1), # blanc
                           font_size=25,
                           halign='center', # centré horizontalement
                           valign='middle' # centré verticalement
                           )
        self.label.bind(size=self.label.setter('text_size')) # texte se réajuste à la taille du label (centrage propre)
        self.add_widget(self.label) # ajout dans le BoxLayout
        self.on_press_callback = on_press

        # Dessin du fond arrondi
        with self.canvas.before:
            Color(*background_color)
            self.rect = RoundedRectangle(size=self.size, pos=self.pos, radius=[radius])
        self.bind(pos=self.update_rect, size=self.update_rect) # ajuste la taille et position du rectangle si le bouton est redimensionné

    def update_rect(self, *args):
        '''Ajuste la position et la taille du rectangle quand le widget est redimensionné'''
        self.rect.pos = self.pos
        self.rect.size = self.size

    def on_press(self):
        if self.on_press_callback:
            self.on_press_callback(self)


class RoundedToggleButton(ToggleButtonBehavior, BoxLayout):
    ''' Créer un ToggleBouton avec coin arrondis'''

    sync_key = StringProperty(None)  # Clé de synchronisation

    def __init__(self,
                 text_start="Désactivé",
                 text_stop="Activé",
                 background_color=get_color_from_hex("#D32F2F"),  # vert
                 background_down=get_color_from_hex("#388E3C"),  # rouge
                 font_size=25, radius=10, # radius gère l'arrondi des coins
                 sync_key=None,
                 **kwargs):
        super().__init__(orientation='vertical', padding=10, **kwargs)

        self.text_start = text_start
        self.text_stop = text_stop
        self.background_color = background_color
        self.background_down = background_down
        self.radius = radius
        self.sync_key = sync_key

        self.label = Label(
            text=self.text_start,
            color=(1, 1, 1, 1),
            font_size=font_size,
            halign='center',
            valign='middle'
        )
        self.label.bind(size=self.label.setter('text_size'))
        self.add_widget(self.label)

        with self.canvas.before:
            self.bg_color = Color(*self.background_color) # couleur du rectangle
            self.rect = RoundedRectangle(size=self.size, pos=self.pos, radius=[self.radius]) # rectangle de fond

        self.bind(pos=self.update_graphics, size=self.update_graphics)
        self.bind(state=self.on_state)

        # Synchronisation
        if self.sync_key:
            app = App.get_running_app()

            if not hasattr(app, 'shared_toggle_states'):
                app.shared_toggle_states = {} # stock l'état de chaque sync_key

            if self.sync_key not in app.shared_toggle_states:
                app.shared_toggle_states[self.sync_key] = self.state

            # Écoute les changements globaux et maj automatique
            app.bind(shared_toggle_states=self.on_shared_state_change)

    def update_graphics(self, *args):
        '''Redimensionne dynamiquement le toggle'''
        self.rect.pos = self.pos
        self.rect.size = self.size

    def on_state(self, instance, value):
        '''Change le texte et la couleur en fonction de l'état du Toggle'''
        if value == 'down':
            self.bg_color.rgba = self.background_down
            self.label.text = self.text_stop
        else:
            self.bg_color.rgba = self.background_color
            self.label.text = self.text_start

        # Met à jour l'état global si sync_key est définie
        if self.sync_key:
            app = App.get_running_app()
            if app.shared_toggle_states.get(self.sync_key) != value:
                app.shared_toggle_states[self.sync_key] = value

    def on_shared_state_change(self, instance, shared_states):
        ''' Si un autre bouton a changé, on s’aligne '''
        new_state = shared_states.get(self.sync_key)
        if new_state is not None and self.state != new_state:
            self.state = new_state  # modifie l'état
            self.on_state(self, new_state)  # déclenche la logique

            # 🔁 Appelle manuellement les fonctions bindées à on_press / on_release
            if new_state == 'down':
                self.dispatch('on_press') # simule un appui utilisateur pour exécuter la fonction on_press
            else:
                self.dispatch('on_release') # idem pour on_release

class FolderAnimation(Image):
    ''' Affiche une animation image par image depuis un dossier. '''
    def __init__(self, image_folder='images', interval=0.2, loop=True, **kwargs):
        super().__init__(**kwargs)
        self.interval = interval
        self.loop = loop
        self.frame_index = 0
        self.anim = None
        self.set_gif(image_folder, interval=self.interval, loop=self.loop)

    def set_gif(self, image_folder, interval=0.2, loop=True):
        ''' Change le dossier d’animation en direct. '''
        if self.anim:
            self.anim.cancel()

        self.loop = loop  # met à jour la valeur
        all_files = os.listdir(image_folder)
        image_files = [f for f in all_files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        self.frames = sorted([os.path.join(image_folder, f) for f in image_files])

        if not self.frames:
            raise Exception(f"Aucune image trouvée dans {image_folder}")

        self.frame_index = 0
        self.source = self.frames[0]

        self.anim = Clock.schedule_interval(self.next_frame, interval)

    def next_frame(self, dt):
        if self.loop:
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            self.source = self.frames[self.frame_index]
        else:
            if self.frame_index < len(self.frames) - 1:
                self.frame_index += 1
                self.source = self.frames[self.frame_index]
            else:
                # On est à la dernière frame, on stoppe
                if self.anim:
                    self.anim.cancel()
                    self.anim = None

def create_rounded_button(text, on_press, size_hint=(1, None), background_color=(0.2, 0.6, 0.86, 1)):
    ''' Créer un bouton stylisé'''
    return RoundedButton(
        text=text,
        on_press=on_press, # action au clic
        size_hint=size_hint, # prend toute la largeur (1=largeur totale, None = hauteur)
        height=dp(55), # hauteur fixe en px
        background_color=background_color, # bleu
        pos_hint={'center_x': 0.5}
    )

def create_icon_label_row(icon_path, label_text, screen_instance=None, font_size=40, icon_size=(40, 40), is_dynamic=False, ref=None):
    ''' Créer une ligne icon + label'''
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

def create_gif_label_row(gif_path, label_text, interval=0.5, screen_instance=None, font_size=40, gif_size=(40, 40), is_dynamic=False, ref_label=None, ref_gif=None):
    ''' Créer une ligne gif + label'''
    # Layout horizontal centré
    outer_layout = AnchorLayout(
        anchor_x='center',
        anchor_y='center',
        size_hint=(1, None)
    )

    # Row horizontale : gif + label
    row = BoxLayout(
        orientation='horizontal',
        spacing=dp(10), # espacement = 10 pixels adaptés à la densité de l'écran
        size_hint=(None, None),
    )

    # Gif
    gif = FolderAnimation(
        image_folder=gif_path,
        interval=interval,
        size_hint=(None, None),
        size=gif_size,
        allow_stretch=True,
        keep_ratio=True,
        pos_hint={'center_y': 0.3}
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
    row.add_widget(gif)
    row.add_widget(label)

    # Ajuste automatiquement la taille de la row
    def update_row_size(*args):
        row.width = gif.width + dp(10) + label.width
        row.height = max(gif.height, label.height)
        outer_layout.height = row.height

    gif.bind(size=update_row_size)
    label.bind(size=update_row_size)

    # Appelle une fois au début
    update_row_size()

    outer_layout.add_widget(row)

    # # Stocker une référence dynamique si besoin
    # if is_dynamic and ref_label and screen_instance:
    #     setattr(screen_instance, ref_label, label)

    # Stocker les références
    if is_dynamic and screen_instance:
        if ref_label:
            setattr(screen_instance, ref_label, label)
        if ref_gif:
            setattr(screen_instance, ref_gif, gif)

    return outer_layout

def create_icon_slider(icon_left_path, icon_right_path, min_val, max_val, icon_size=(40, 40), step=1.00, initial=None, unit="", sync_key=None, on_validate=None):
    '''
        Crée un composant personnalisé contenant :
        - Deux icônes (gauche et droite) encadrant un Slider horizontal.
        - Un label flottant affichant dynamiquement la valeur du Slider.
        - Un boutton OK pour valider la valeur du Slider, associer à la fonction d'activation
        - La possibilité de synchroniser ce Slider avec un autre via une clé de synchronisation.
        '''

    container = AnchorLayout(
        anchor_x='center',
        anchor_y='center',
        size_hint=(1, None)
    )

    slider_row = BoxLayout(
        orientation='horizontal',
        spacing=dp(10),
        size_hint=(0.9, None),  # Légèrement réduit pour inclure le bouton OK
        height=icon_size[1] + dp(20)
    )

    icon_left = Image(source=icon_left_path, size_hint=(None, None), size=icon_size)
    icon_right = Image(source=icon_right_path, size_hint=(None, None), size=icon_size)

    slider_container = FloatLayout(size_hint=(1, None))

    slider = Slider(
        min=min_val,
        max=max_val,
        value=initial if initial is not None else min_val,
        step=step,
        size_hint=(1, None),
        height=icon_size[1],
        pos_hint={'center_y': 0.2, 'center_x': 0.5}
    )

    value_label = Label(
        text=f"{int(initial)}{unit}",
        size_hint=(None, None),
        font_size=20,
        color=(1, 1, 1, 1),
        pos_hint={'center_y': 0.5},
        bold=True
    )

    def update_label_pos(instance, value):
        if slider.value_pos:
            slider_x, _ = slider.to_widget(*slider.value_pos)
            value_label.center_x = slider_x
        value_label.text = f"{int(value)}{unit}"

    slider.bind(value=update_label_pos)
    slider.bind(size=lambda *a: update_label_pos(slider, slider.value))

    slider_container.add_widget(value_label)
    slider_container.add_widget(slider)

    # ✅ Bouton OK
    ok_button = Button(
        text="OK",
        size_hint=(None, None),
        size=(dp(50), dp(40)),
        on_release=lambda x: on_validate(slider.value) if on_validate else None
    )

    # Composition finale
    slider_row.add_widget(icon_left)
    slider_row.add_widget(slider_container)
    slider_row.add_widget(icon_right)
    slider_row.add_widget(ok_button)

    container.add_widget(slider_row)

    # Synchronisation pour que les autres sliders changent aussi
    if sync_key:
        app = App.get_running_app()
        if sync_key not in app.shared_slider_values:
            app.shared_slider_values[sync_key] = slider.value

        def on_slider_change(instance, value):
            if app.shared_slider_values.get(sync_key) != value:
                app.shared_slider_values[sync_key] = value

        def on_shared_change(instance, shared_values):
            new_value = shared_values.get(sync_key)
            if new_value is not None and slider.value != new_value:
                slider.value = new_value

        slider.bind(value=on_slider_change)
        app.bind(shared_slider_values=on_shared_change)

    container.slider = slider
    container.value_label = value_label
    container.ok_button = ok_button

    return container

def show_info_popup(title="Information", message="Ceci est un message.", size_hint=(0.6, 0.4)):
    layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

    label = Label(text=message, halign='center', valign='middle')
    label.bind(size=label.setter('text_size'))  # pour centrer verticalement

    ok_button = Button(text="OK", size_hint=(1, 0.3))

    popup = Popup(title=title,
                  content=layout,
                  size_hint=size_hint,
                  auto_dismiss=False)

    ok_button.bind(on_release=popup.dismiss)

    layout.add_widget(label)
    layout.add_widget(ok_button)

    popup.open()

#=======================================================================================================================
#                                                  ECRAN PRINCIPAL
#=======================================================================================================================
class HomeScreen(Screen):
    ''' ÉCRAN D’ACCUEIL '''
    def __init__(self, scan_screen, **kwargs):
        super().__init__(**kwargs)

        # Accès vers les autres écrans
        self.scan_screen = scan_screen

        # Initialisation des variables
        self.last_bpm = None
        self.websocket_server = None
        self.receiver_thread = None  # thread de réception UDP
        self.IP_Unity = None
        self.IP_Python = None
        self.last_ping_time = time.time()
        self.latest_img = None
        self.last_img_time = time.time()

        # Initialisation des flags
        self.arrow_added = False # pour le gif
        self.send_ip_running = True  # contrôler la boucle d'envoi de l'IP
        self.listen_UDP = True
        self.state_label = True

        # Conteneur principal
        main_layout = BoxLayout(
            orientation='vertical',
            spacing=dp(20),
            padding=dp(40)
        )

        # --- TOP: Logo et titre ---
        top_section = AnchorLayout(
            anchor_x='center',
            anchor_y='top',
            size_hint=(1, 0.2)
        )

        top_title = create_icon_label_row(
            resource_path("images/heart-rate-monitor.png"),
            "KCApp",
            font_size=40
        )

        top_section.add_widget(top_title)
        main_layout.add_widget(top_section)

        # --- MIDDLE : Data ---
        center_section = AnchorLayout(
            anchor_x='center',
            anchor_y='center',
            size_hint=(1, 0.4)
        )

        center_box = BoxLayout(
            orientation='vertical',
            spacing=dp(50),
            size_hint=(None, None)
        )

        # Crée la zone pour les data bpm
        self.bpm_box = BoxLayout(
            orientation='horizontal',
            spacing=dp(100),
            size_hint=(None, None),
            pos_hint={'center_x': 0.5}  # CENTRAGE horizontal
        )

        # Crée les paires icône + label
        heart_row = create_icon_label_row(
            resource_path("images/heart.png"),
            "-- bpm",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="heart_rate_label"
        )

        statut_row = create_gif_label_row(
            resource_path("gifs/loading"),
            "En attente de connexion du jeu...",
            interval=0.1,
            gif_size=(60,60),
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref_label="statut_label",
            ref_gif ="statut_gif"
        )

        # Création des gifs
        self.arrow = FolderAnimation(
            image_folder=resource_path('gifs/arrow'),
            interval=0.5,
            size_hint=(None, None),
            allow_stretch=True,
            keep_ratio=True,
            pos_hint={'center_y': 0.3}
        )

        # Ajoute à bpm_box
        self.bpm_box.add_widget(heart_row)

        # Ajoute à data_box
        center_box.add_widget(self.bpm_box)
        center_box.add_widget(statut_row)

        # Ajoute à data section puis au main layout
        center_section.add_widget(center_box)
        main_layout.add_widget(center_section)

        # --- BOTTOM: Boutons ---
        bottom_section = AnchorLayout(
            anchor_x='center',
            anchor_y='bottom',
            size_hint=(1, 0.4)
        )
        btn_box = BoxLayout(
            orientation='vertical',
            spacing=dp(5),
            size_hint=(0.8, None)
        )

        # Bouton ON/OFF pour envoyer les data dans le jeu
        self.start_ws_button = RoundedToggleButton(
            text_start="Mode adaptatif désactivé",
            text_stop="Mode adaptatif activé",
            size_hint=(1, None),
            height=dp(55),
            font_size=25,
            sync_key= "mode adaptatif"
        )
        self.start_ws_button.bind(on_press=self.on_toggle, # bouton ON
                                  on_release=self.on_toggle # bouton OFF (important pour synchronisation)
                                  )

        btn_box.add_widget(self.start_ws_button)

        # Autres boutons
        btn_box.add_widget(create_rounded_button("Connexion du capteur", self.go_to_scan))
        btn_box.add_widget(create_rounded_button("Suivi de la FC", self.go_to_progress_FC))
        btn_box.add_widget(create_rounded_button("Pilotage", self.go_to_pilotage))
        btn_box.add_widget(create_rounded_button("Ecran du jeu", self.go_to_game))
        btn_box.add_widget(create_rounded_button("Profil", self.go_to_profil))

        bottom_section.add_widget(btn_box)

        main_layout.add_widget(bottom_section)

        # Ajouter tous les widgets au conteneur principal
        self.add_widget(main_layout)

    def on_enter(self):
        # Lancer la fonction send_ip en arrière-plan dès l'ouverture de l'écran
        threading.Thread(target=self.send_ip, daemon=True).start()

        # Lancement du thread UDP receiver si ce n’est pas déjà fait
        if not hasattr(self,
                       "receiver_thread") or self.receiver_thread is None or not self.receiver_thread.is_alive():
            self.receiver_thread = threading.Thread(target=self.udp_receiver, daemon=True)
            self.receiver_thread.start()

    def on_toggle(self, instance):
        if instance.state == 'down':

            # Si heart_rate_data n'est pas "int"
            if not isinstance(self.scan_screen.heart_rate_data, int):
                show_info_popup(
                    title="Information",
                    message="Connectez le capteur pour utiliser cette fonctionnalité"
                )
                instance.state = 'normal'  # Réinitialise le bouton en START (non enfoncé)
                return

            print("🟢 Serveur activé")
            self.start_server_asyn()

        else:
            print("🔴 Serveur désactivé")
            self.stop_server()

            # Supprime le gif
            self.arrow_added = False
            self.bpm_box.remove_widget(self.arrow)

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

    async def websocket_handler(self, websocket, path): # appelé quand un cient WS se connecte
        clients.add(websocket)
        try:
            async for message in websocket: # ecoute les messages entrant de Unity
                print(f"📩 Message reçu depuis Unity : {message}")
        except websockets.ConnectionClosed as e:
            print(f"⚠️ Unity s'est déconnecté : {e}")
        finally:
            clients.remove(websocket) # retire le client une fois déconnecté

    def send_ip(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.IP_Python = self.get_ip()

            # Liste des IP possibles
            list_ip = self.get_possible_ips(self.IP_Python)

            print(f"📡 Recherche de l'IP Unity en cours...")

            while self.send_ip_running :
                for ip_possible in list_ip :

                    # Envoie de l'IP Unity fonctionnel et de l'IP local
                    message = f"IP_Unity:{ip_possible}/IP_Python:{self.IP_Python}"
                    message = message.encode()
                    sock.sendto(message, (ip_possible, UDP_PORT_SEND))
                    # print(f"📡 Message envoyé de {self.IP_Python}: {message.decode()} vers {ip_possible}:{UDP_PORT_SEND}")

        except Exception as e:
            print(f"⚠️ Erreur lors de l'envoi UDP : {e}")

    def get_ip(self): # récupère l'IP locale en se connectant fictivement à un serveur externe
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip

    def get_possible_ips(self, local_ip) :
        """
        Retourne toutes les adresses IP possibles sur le même sous-réseau que l'IP locale.

        Args:
            local_ip (str): L'adresse IP locale de l'appareil maître (ex: "192.168.1.12").

        Returns:
            list[str]: Liste d'adresses IP possibles sur le même réseau.
        """
        # On suppose un masque standard /24, soit 255.255.255.0
        network = ipaddress.IPv4Network(local_ip + "/24", strict=False) # ressort 255 possibilités

        # Liste toutes les adresses utilisables (exclut le network et broadcast address)
        possible_ips = [str(ip) for ip in network.hosts()]

        return possible_ips

    def udp_receiver(self):
        sock_receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_receiver.bind(("0.0.0.0", UDP_PORT_RECEIVE))  # même port que Unity
        sock_receiver.settimeout(1.0) # permet de ne pas bloquer indéfiniment
        while self.listen_UDP:
            try:
                print("Ecoute UDP en cours...")

                # Identifier la déconnection de Unity si pas de ping reçu pendant + de 3 sec
                elapsed = time.time() - self.last_ping_time

                if self.IP_Unity and elapsed > 3:
                    if self.state_label:
                        self.statut_label.text = 'En attente de connexion du jeu...'
                        self.statut_gif.set_gif(resource_path('gifs/loading'),
                                                interval=0.1,
                                                loop=True)
                        self.state_label = False

                    # Renvoyer l'IP
                    self.send_UDP(f"IP_Unity", f"{self.IP_Unity}/IP_Python:{self.IP_Python}")

                # Reception du message
                data, _ = sock_receiver.recvfrom(65535)  # 65535 = 65 Ko (limite max du paquet UDP)
                print(f"[UDP] Message reçu de Unity : {data}")

                # Stocker le dernier message reçu
                if data.startswith(b'IMG:'):
                    img_bytes = data[4:]
                    self.latest_img = img_bytes
                    self.last_img_time = time.time()  # ✅ Heure de reception du dernier message

                # mettre fin ici dès que IP_Unity est reçu
                if data.startswith(b'IP_Unity:'):
                    message = data.decode()
                    self.IP_Unity = message.split("IP_Unity:")[1].strip()
                    print(f"✅ IP de Unity reçue : {self.IP_Unity}")
                    self.send_ip_running = False  # 🔴 Met fin à la boucle

                    # Mise à jour sur l'écran d'accueil
                    self.statut_label.text = f'Jeu connecté ({self.IP_Unity})'
                    self.statut_gif.set_gif(resource_path('gifs/check'),
                                            interval = 0.1,
                                            loop=False)

                if data == b'ping_Unity':
                    # Dernier ping reçu
                    self.last_ping_time = time.time()
                    self.state_label = True

            except socket.timeout: # gestion des exceptions pour éviter crash
                continue
            except Exception as e:
                print(f"Erreur socket : {e}")
                break

        sock_receiver.close() # ferme le socket
        print("🛑 Réception UDP arrêtée")

    def send_UDP(self, id, value):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            message = f"{id}:{value}"
            message = message.encode()

            # Envoie des messages à Unity
            sock.sendto(message, (self.IP_Unity, UDP_PORT_SEND))
            print(f"📡 Message envoyé en broadcast : {message.decode()} vers {self.IP_Unity}:{UDP_PORT_SEND}")

        except Exception as e:
            print(f"⚠️ Erreur lors de l'envoi UDP : {e}")

    async def send_data_to_clients(self, heart_rate):
        if not clients:
            print("❌ Aucun client WebSocket connecté !")

            # Actualise l'ajout du gif
            self.bpm_box.remove_widget(self.arrow)
            self.arrow_added = False

            # Envoie de l'adresse IP de l'appareil maître à Unity via UDP pour connection websocket
            self.send_UDP("command_ws", "START")
            return

        if clients:
            message = str(heart_rate)
            print(f"{message} bpm")

            # Si gif pas encore ajouté
            if not self.arrow_added :
                self.bpm_box.add_widget(self.arrow)
                self.arrow_added = True

            await asyncio.gather(*[client.send(message) for client in clients])

    def go_to_scan(self, instance):
        ''' Change l'écran affiché par le ScreenManger'''
        self.manager.current = 'scan'

    def go_to_progress_FC(self, instance):
        ''' Change l'écran affiché par le ScreenManger'''
        self.manager.current = 'progress_FC'

    def go_to_pilotage(self, instance):
        ''' Change l'écran affiché par le ScreenManger'''
        self.manager.current = 'pilotage'

    def go_to_game(self, instance):
        ''' Change l'écran affiché par le ScreenManger'''
        self.manager.current = 'game'

    def go_to_profil(self, instance):
        ''' Change l'écran affiché par le ScreenManger'''
        self.manager.current = 'profil'

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

#=======================================================================================================================
#                                                  SOUS ECRAN "CONNEXION DU CAPTEUR"
#=======================================================================================================================
class ScanScreen(Screen):
    ''' ECRAN DU SCAN BLUETOOTH '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initialisation des variables
        self.device_spinner = None  # menu déroulant pour afficher les appareils détectés
        self.last_bpm = None
        self.devices = None
        self.client = None
        self.heart_rate_data = None # valeur par defaut

        # Conteneur principal
        main_layout = BoxLayout(
            orientation='vertical',
            padding=dp(40),
            spacing=dp(20)
        )

        # --- TOP: Logo et titre ---
        top_section = AnchorLayout (
            anchor_x='center',
            anchor_y='top',
            size_hint=(1, 0.2)
        )

        top_tittle = create_icon_label_row(
            resource_path("images/bluetooth.png"),
            "Connexion du capteur",
            font_size=30
        )
        top_section.add_widget(top_tittle)
        main_layout.add_widget(top_section)

        # --- MIDDLE : Data FC + Battery + SCAN ---
        center_section = AnchorLayout(
            anchor_x='center',
            anchor_y='center',
            size_hint=(1, 0.7)
        )
        center_box = BoxLayout(
            orientation='vertical',
            spacing=dp(200),
            size_hint=(0.8, None),
        )

        data_box = BoxLayout(
            orientation='horizontal',
            spacing=dp(20),
            size_hint=(1, None),
        )

        # Crée les paires icône + label
        heart_row = create_icon_label_row(
            resource_path("images/heart.png"),
            "-- bpm",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="heart_rate_label"
        )

        battery_row = create_icon_label_row(
            resource_path("images/battery.png"),
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

        # zone de scan
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
        )
        self.device_spinner.bind(text=self.on_device_selected)

        # Ajoute au btn_box
        btn_scan_box.add_widget(scan_button)
        btn_scan_box.add_widget(self.device_spinner)

        # ajout à center_box
        center_box.add_widget(data_box)
        center_box.add_widget(btn_scan_box)

        # Ajoute à center_section
        center_section.add_widget(center_box)

        main_layout.add_widget(center_section)

        # --- BOTTOM: Boutons ---
        bottom_section = AnchorLayout(
            anchor_x='center',
            anchor_y='bottom',
            size_hint=(1, 0.01)
        )
        bottom_box = BoxLayout(
            orientation='vertical',
            spacing=dp(20),
            size_hint=(0.8, None)
        )

        back_button = create_rounded_button("Retour", self.go_back)

        # Ajout au bottom_box
        bottom_box.add_widget(back_button)

        # Ajout au bottom_section
        bottom_section.add_widget(bottom_box)

        main_layout.add_widget(bottom_section)

        self.add_widget(main_layout)

    def on_enter(self): # s'active dès l'ouverture de l'écran
        # 🔗 Lien vers l'écran principal
        self.home_screen = self.manager.get_screen('home')

    def go_back(self, instance):
        self.manager.current = 'home'

    def start_ble_scan(self, instance):
        self.device_spinner.text = "Scan en cours..."
        asyncio.ensure_future(self.scan_ble())

    def update_ui_after_scan(self):
        if not self.devices:
            self.device_spinner.text = "Aucun appareil trouvé. Réessayez"
            self.device_spinner.values = []
        else:
            if len(self.devices) == 1 :
                self.device_spinner.text = f"{len(self.devices)} appareil trouvé"

            if len(self.devices) > 1:
                self.device_spinner.text = f"{len(self.devices)} appareils trouvés"

            self.device_spinner.values = [f"{d.name} ({d.address})" for d in self.devices]

    async def scan_ble(self):
        if self.client :
            self.device_spinner.text = "Déconnexion en cours..."
            await self.client.disconnect()

            self.update_heart_rate("--")
            self.update_battery("--")

            # Mise à jour sur l'écran d'accueil
            self.home_screen.update_heart_rate("--")

        try :
            self.device_spinner.text = "Scan en cours..."
            scanned_devices = await bleak.BleakScanner.discover(3)
            self.devices = [d for d in scanned_devices if any(brand in (d.name or "") for brand in TARGET_DEVICES)]
            self.update_ui_after_scan()

        except OSError as e:
            print(f"⚠️ Erreur Bluetooth : {e}")
            show_info_popup(
                title="Bluetooth inactif",
                message="Activez le Bluetooth pour utiliser cette fonctionnalité"
            )

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
                        self.home_screen.update_heart_rate(heart_rate)

                        # Mise à jour sur l'écran actuel et sur le graphique
                        self.update_heart_rate(heart_rate)

                        if self.home_screen.start_ws_button.state == 'down':
                            print("✅ Websocket activé.")
                            await self.home_screen.send_data_to_clients(heart_rate)
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

#=======================================================================================================================
#                                                 SOUS ECRAN "SUIVI DE LA FC"
#=======================================================================================================================
class ProgressScreen(Screen):
    def __init__(self, scan_screen, pilotage_screen, profil_screen, **kwargs):
        super().__init__(**kwargs)

        # 🔗 Liens vers les autres écrans
        self.scan_screen = scan_screen
        self.pilotage_screen = pilotage_screen
        self.profil_screen = profil_screen

        # Initialisation des variables
        self.data_hr = []  # liste des données FC en temps reel
        self.data_target_hr = []
        self.time = 0
        self.last_bpm = None

        # Conteneur principal
        main_layout = BoxLayout(
            orientation='vertical',
            padding=dp(40),
            spacing=dp(20)
        )

        # --- TOP: Logo et titre ---
        top_section = AnchorLayout(
            anchor_x='center',
            anchor_y='top',
            size_hint=(1, 0.1)
        )

        top_tittle = create_icon_label_row(
            resource_path("images/discount.png"),
            "Suivi de la FC",
            font_size=30
        )
        top_section.add_widget(top_tittle)
        main_layout.add_widget(top_section)

        # --- MIDDLE : Data + Graphique + Slider ---
        center_section = AnchorLayout(
            anchor_x='center',
            anchor_y='center',
            size_hint=(1, 0.8)
        )

        self.center_box = BoxLayout(
            orientation='vertical',
            spacing=dp(30),
            size_hint=(1, 1)
        )

        # Crée la zone pour les data bpm
        self.bpm_box = BoxLayout(
            orientation='horizontal',
            spacing=dp(200),
            size_hint=(None, None),
            pos_hint={'center_x': 0.5}  # CENTRAGE horizontal
        )

        # Bouton ON/OFF pour envoyer les data dans le jeu
        self.start_ws_button = RoundedToggleButton(
            text_start="Mode adaptatif désactivé",
            text_stop="Mode adaptatif activé",
            size_hint=(0.4, None),
            height=dp(55),
            font_size=25,
            sync_key="mode adaptatif",
            pos_hint={'center_x': 0.5}
        )
        self.start_ws_button.bind(on_press=self.on_toggle, on_release=self.on_toggle)

        # Crée les paires icône + label
        self.heart_row = create_icon_label_row(
            resource_path("images/heart.png"),
            "-- bpm",
            screen_instance=self,
            font_size=40,
            is_dynamic=True,
            ref="heart_rate_label"
        )

        self.target_row = create_icon_label_row(
            resource_path("images/target3.png"),
            f"{self.pilotage_screen.target_hr} %",
            screen_instance=self,
            font_size=40,
            icon_size=(45, 45),
            is_dynamic=True,
            ref="target_label"
        )

        # Ajoute les deux data bpm à bpm_box
        self.bpm_box.add_widget(self.heart_row)

        ## --- Graphique ---
        self.graph = Graph(xlabel='Time (s)', ylabel='FCmax (%)',
                           size_hint=(1, 1), opacity=1,
                           x_ticks_minor=1, x_ticks_major=60,  # intervalles de graduation
                           y_ticks_minor=1, y_ticks_major=10,  # intervalles de graduation
                           y_grid_label=True, x_grid_label=True,  # labels des axes
                           padding=5,  # espacement entre axe et label
                           x_grid=False, y_grid=True,  # affiche les grilles
                           xmin=0, xmax=600, ymin=0, ymax=100)  # plages des axes

        # Crée la courbe %FCmax cible
        self.target_line = LinePlot(color=get_color_from_hex("#42A5F5"), line_width=3)

        # Créé la courbe FC
        self.plot = LinePlot(color=[1, 0, 0, 1], line_width=3)
        self.graph.add_plot(self.plot)

        # --- Slider de %FCmax cible ---
        self.hr_target_slider = create_icon_slider(
            icon_left_path=resource_path("images/snowflake.png"),
            icon_right_path=resource_path("images/hot-deal.png"),
            min_val=0,
            max_val=100,
            step=1,
            initial=50,
            unit=" %",
            sync_key="hr_target",
            on_validate=self.pilotage_screen.on_slider_target_hr
        )

        # ajout au graph_box
        self.center_box.add_widget(self.bpm_box)
        self.center_box.add_widget(self.graph)
        self.center_box.add_widget(self.start_ws_button)

        center_section.add_widget(self.center_box)

        main_layout.add_widget(center_section)

        # Appel toutes les secondes
        Clock.schedule_interval(self.update_graph, 1)

        # --- BOTTOM : Button ---
        bottom_section = AnchorLayout(
            anchor_x='center',
            anchor_y='bottom',
            size_hint=(1, 0.1)
        )
        bottom_box = BoxLayout(
            orientation='vertical',
            spacing=dp(20),
            size_hint=(0.8, None)
        )

        back_button = create_rounded_button("Retour", self.go_back,
                                            size_hint=(1, None)
                                            )

        bottom_box.add_widget(back_button)
        bottom_section.add_widget(bottom_box)
        main_layout.add_widget(bottom_section)

        # Ajout du main_layout à l'écran
        self.add_widget(main_layout)

    def on_enter(self, *args):
        self.home_screen = self.manager.get_screen('home')

    def on_toggle(self, instance):
        if instance.state == 'down':

            # Si heart_rate_data n'est pas "int"
            if not isinstance(self.scan_screen.heart_rate_data, int):
                show_info_popup(
                    title="Information",
                    message="Connectez le capteur pour utiliser cette fonctionnalité"
                )
                instance.state = 'normal'  # Réinitialise le bouton en START (non enfoncé)
                return

            self.center_box.add_widget(self.hr_target_slider)
            self.bpm_box.add_widget(self.target_row)

            # Crée la courbe %FCmax cible
            self.graph.add_plot(self.target_line)

            # On calcule dynamiquement la taille de bpm_box en fonction du contenu
            self.bpm_box.width = self.heart_row.width + self.target_row.width  # + self.bpm_box.spacing
            self.bpm_box.height = max(self.heart_row.height, self.target_row.height)

        else:
            # Supprime les widgets
            self.bpm_box.remove_widget(self.target_row)
            self.center_box.remove_widget(self.hr_target_slider)
            self.graph.remove_plot(self.target_line)

    def update_graph(self, dt): # dt = délai depuis le dernier appel
        '''Fonction appelée pour mettre à jour le graphique'''

        # Vérifier qu'un appareil est connecté
        if isinstance(self.scan_screen.heart_rate_data, int): # retourne True si l'objet est "int"
            HR = self.scan_screen.heart_rate_data  # 🔄 récupère la FC en temps réel

            # Calcul de la FCmax en fonction de l'âge
            self.maxHR = 211 - (self.profil_screen.age * 0.64)

            # Convertir en % de FCmax
            hr = (HR/self.maxHR)*100

            # Mise à jour du label
            self.update_heart_rate(HR)

            # Ajout du temps et de la FC dans la liste
            self.data_hr.append((self.time, hr))

            # Incrémentation de 1 du temps
            self.time += 1

            # Garde seulement les 600 dernières secondes
            if len(self.data_hr) > 600:
                self.data_hr = self.data_hr[-600:]
                self.graph.xmin = self.data_hr[0][0]
                self.graph.xmax = self.data_hr[-1][0]

            # mise à jour des points affichés dans le graphique
            self.plot.points = self.data_hr

            if self.start_ws_button.state == 'down':
                # Mise à jour du label
                self.target_label.text = f"{self.pilotage_screen.target_hr:.0f} %"

                # Mise à jour de la courbe %FCMax cible
                self.data_target_hr.append((self.time,self.pilotage_screen.target_hr))
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

    def go_back(self, instance):
        self.manager.current = 'home'

#=======================================================================================================================
#                                                 SOUS ECRAN "PILOTAGE"
#=======================================================================================================================
class PilotageScreen(Screen):
    ''' ECRAN PILOTAGE'''
    def __init__(self, scan_screen, **kwargs):
        super().__init__(**kwargs)

        # 🔗 Liens vers les autres écrans
        self.scan_screen = scan_screen
        self.home_screen = None

        # Initialisation des variables
        self.target_hr = 50  # 🎯 %FCMax cible (par defaut)
        self.cube_rate_perc = None
        self.cube_rate = float()

        # Conteneur principal
        main_layout = BoxLayout(
            orientation='vertical',
            spacing=dp(20),  # utilité ?
            padding=dp(40)
        )

        # --- TOP: Logo et titre ---
        top_section = AnchorLayout(
            anchor_x='center',
            anchor_y='top',
            size_hint=(1, 0.1)
        )

        top_title = create_icon_label_row(
            resource_path("images/pilotage.png"),
            "Pilotage du jeu",
            font_size=30
        )

        top_section.add_widget(top_title)
        main_layout.add_widget(top_section)

        # --- MIDDLE : Data Input ---
        center_section = AnchorLayout(
            anchor_y='center', # centrer dans l'écran
            anchor_x='center',
            size_hint=(1, 0.8)
            )

        self.center_box = BoxLayout(
            orientation='vertical',
            spacing=dp(100),
            size_hint=(1, None)
        )

        self.manuel_box = BoxLayout(
            orientation='vertical',
            spacing=dp(30),
            size_hint=(1, None)
        )

        self.auto_box = BoxLayout(
            orientation='vertical',
            spacing=dp(30),
            size_hint=(1, None)
        )

        # Sous-titres
        manuel_label = Label(
            text='PILOTAGE MANUEL',
            bold=True,  # gras
            font_size=30,
            color=(1, 1, 1, 1),
            size_hint_x= 0.3
        )

        auto_label = Label(
            text="PILOTAGE AUTOMATIQUE",
            bold=True,  # gras
            font_size=30,
            color=(1, 1, 1, 1),
            size_hint_x=0.4
        )

        # Sliders
        self.cube_rate_slider = create_icon_slider(
            icon_left_path=resource_path("images/cube.png"),
            icon_right_path=resource_path("images/cubes.png"),
            min_val=0, # freq rate = 2 (rareté ++ des cubes)
            max_val=100, # freq rate = 0 (+ de cubes)
            step=1,
            initial=50,
            unit=" %",
            on_validate=self.on_slider_cube_rate  # associer à la fonction lorsque OK est appuyé
        )

        self.hr_target_slider = create_icon_slider(
            icon_left_path=resource_path("images/snowflake.png"),
            icon_right_path=resource_path("images/hot-deal.png"),
            min_val=0,
            max_val=100,
            step=1,
            initial=50,
            unit=" %",
            sync_key="hr_target",
            on_validate=self.on_slider_target_hr  # associer à la fonction lorsque OK est appuyé
        )

        # Boutons ON/OFF
        self.obs_button = RoundedToggleButton(
            text_start="Obstacle désactivé",
            text_stop="Obstacle activé",
            size_hint=(0.3, None),
            height=70,
            font_size=25,
            pos_hint={'center_x': 0.5}  # CENTRAGE horizontal
        )

        self.obs_button.bind(on_press=self.on_toggle_obs)

        self.start_ws_button = RoundedToggleButton(
            text_start="Mode adaptatif désactivé",
            text_stop="Mode adaptatif activé",
            size_hint=(0.4, None),
            height=70,
            font_size=25,
            pos_hint={'center_x': 0.5},  # CENTRAGE horizontal
            sync_key="mode adaptatif"
        )

        self.start_ws_button.bind(on_press=self.on_toggle,
                                  on_release = self.on_toggle)

        # Ajout dans manuel_box
        self.manuel_box.add_widget(manuel_label)  # sous-titre
        self.manuel_box.add_widget(self.obs_button) # Bouton ON/OFF obstacle
        self.manuel_box.add_widget(self.cube_rate_slider)  # slider cubes

        # Ajout dans automatique_box
        self.auto_box.add_widget(auto_label)
        self.auto_box.add_widget(self.start_ws_button) # bouton ON/OFF mode adaptatif

        # Ajout à center_box
        self.center_box.add_widget(self.manuel_box)
        self.center_box.add_widget(self.auto_box)

        # ajuste automatiquement la taille du center_box
        self.center_box.bind(minimum_height=self.center_box.setter('height'))

        # Ajout à data_section
        center_section.add_widget(self.center_box)
        main_layout.add_widget(center_section)

        # --- BOTTOM : Button ---
        bottom_section = AnchorLayout(
            anchor_x='center',
            anchor_y='bottom',
            size_hint=(1, 0.1)
        )
        bottom_box = BoxLayout(
            orientation='vertical',
            spacing=dp(20),
            size_hint=(0.8, None)
        )

        back_button = create_rounded_button("Retour", self.go_back,
                                            size_hint=(1, None))
        bottom_box.add_widget(back_button)
        bottom_section.add_widget(bottom_box)
        main_layout.add_widget(bottom_section)

        # Ajout du main_layout à l'écran
        self.add_widget(main_layout)

    def on_enter(self, *args):
        # Lien vers l'écran principal
        self.home_screen = self.manager.get_screen('home')

    def on_toggle(self, instance):
        if instance.state == 'down':

            # Si heart_rate_data n'est pas "int"
            if not isinstance(self.scan_screen.heart_rate_data, int):
                show_info_popup(
                    title="Information",
                    message="Connectez le capteur pour utiliser cette fonctionnalité"
                )
                instance.state = 'normal'  # Réinitialise le bouton en START (non enfoncé)
                return

            # Supprime le widget du parent s'il est déjà attaché
            if self.hr_target_slider.parent:
                self.hr_target_slider.parent.remove_widget(self.hr_target_slider)

            self.auto_box.add_widget(self.hr_target_slider)  # slider target FC

            # Supprime le slider manuel si présent
            if self.cube_rate_slider.parent:
                self.cube_rate_slider.parent.remove_widget(self.cube_rate_slider)

            # ajuste l'espacement du center_box
            self.center_box.spacing = dp(350)

        else:
            # Supprime le slider automatique si présent
            if self.hr_target_slider.parent:
                self.hr_target_slider.parent.remove_widget(self.hr_target_slider)

            # Réintègre le slider manuel
            if self.cube_rate_slider.parent is None:
                self.manuel_box.add_widget(self.cube_rate_slider)

            # ajuste l'espacement du center_box
            self.center_box.spacing = dp(100)

    def on_toggle_obs(self, instance):
        if instance.state == 'down':
            print("🟢 Obstacle activé")
            # ajouter ici l'envoie UDP de la commande pour désactiver les obstacles
            self.home_screen.send_UDP('obs', "START")
        else:
            print("🔴 Obstacle désactivé")
            # ajouter ici l'envoie UDP de la commande pour activer les obstacles
            self.home_screen.send_UDP('obs', "STOP")

    def on_slider_target_hr(self, value):
        self.target_hr = value
        self.target_hr = int(self.target_hr)
        # Envoie dans Unity via UDP
        self.home_screen = self.manager.get_screen('home') # obligé car slider p-e activé depuis autre écran
        self.home_screen.send_UDP('target_hr', self.target_hr)

    def on_slider_cube_rate(self, value):
        self.cube_rate_perc = value

        # convertion pour retrouver la frequence de cube
        self.cube_rate = round(2 - (self.cube_rate_perc * 2) / 100, 2) # 2 = valeur à 0% d'intensité sur le slider
        print(self.cube_rate)

        # Envoie dans Unity via UDP
        self.home_screen.send_UDP('cube_rate', self.cube_rate)

    def go_back(self, instance):
        self.manager.current = 'home'

# =======================================================================================================================
#                                                 SOUS ECRAN "GAME"
# =======================================================================================================================
class GameScreen(Screen):
    ''' ECRAN DU JEU'''

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Conteneur principal
        main_layout = BoxLayout(orientation='vertical',
                                padding=dp(40),
                                spacing=dp(20)
                                )

        # --- TOP: Titre ---
        top_section = AnchorLayout(anchor_x='center', anchor_y='top', size_hint=(1, 0.1))
        top_title = create_icon_label_row(resource_path("images/video-games.png"), "Ecran du jeu", font_size=30)
        top_section.add_widget(top_title)
        main_layout.add_widget(top_section)

        # --- MIDDLE : Image ---
        center_section = AnchorLayout(anchor_x='center',
                                      anchor_y='center',
                                      size_hint=(1, 0.7)
                                      )
        # widget Image
        self.image_widget = Image(size_hint=(1, 1))

        # Image "NO SIGNAL"
        self.no_signal_texture = Image(source="images/no_signal.jpg").texture

        # Afficher l'image "NO SIGNAL"
        self.image_widget.texture = self.no_signal_texture

        center_section.add_widget(self.image_widget)
        main_layout.add_widget(center_section)

        # --- BOTTOM : boutons ---
        bottom_section = AnchorLayout(anchor_x='center',
                                      anchor_y='bottom',
                                      size_hint=(1, 0.2)
                                      )
        bottom_box = BoxLayout(orientation='vertical',
                               spacing=dp(20),
                               size_hint=(0.8, None)
                               )

        back_button = create_rounded_button("Retour", self.go_back, size_hint=(0.8, None))

        # bottom_box.add_widget(self.toggle_button)
        bottom_box.add_widget(back_button)
        bottom_section.add_widget(bottom_box)
        main_layout.add_widget(bottom_section)

        self.add_widget(main_layout)

    def on_enter(self): # appeler automatiquement quand on entre dans l'écran
        # Lien vers l'écran principal
        self.home_screen = self.manager.get_screen('home')

        # Demande d'envoi des images à Unity
        self.home_screen.send_UDP('stream_game', "START")

        # Lancer la fonction de mise à jour des images
        Clock.schedule_interval(self.update_image, 1 / 30.)  # afficher les images (30 FPS)

    def on_leave(self): # appelé automatiquement lorsque l'écran est quitté
        # Demande d'arrêt d'envoi des images à Unity
        self.home_screen.send_UDP('stream_game', 'STOP')
        # Stopper la fonction
        Clock.unschedule(self.update_image)

    def update_image(self, dt):
        now = time.time()

        if self.home_screen.latest_img:
            try:
                # convertir l'image binaire en image PIL
                pil_image = PILImage.open(io.BytesIO(self.home_screen.latest_img)).convert('RGB')

                # Creer une texture à partir de l'image
                tex = Texture.create(size=pil_image.size, colorfmt='rgb')
                tex.blit_buffer(pil_image.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
                tex.flip_vertical()

                # Affiche cette texture
                self.image_widget.texture = tex

            except Exception as e:
                print(f"Erreur affichage image : {e}")

        # Si plus de 2 secondes sans nouvelle image
        if now - self.home_screen.last_img_time > 2:
            self.image_widget.texture = self.no_signal_texture

    def go_back(self, instance):
        self.manager.current = 'home'

#=======================================================================================================================
#                                                 SOUS ECRAN "PROFIL"
#=======================================================================================================================
class ProfilScreen(Screen):
    ''' ECRAN PROFIL'''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initialisation des variables
        self.age = 10 # par defaut

        # Conteneur principal
        main_layout = BoxLayout(
            orientation='vertical',
            padding=40,
            spacing=20
        )

        # --- TOP: Logo et titre ---
        top_section = AnchorLayout(
            anchor_x='center',
            anchor_y='top',
            size_hint=(1, 0.2)
        )

        top_tittle = create_icon_label_row(
            resource_path("images/user.png"),
            "Profil",
            font_size=30
        )
        top_section.add_widget(top_tittle)
        main_layout.add_widget(top_section)

        # --- MIDDLE : Data Input ---
        center_section = AnchorLayout(
            anchor_x='center',
            anchor_y='center',
            size_hint=(1, 0.6)
        )

        center_box = BoxLayout(
            orientation='vertical',
            spacing=dp(100),
            size_hint=(1, None)
        )

        # Crée les Sliders
        age_slider = create_icon_slider(
            icon_left_path=resource_path("images/baby.png"),
            icon_right_path=resource_path("images/old-man.png"),
            min_val=0,
            max_val=100,
            step=1,
            initial=10,
            unit=" ans",
            on_validate=self.on_slider_age
        )

        poids_slider = create_icon_slider(
            icon_left_path=resource_path("images/butterfly.png"),
            icon_right_path=resource_path("images/elephant.png"),
            min_val=20,
            max_val=100,
            step=1,
            initial=40,
            unit=" kg",
            on_validate=None  # associer à x fonction lorsque OK est appuyé
        )

        # Ajout dans data_box
        center_box.add_widget(age_slider) # slider âge
        center_box.add_widget(poids_slider) # slider poids

        # ajuste automatiquement la taille du center_box
        center_box.bind(minimum_height=center_box.setter('height'))

        # Ajout à center_section
        center_section.add_widget(center_box)
        main_layout.add_widget(center_section)

        # --- BOTTOM : Button ---
        bottom_section = AnchorLayout(
            anchor_x='center',
            anchor_y='bottom',
            size_hint=(1, 0.2)
        )
        bottom_box = BoxLayout(
            orientation='vertical',
            spacing=dp(20),
            size_hint=(0.8, None)
        )

        back_button = create_rounded_button("Retour", self.go_back,
                                            size_hint=(0.8, None))

        # Ajoute au bottom_section
        bottom_box.add_widget(back_button)
        bottom_section.add_widget(bottom_box)

        main_layout.add_widget(bottom_section)

        # Ajout du main_layout à l'écran
        self.add_widget(main_layout)

    def on_enter(self, *args):
        self.home_screen = self.manager.get_screen('home')

    def on_slider_age(self, value):
        self.age = value

        # Convertion en entier
        self.age = int(self.age)

        # Envoie à Unity via UDP
        self.home_screen.send_UDP('age', self.age)

    def go_back(self, instance):
        self.manager.current = 'home'

#=======================================================================================================================
#                                                 CONSTRUCTION DE L'APPLICATION
#=======================================================================================================================
class KCApp(App):
    ''' CONSTRUCTION DE L'APPLICATION '''

    shared_slider_values = DictProperty({})
    shared_toggle_states = DictProperty({})

    def build(self):
        # Gestion des écrans
        sm = ScreenManager()

        # Ecrans indépendant des autres
        scan_screen = ScanScreen(name='scan')
        profil_screen = ProfilScreen(name='profil')
        game_screen = GameScreen(name='game')

        # Ecrans dépendant des autres
        home_screen = HomeScreen(scan_screen=scan_screen, name='home')
        pilotage_screen = PilotageScreen(scan_screen=scan_screen, name='pilotage')
        progress_screen = ProgressScreen(scan_screen=scan_screen, pilotage_screen = pilotage_screen, profil_screen= profil_screen, name='progress_FC')

        # Ajout des écrans
        sm.add_widget(home_screen)
        sm.add_widget(scan_screen)
        sm.add_widget(progress_screen)
        sm.add_widget(profil_screen)
        sm.add_widget(pilotage_screen)
        sm.add_widget(game_screen)

        return sm

async def main(app):
    await app.async_run("asyncio")

if __name__ == '__main__':
    # Afficher les logs ayant un niveau supérieur ou égal à DEBUG
    Logger.setLevel(logging.DEBUG)

    # Lancement de l'app
    app = KCApp()
    asyncio.run(main(app))