#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import threading
from flask import Flask
from datetime import datetime
from typing import Dict, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, 
    MessageHandler, filters, CallbackQueryHandler
)

# --- SERVEUR WEB POUR RENDER ---
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Bot is running!", 200

def run_flask():
    # Écoute sur le port 10000 requis par Render
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# --- IMPORTS ET LOGGING ---
try:
    from strategies import StrategyManager
    from utils_new import get_latest_results, update_history
except ImportError as e:
    logging.error(f"Erreur d'importation : {e}. Vérifiez vos fichiers .py")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur config: {e}")
            return {}

    def get(self, section: str, key: str = None, default=None):
        if key is None: return self.config.get(section, default)
        return self.config.get(section, {}).get(key, default)

class BaccaraBot:
    def __init__(self, config_path: str = "config.json"):
        self.config = ConfigManager(config_path)
        self.token = self.config.get('telegram', 'bot_token')
        self.admin_id = self.config.get('telegram', 'admin_id')
        self.main_channel = self.config.get('telegram', 'main_channel')
        self.language = self.config.get('app', 'language', 'FR')
        self.check_interval = self.config.get('app', 'check_interval_seconds', 30)
        
        self.history = {}
        self.is_running = False
        self.last_check = None
        self.active_predictions = []
        self.daily_stats = {'total_predictions': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0}
        
        # CORRECTION SYNTAXE : Utilisation de doubles guillemets pour les apostrophes
        self.translations = {
            'FR': {
                'bot_started': '🤖 Bot démarré! Surveillance active.',
                'bot_stopped': '🛑 Bot arrêté.',
                'admin_only': "⚠️ Seul l'administrateur peut utiliser cette commande.",
                'status_running': "🟢 Bot en cours d'exécution",
                'status_stopped': '🔴 Bot arrêté',
                'games_history': "Jeux dans l'historique",
                'prediction_title': '🔮 PRÉDICTION BACCARA'
            }
        }

    def _t(self, key: str) -> str:
        return self.translations.get(self.language, self.translations['FR']).get(key, key)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [[InlineKeyboardButton("▶️ Démarrer", callback_data='start_bot'),
                     InlineKeyboardButton("⏹ Arrêter", callback_data='stop_bot')]]
        await update.message.reply_text("🎰 *Bot Baccara prêt*", 
                                       reply_markup=InlineKeyboardMarkup(keyboard), 
                                       parse_mode='Markdown')

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.data == 'start_bot':
            if str(query.from_user.id) == str(self.admin_id):
                self.is_running = True
                await query.edit_message_text(f"✅ {self._t('bot_started')}")
            else:
                await query.edit_message_text(self._t('admin_only'))
        elif query.data == 'stop_bot':
            self.is_running = False
            await query.edit_message_text(f"🛑 {self._t('bot_stopped')}")

    async def check_and_predict(self, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_running: return
        logger.info("Analyse en cours...")
        self.last_check = datetime.now()
        # Votre logique de prédiction ici...

    def run(self):
        if not self.token:
            logger.error("Token manquant dans config.json !")
            return

        # 1. Lancer Flask pour Render
        threading.Thread(target=run_flask, daemon=True).start()

        # 2. Lancer le Bot Telegram
        # Note: L'option [job-queue] doit être installée via pip
        application = Application.builder().token(self.token).build()
        
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Initialisation correcte de la boucle de surveillance
        if application.job_queue:
            application.job_queue.run_repeating(self.check_and_predict, 
                                              interval=self.check_interval, 
                                              first=10)
        
        logger.info("Bot en ligne et serveur Web sur port 10000")
        application.run_polling()

if __name__ == "__main__":
    bot = BaccaraBot()
    bot.run()
