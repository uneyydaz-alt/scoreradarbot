import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, CHANNEL_USERNAME

# Donnees Braga vs Betis
# Row 246: Over 1.5 -> Win (2 buts total >= 2)
# Row 247: Over 2.5 -> Lose (2 buts total < 3)

msg1 = (
    "\U0001f3c1 FT | SC Braga 1-1 Real Betis\n"
    "\u2022 \u2705 Over 1.5 FT"
)

msg2 = (
    "\U0001f3c1 FT | SC Braga 1-1 Real Betis\n"
    "\u2022 \u274c Over 2.5 FT"
)

async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(chat_id=CHANNEL_USERNAME, text=msg1)
    print("Envoye:", msg1)
    await bot.send_message(chat_id=CHANNEL_USERNAME, text=msg2)
    print("Envoye:", msg2)

asyncio.run(main())
