import asyncio
from utils.event_bus import event_bus
from kivy.app import App
from time import time

class AdaptiveController:
    """ Ecouter les events (HR et Unity connection) et décider quoi faire"""

    def __init__(self):
        app = App.get_running_app()
        self.ws_server = app.ws_server
        self.udp_discovery = app.udp_discovery

        self.unity_connected = False
        self.last_hr = None
        self.adaptive_mode_enabled = True

        event_bus.subscribe("heart_rate_received", self.on_heart_rate)
        event_bus.subscribe("unity_connection_changed", self.on_unity_connection)

    def on_unity_connection(self, data):
        self.unity_connected = data["connected"]

        if not self.unity_connected and self.ws_server.is_running:
            asyncio.ensure_future(self.stop_ws())

    def on_heart_rate(self, bpm):
        self.last_hr = bpm

        if not self.adaptive_mode_enabled:
            return

        if self.unity_connected:
            if not self.ws_server.is_running:
                asyncio.ensure_future(self.start_ws())

            asyncio.ensure_future(self.ws_server.send_data_to_clients(bpm))

    async def start_ws(self):
        success = await self.ws_server.start()

        if success:
            self.udp_discovery.send_message("command_ws", "1")

    async def stop_ws(self):
        await self.ws_server.stop()