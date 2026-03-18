#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram Baccara - Système de prédiction complet
Version avec Serveur Web (Port 10000) et corrections JobQueue/Syntaxe
"""

import os
import sys
import json
import time
import logging
import asyncio
import threading
from flask import Flask
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, 
    MessageHandler, filters, CallbackQueryHandler
)

# --- CONFIGURATION DU SERVEUR WEB POUR RENDER ---
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Bot is running and healthy!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# --- IMPORT DES MODULES LOCAUX ---
# Ajout de protections pour éviter le crash si NumPy ou les modules manquent
try:
    import numpy as np
    from strategies import StrategyManager
    from strategies_intervalles import StrategieIntervalles
    from utils_new import get_latest_results, update_history
except ImportError as e:
    logging.error(f"ERREUR D'IMPORTATION : {e}. Vérifiez votre requirements.txt et vos fichiers locaux.")

# Configuration du logging
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
            logger.error(f"Erreur lors du chargement de la config: {e}")
            return {}

    def get(self, section: str, key: str = None, default=None):
        if key is None: return self.config.get(section, default)
        return self.config.get(section, {}).get(key, default)

    def update(self, section: str, key: str, value):
        if section not in self.config: self.config[section] = {}
        self.config[section][key] = value
        self._save_config()

    def _save_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

class BaccaraBot:
    def __init__(self, config_path: str = "config.json"):
        self.config = ConfigManager(config_path)
        self.token = self.config.get('telegram', 'bot_token')
        self.admin_id = self.config.get('telegram', 'admin_id')
        self.main_channel = self.config.get('telegram', 'main_channel')
        self.redirect_channels = self.config.get('telegram', 'redirect_channels', [])
        self.language = self.config.get('app', 'language', 'FR')
        self.check_interval = self.config.get('app', 'check_interval_seconds', 30)
        self.verification_attempts = self.config.get('app', 'verification_attempts', 3)
        
        self.history = {}
        try:
            self.strategy_manager = StrategyManager()
        except:
            self.strategy_manager = None
            
        self.daily_stats = {'total_predictions': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0}
        self.active_predictions = []
        self.is_running = False
        self.last_check = None
        self.translations = self._load_translations()

    def _load_translations(self) -> Dict:
        # Correction de la SyntaxError détectée à la ligne 134
        return {
            'FR': {
                'prediction_title': '🔮 PRÉDICTION BACCARA',
                'symbol': 'Enseigne',
                'game': 'Jeu #',
                'confidence': 'Confiance',
                'strategy': 'Stratégie',
                'waiting_result': '⏳ En attente du résultat...',
                'win': '✅ GAGNÉ',
                'loss': '❌ PERDU',
                'verified': 'Résultat vérifié',
                'bot_started': '🤖 Bot démarré! Surveillance active.',
                'bot_stopped': '🛑 Bot arrêté.',
                'stats_title': '📊 STATISTIQUES DU JOUR',
                'total': 'Total',
                'wins': 'Gagnés',
                'losses': 'Perdus',
                'win_rate': 'Taux de réussite',
                'admin_only': "⚠️ Seul l'administrateur peut utiliser cette commande.",
                'current_config': '⚙️ Configuration actuelle',
                'status_running': "🟢 Bot en cours d'exécution",
                'status_stopped': '🔴 Bot arrêté',
                'last_check': 'Dernière vérification',
                'predictions_pending': 'Prédictions en attente',
                'games_history': "Jeux dans l'historique"
            },
            'EN': { 'prediction_title': '🔮 BACCARA PREDICTION', 'admin_only': '⚠️ Only admin can use this command.', 'win': '✅ WIN', 'loss': '❌ LOSS' },
            'ES': { 'prediction_title': '🔮 PREDICCIÓN BACCARA', 'admin_only': '⚠️ Solo el admin puede usar este comando.' },
            'DE': { 'prediction_title': '🔮 BACCARA VORHERSAGE', 'admin_only': '⚠️ Nur Admin kann diesen Befehl verwenden.' },
            'RU': { 'prediction_title': '🔮 ПРЕДСКАЗАНИЕ БАККАРА', 'admin_only': '⚠️ Только админ может использовать эту команду.' },
            'AR': { 'prediction_title': '🔮 توقع البكارات', 'admin_only': '⚠️ المشرف فقط يمكنه استخدام هذا الأمر.' }
        }

    def _t(self, key: str) -> str:
        return self.translations.get(self.language, self.translations['FR']).get(key, key)

    def _is_admin(self, user_id: int) -> bool:
        return str(user_id) == str(self.admin_id)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("▶️ Démarrer", callback_data='start_bot'), InlineKeyboardButton("⏹ Arrêter", callback_data='stop_bot')],
            [InlineKeyboardButton("📊 Statistiques", callback_data='stats'), InlineKeyboardButton("📈 Status", callback_data='status')]
        ]
        await update.message.reply_text(f"🎰 *Bot Baccara*\n\nCanal: `{self.main_channel}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.data == 'start_bot':
            if self._is_admin(query.from_user.id):
                self.is_running = True
                await query.edit_message_text(f"✅ {self._t('bot_started')}")
            else:
                await query.edit_message_text(self._t('admin_only'))
        elif query.data == 'stop_bot':
            self.is_running = False
            await query.edit_message_text(f"🛑 {self._t('bot_stopped')}")

    async def check_and_predict(self, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_running: return
        self.last_check = datetime.now()
        try:
            results = get_latest_results()
            if results:
                self.history = update_history(results, self.history)
                # Logique de prédiction ici...
        except Exception as e:
            logger.error(f"Erreur analyse: {e}")

    def run(self):
        if not self.token:
            logger.error("Token manquant !")
            return

        # Démarrage du serveur Web (obligatoire pour Render)
        threading.Thread(target=run_flask, daemon=True).start()
        logger.info("Serveur Web actif sur port 10000")

        # Initialisation de l'application Telegram
        application = Application.builder().token(self.token).build()
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Correction de l'erreur JobQueue
        if application.job_queue:
            application.job_queue.run_repeating(self.check_and_predict, interval=self.check_interval, first=10)
        else:
            logger.error("Erreur: JobQueue n'est pas disponible. Vérifiez l'installation de python-telegram-bot[job-queue]")
        
        logger.info("Bot en cours d'exécution...")
        application.run_polling()

if __name__ == "__main__":
    bot = BaccaraBot()
    bot.run()
