from app.data.session_config import SessionConfig
from app.data.hr_session import HRSession

class GameSession:
    _instance = None  # ✅ attribut de classe

    def __init__(self, user_profile=None):
        self.user_profile = user_profile
        self.config = SessionConfig()
        self.hr_session = HRSession()
