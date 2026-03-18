#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram Baccara - Système de prédiction complet
Intègre config.json pour la configuration environnementale
"""

import os
import sys
import json
import time
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, JobQueue,
    MessageHandler, filters, ConversationHandler
)

# Import des modules locaux
# Note: Assurez-vous que ces fichiers existent dans votre dossier projet
try:
    from strategies import StrategyManager
    from strategies_intervalles import StrategieIntervalles
    from utils_new import get_latest_results, update_history
except ImportError as e:
    logging.error(f"Erreur d'importation : {e}. Vérifiez que strategies.py, strategies_intervalles.py et utils_new.py sont présents.")

# Configuration du logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class ConfigManager:
    """Gestionnaire de configuration basé sur config.json."""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Charge la configuration depuis le fichier JSON."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # Configuration par défaut si le fichier n'existe pas
                return {
                    "telegram": {"bot_token": "", "admin_id": 0, "main_channel": ""},
                    "app": {"language": "FR", "check_interval_seconds": 30}
                }
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la config: {e}")
            return {}

    def get(self, section: str, key: str = None, default=None):
        """Récupère une valeur de configuration."""
        if key is None:
            return self.config.get(section, default)
        return self.config.get(section, {}).get(key, default)

    def update(self, section: str, key: str, value):
        """Met à jour une valeur de configuration."""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
        self._save_config()

    def _save_config(self):
        """Sauvegarde la configuration."""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)


class BaccaraBot:
    """Bot principal de prédiction Baccara."""

    def __init__(self, config_path: str = "config.json"):
        # Chargement de la configuration
        self.config = ConfigManager(config_path)

        # Configuration Telegram
        self.token = self.config.get('telegram', 'bot_token')
        self.admin_id = self.config.get('telegram', 'admin_id')
        self.main_channel = self.config.get('telegram', 'main_channel')
        self.redirect_channels = self.config.get('telegram', 'redirect_channels', [])
        self.notify_on_error = self.config.get('telegram', 'notification_on_error', True)

        # Configuration App
        self.language = self.config.get('app', 'language', 'FR')
        self.check_interval = self.config.get('app', 'check_interval_seconds', 30)
        self.verification_attempts = self.config.get('app', 'verification_attempts', 3)
        self.min_games = self.config.get('app', 'min_games_for_analysis', 50)
        self.cycle_size = self.config.get('app', 'prediction_cycle_size', 3)

        # Configuration API
        self.api_url = self.config.get('api', 'url')
        self.api_params = self.config.get('api', 'params', {})
        self.api_timeout = self.config.get('api', 'timeout', 30)

        # État interne
        self.history = {}
        try:
            self.strategy_manager = StrategyManager()
        except NameError:
            self.strategy_manager = None
            
        self.daily_stats = self._load_daily_stats()
        self.active_predictions = []
        self.is_running = False
        self.last_check = None

        # Traductions
        self.translations = self._load_translations()

        logger.info(f"Bot initialisé - Canal: {self.main_channel}, Admin: {self.admin_id}")

    def _load_translations(self) -> Dict:
        """Charge les traductions multilingues."""
        # CORRECTION : Utilisation de doubles guillemets pour gérer les apostrophes françaises
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
                'next_check': 'Prochaine analyse dans {} secondes',
                'bot_started': '🤖 Bot démarré! Surveillance active.',
                'bot_stopped': '🛑 Bot arrêté.',
                'no_prediction': 'Aucune prédiction pour le moment.',
                'stats_title': '📊 STATISTIQUES DU JOUR',
                'total': 'Total',
                'wins': 'Gagnés',
                'losses': 'Perdus',
                'win_rate': 'Taux de réussite',
                'admin_only': "⚠️ Seul l'administrateur peut utiliser cette commande.",
                'config_updated': '✅ Configuration mise à jour.',
                'current_config': '⚙️ Configuration actuelle',
                'status_running': "🟢 Bot en cours d'exécution",
                'status_stopped': '🔴 Bot arrêté',
                'last_check': 'Dernière vérification',
                'predictions_pending': 'Prédictions en attente',
                'games_history': "Jeux dans l'historique"
            },
            'EN': {
                'prediction_title': '🔮 BACCARA PREDICTION',
                'symbol': 'Suit',
                'game': 'Game #',
                'confidence': 'Confidence',
                'strategy': 'Strategy',
                'waiting_result': '⏳ Waiting for result...',
                'win': '✅ WIN',
                'loss': '❌ LOSS',
                'verified': 'Result verified',
                'next_check': 'Next analysis in {} seconds',
                'bot_started': '🤖 Bot started! Active monitoring.',
                'bot_stopped': '🛑 Bot stopped.',
                'no_prediction': 'No prediction at the moment.',
                'stats_title': '📊 TODAY STATISTICS',
                'total': 'Total',
                'wins': 'Wins',
                'losses': 'Losses',
                'win_rate': 'Win rate',
                'admin_only': '⚠️ Only admin can use this command.',
                'config_updated': '✅ Configuration updated.',
                'current_config': '⚙️ Current configuration',
                'status_running': '🟢 Bot running',
                'status_stopped': '🔴 Bot stopped',
                'last_check': 'Last check',
                'predictions_pending': 'Pending predictions',
                'games_history': 'Games in history'
            }
        }

    def _t(self, key: str) -> str:
        """Récupère une traduction."""
        return self.translations.get(self.language, self.translations['FR']).get(key, key)

    def _is_admin(self, user_id: int) -> bool:
        """Vérifie si l'utilisateur est l'admin."""
        return str(user_id) == str(self.admin_id)

    def _load_daily_stats(self) -> Dict:
        """Charge les statistiques journalières."""
        today = datetime.now().strftime('%Y-%m-%d')
        stats_path = self.config.get('paths', 'daily_stats', 'daily_stats.json')
        try:
            if os.path.exists(stats_path):
                with open(stats_path, 'r') as f:
                    stats = json.load(f)
                    return stats.get(today, {'total_predictions': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0})
            return {'total_predictions': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0}
        except Exception:
            return {'total_predictions': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0}

    def _save_daily_stats(self):
        """Sauvegarde les statistiques journalières."""
        today = datetime.now().strftime('%Y-%m-%d')
        stats_path = self.config.get('paths', 'daily_stats', 'daily_stats.json')
        stats = {}
        try:
            if os.path.exists(stats_path):
                with open(stats_path, 'r') as f:
                    stats = json.load(f)
        except Exception:
            pass

        stats[today] = self.daily_stats
        with open(stats_path, 'w') as f:
            json.dump(stats, f, indent=4)

    # ========== COMMANDES TELEGRAM ==========

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /start - Menu principal."""
        user = update.effective_user
        
        keyboard = [
            [InlineKeyboardButton("▶️ Démarrer", callback_data='start_bot'),
             InlineKeyboardButton("⏹ Arrêter", callback_data='stop_bot')],
            [InlineKeyboardButton("📊 Statistiques", callback_data='stats'),
             InlineKeyboardButton("⚙️ Configuration", callback_data='config')],
            [InlineKeyboardButton("📈 Status", callback_data='status')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🎰 *Bot Baccara*\n\n"
            f"Bienvenue {user.first_name}!\n"
            f"📡 Canal: `{self.main_channel}`\n"
            f"⏱ Intervalle: `{self.check_interval}s`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /stats."""
        await update.message.reply_text(self._format_stats(), parse_mode='Markdown')

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /status."""
        status = self._t('status_running') if self.is_running else self._t('status_stopped')
        last_check_str = self.last_check.strftime('%H:%M:%S') if self.last_check else 'Jamais'

        text = (
            f"📊 *{self._t('current_config')}*\n\n"
            f"{status}\n"
            f"🕐 {self._t('last_check')}: {last_check_str}\n"
            f"📋 {self._t('predictions_pending')}: {len(self.active_predictions)}\n"
            f"🎮 {self._t('games_history')}: {len(self.history)}\n"
        )
        await update.message.reply_text(text, parse_mode='Markdown')

    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /config (admin only)."""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text(self._t('admin_only'))
            return

        text = (
            f"⚙️ *{self._t('current_config')}*\n\n"
            f"🌍 Langue: `{self.language}`\n"
            f"⏱ Intervalle: `{self.check_interval}s`"
        )
        await update.message.reply_text(text, parse_mode='Markdown')

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gère les boutons."""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'start_bot':
            if self._is_admin(query.from_user.id):
                self.is_running = True
                await query.edit_message_text(f"✅ {self._t('bot_started')}")
            else:
                await query.edit_message_text(self._t('admin_only'))
        
        elif query.data == 'stop_bot':
            if self._is_admin(query.from_user.id):
                self.is_running = False
                await query.edit_message_text(f"🛑 {self._t('bot_stopped')}")
            else:
                await query.edit_message_text(self._t('admin_only'))

    def _format_stats(self) -> str:
        """Formate les stats."""
        s = self.daily_stats
        return (
            f"📊 *{self._t('stats_title')}*\n\n"
            f"• {self._t('total')}: {s['total_predictions']}\n"
            f"• {self._t('wins')}: {s['wins']} ✅\n"
            f"• {self._t('losses')}: {s['losses']} ❌\n"
            f"• {self._t('win_rate')}: {s['win_rate']:.1%}"
        )

    async def check_and_predict(self, context: ContextTypes.DEFAULT_TYPE):
        """Boucle principale."""
        if not self.is_running:
            return
        # Logique de prédiction...
        self.last_check = datetime.now()

    def run(self):
        """Lancement."""
        if not self.token:
            print("ERREUR: Token manquant dans config.json")
            return

        app = Application.builder().token(self.token).build()

        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("stats", self.stats_command))
        app.add_handler(CommandHandler("status", self.status_command))
        app.add_handler(CommandHandler("config", self.config_command))
        app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))

        # Correction : Les callbacks sont gérés par CallbackQueryHandler, pas CommandHandler
        from telegram.ext import CallbackQueryHandler
        app.add_handler(CallbackQueryHandler(self.button_callback))

        app.job_queue.run_repeating(self.check_and_predict, interval=self.check_interval, first=5)

        print("Bot en ligne...")
        app.run_polling()

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        pass

if __name__ == "__main__":
    bot = BaccaraBot()
    bot.run()
