import asyncio
import logging

from kivy.logger import Logger
from app.app import KCApp
from utils.logger import setup_logger


async def main(app):
    """Point d'entrée asynchrone de l'application"""
    await app.async_run("asyncio")

if __name__ == '__main__':
    # Configuration du logging
    setup_logger()
    Logger.setLevel(logging.DEBUG)
    
    # Lancement de l'application
    app = KCApp()
    asyncio.run(main(app))
