import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "VOTRE_TOKEN_ICI")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Paramètres du bot
DAILY_BONUS = 10       # ₽ par jour
REFERRAL_BONUS = 250   # ₽ par parrainage
MIN_WITHDRAW = 5000    # ₽ minimum de retrait
REFERRALS_REQUIRED = 20  # parrainages requis

# Canal de publication des retraits
CANAL_RETRAIT = "@zarabotok_official0"
