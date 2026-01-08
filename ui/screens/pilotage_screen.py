from kivy.uix.screenmanager import Screen

class PilotageScreen(Screen):
    #def on_enter(self):
        #self.ids.title_label.text = "Bienvenue !"

    def on_profile_press(self, *args):
        self.parent.current = "profile"

    def on_settings_press(self, *args):
        self.parent.current = "settings"