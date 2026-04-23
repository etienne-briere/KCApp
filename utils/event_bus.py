from kivy.clock import Clock

class EventBus:
    def __init__(self):
        self.listeners = {}

    def subscribe(self, event_name, callback):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)
    
    def unsubscribe(self, event_name, callback):
        if event_name in self.listeners:
            if callback in self.listeners[event_name]:
                self.listeners[event_name].remove(callback)

            # optionnel : nettoyer si liste vide
            if not self.listeners[event_name]:
                del self.listeners[event_name]
    
    def emit(self, event_name, data=None):
        if event_name in self.listeners:
            for callback in list(self.listeners[event_name]):
                print(f"[EventBus] {event_name} → {callback.__name__}")
                Clock.schedule_once(lambda dt, cb=callback: cb(data))
    
event_bus = EventBus()