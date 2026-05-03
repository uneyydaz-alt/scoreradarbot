"""Point d'entrée du Value Radar Bot."""
import sys
import os

# Les imports dans value_bot/ sont relatifs au dossier value_bot
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "value_bot"))

from bot import main

if __name__ == "__main__":
    main()
