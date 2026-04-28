from app.data.session_config import SessionConfig
from app.data.hr_session import HRSession
from app.data.user_profile import UserProfile

class GameSession:

    def __init__(self, user_profile=None):
        self.user_profile = UserProfile()
        self.config = SessionConfig()
        self.hr_session = HRSession()
