
import time

class GameMetrics:
    
    def __init__(self, session):
        self.session = session
        
        # historique CPM
        self.cpm_history = []
        self.cpm_time = []

    def add_cpm(self, value):
        t = time.time() - self.session.start_time
        
        self.cpm_history.append(value)
        self.cpm_time.append(t)
    
    def reset(self):
        self.cpm_history.clear()
        self.cpm_time.clear()