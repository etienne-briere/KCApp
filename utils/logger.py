import logging
from config import DEBUG_MODE

def setup_logger():
    """Configure le système de logging"""
    level = logging.DEBUG if DEBUG_MODE else logging.INFO
    
    # Configuration du logging Python standard
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('app.log'),
            logging.StreamHandler()
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Logger configuré - Niveau: {logging.getLevelName(level)}")

def get_logger(name):
    '''
    Retourne un logger pour un module donné
    
    :param name: Nom du module (utiliser __name__)
    '''
    """"""
    return logging.getLogger(name)