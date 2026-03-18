#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram Baccara - Version optimisée avec nouvelle API
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
    MessageHandler, filters
)

# Import des modules optimisés
from strategies import StrategyManager
from strategies_intervalles import StrategieIntervalles
from utils_api import BaccaraAPIClient, update_history, get_api_client

# Configuration du logging avancé
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Créer le dossier logs
os.makedirs('logs', exist_ok=True)


class ConfigManager:
    """Gestionnaire de configuration."""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Config {self.config_path} non trouvé!")
            raise

    def get(self, section: str, key: str = None, default=None):
        if key is None:
            return self.config.get(section, default)
        return self.config.get(section, {}).get(key, default)


class BaccaraBot:
    """Bot principal optimisé."""

    def __init__(self, config_path: str = "config.json"):
        self.config = ConfigManager(config_path)

        # Config Telegram
        self.token = self.config.get('telegram', 'bot_token')
        self.admin_id = self.config.get('telegram', 'admin_id')
        self.main_channel = self.config.get('telegram', 'main_channel')
        self.redirect_channels = self.config.get('telegram', 'redirect_channels', [])

        # Config App
        self.language = self.config.get('app', 'language', 'FR')
        self.check_interval = self.config.get('app', 'check_interval_seconds', 30)
        self.verification_attempts = self.config.get('app', 'verification_attempts', 3)

        # État
        self.history = {}
        self.strategy_manager = StrategyManager()
        self.daily_stats = self._load_daily_stats()
        self.active_predictions = []
        self.is_running = False
        self.last_check = None

        # NOUVEAU: Client API optimisé
        self.api_client = get_api_client(self.config.config)

        # Traductions
        self.translations = self._load_translations()

        logger.info(f"Bot initialisé - Canal: {self.main_channel}")

    def _load_translations(self) -> Dict:
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
                'bot_started': '🤖 Bot démarré!',
                'bot_stopped': '🛑 Bot arrêté.',
                'stats_title': '📊 STATISTIQUES',
                'total': 'Total',
                'wins': 'Gagnés',
                'losses': 'Perdus',
                'win_rate': 'Taux de réussite',
                'admin_only': '⚠️ Seul l'administrateur peut faire ça.',
                'api_status': '📡 Statut API',
                'last_fetch': 'Dernière récupération',
                'cache_status': 'État du cache',
                'games_history': 'Jeux en mémoire'
            }
        }

    def _t(self, key: str) -> str:
        return self.translations.get(self.language, self.translations['FR']).get(key, key)

    def _is_admin(self, user_id: int) -> bool:
        return user_id == self.admin_id

    def _load_daily_stats(self) -> Dict:
        today = datetime.now().strftime('%Y-%m-%d')
        try:
            with open('daily_stats.json', 'r') as f:
                stats = json.load(f)
                return stats.get(today, {'total_predictions': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0})
        except FileNotFoundError:
            return {'total_predictions': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0}

    def _save_daily_stats(self):
        today = datetime.now().strftime('%Y-%m-%d')
        try:
            with open('daily_stats.json', 'r') as f:
                stats = json.load(f)
        except FileNotFoundError:
            stats = {}
        stats[today] = self.daily_stats
        with open('daily_stats.json', 'w') as f:
            json.dump(stats, f, indent=4)

    # ========== COMMANDES ==========

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menu principal."""
        user = update.effective_user

        keyboard = [
            [InlineKeyboardButton("▶️ Démarrer", callback_data='start_bot'),
             InlineKeyboardButton("⏹ Arrêter", callback_data='stop_bot')],
            [InlineKeyboardButton("📊 Stats", callback_data='stats'),
             InlineKeyboardButton("📡 API Status", callback_data='api_status')]
        ]

        await update.message.reply_text(
            f"🎰 *Bot Baccara Optimisé*\n\n"
            f"Bienvenue {user.first_name}!\n"
            f"Canal: `{self.main_channel}`\n"
            f"Langue: `{self.language}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def api_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """NOUVEAU: Statut de l'API."""
        stats = self.api_client.get_stats()

        last_fetch = stats['last_fetch'][:19] if stats['last_fetch'] else 'Jamais'
        cache_valid = "✅ Valide" if stats['cache_valid'] else "❌ Invalide"
        errors = stats['consecutive_errors']

        text = (
            f"📡 *{self._t('api_status')}*\n\n"
            f"🕐 {self._t('last_fetch')}: {last_fetch}\n"
            f"💾 {self._t('cache_status')}: {cache_valid}\n"
            f"⚠️ Erreurs consécutives: {errors}\n"
            f"🎮 {self._t('games_history')}: {len(self.history)}"
        )
        await update.message.reply_text(text, parse_mode='Markdown')

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestion des boutons."""
        query = update.callback_query
        await query.answer()
        user = query.from_user

        if query.data == 'start_bot' and self._is_admin(user.id):
            self.is_running = True
            await query.edit_message_text(f"✅ {self._t('bot_started')}")

        elif query.data == 'stop_bot' and self._is_admin(user.id):
            self.is_running = False
            jobs = context.job_queue.get_jobs_by_name('baccara_monitor')
            for job in jobs:
                job.schedule_removal()
            await query.edit_message_text(f"🛑 {self._t('bot_stopped')}")

        elif query.data == 'stats':
            await self.stats_command(update, context)

        elif query.data == 'api_status':
            await self.api_status_command(update, context)

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Statistiques."""
        total = self.daily_stats['total_predictions']
        wins = self.daily_stats['wins']
        losses = self.daily_stats['losses']
        win_rate = self.daily_stats['win_rate']

        text = (
            f"📊 *{self._t('stats_title')}*\n\n"
            f"• {self._t('total')}: {total}\n"
            f"• {self._t('wins')}: {wins} ✅\n"
            f"• {self._t('losses')}: {losses} ❌\n"
            f"• {self._t('win_rate')}: {win_rate:.1%}"
        )
        await update.message.reply_text(text, parse_mode='Markdown')

    # ========== LOGIQUE PRINCIPALE ==========

    async def check_and_predict(self, context: ContextTypes.DEFAULT_TYPE):
        """Boucle principale optimisée."""
        if not self.is_running:
            return

        try:
            logger.info("Vérification des données...")
            self.last_check = datetime.now()

            # NOUVEAU: Utilise le client API optimisé
            games = self.api_client.get_latest_results()

            if not games:
                logger.warning("Aucun jeu récupéré")
                return

            # Convertir au format legacy pour compatibilité
            results = []
            for game in games:
                results.append({
                    'game_number': game.game_number,
                    'player_cards': game.player_cards,
                    'banker_cards': game.banker_cards,
                    'is_finished': game.is_finished,
                    'winner': game.winner
                })

            # Mettre à jour l'historique
            old_len = len(self.history)
            self.history = update_history(results, self.history)
            new_games = len(self.history) - old_len

            if new_games > 0:
                logger.info(f"{new_games} nouveaux jeux ajoutés")

            # Vérifier les prédictions en attente
            await self._verify_pending_predictions(context)

            # Générer de nouvelles prédictions
            prediction = self.strategy_manager.generate_prediction(self.history)

            if prediction:
                logger.info(f"Nouvelle prédiction: {prediction['symbol']} #{prediction['game_number']}")
                await self._send_prediction(context, prediction)

                self.active_predictions.append({
                    'prediction': prediction,
                    'timestamp': datetime.now(),
                    'verified': False,
                    'result': None,
                    'attempts': 0
                })

                self.daily_stats['total_predictions'] += 1
                self._save_daily_stats()

        except Exception as e:
            logger.error(f"Erreur dans check_and_predict: {e}")

    async def _send_prediction(self, context: ContextTypes.DEFAULT_TYPE, prediction: Dict):
        """Envoie la prédiction."""
        symbol = prediction['symbol']
        game_num = prediction['game_number']
        confidence = prediction.get('confidence', 0)

        text = (
            f"🔮 *{self._t('prediction_title')}* 🔮\n\n"
            f"📌 {self._t('symbol')}: {symbol}\n"
            f"🎲 {self._t('game')}: #{game_num}\n"
            f"📈 {self._t('confidence')}: {confidence:.0%}\n\n"
            f"⏳ {self._t('waiting_result')}"
        )

        try:
            await context.bot.send_message(
                chat_id=self.main_channel,
                text=text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Erreur envoi: {e}")

    async def _verify_pending_predictions(self, context: ContextTypes.DEFAULT_TYPE):
        """Vérifie les prédictions."""
        for pred_data in self.active_predictions[:]:
            if pred_data['verified']:
                continue

            prediction = pred_data['prediction']
            predicted_game = prediction['game_number']
            pred_data['attempts'] += 1

            if pred_data['attempts'] > self.verification_attempts:
                await self._resolve_prediction(context, pred_data, 'loss')
                continue

            if predicted_game in self.history:
                game_data = self.history[predicted_game]
                if game_data.get('is_finished'):
                    # Vérifier si le symbole est présent
                    found = self._check_symbol(prediction['symbol'], game_data.get('player_cards', []))
                    result = 'win' if found else 'loss'
                    await self._resolve_prediction(context, pred_data, result)

    def _check_symbol(self, symbol: str, cards: List[Dict]) -> bool:
        """Vérifie si un symbole est dans les cartes."""
        symbol_map = {'♠️': 0, '♣️': 1, '♦️': 2, '♥️': 3}
        target = symbol_map.get(symbol, -1)

        for card in cards:
            if isinstance(card, dict):
                if card.get('S') == target or card.get('value') == target:
                    return True
        return False

    async def _resolve_prediction(self, context, pred_data, result):
        """Résout une prédiction."""
        prediction = pred_data['prediction']
        pred_data['verified'] = True
        pred_data['result'] = result

        if result == 'win':
            self.daily_stats['wins'] += 1
            text = f"✅ *{self._t('win')}* - Jeu #{prediction['game_number']} - {prediction['symbol']}"
        else:
            self.daily_stats['losses'] += 1
            text = f"❌ *{self._t('loss')}* - Jeu #{prediction['game_number']} - {prediction['symbol']}"

        total = self.daily_stats['total_predictions']
        wins = self.daily_stats['wins']
        self.daily_stats['win_rate'] = wins / total if total > 0 else 0

        try:
            await context.bot.send_message(
                chat_id=self.main_channel,
                text=text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Erreur envoi résultat: {e}")

        self._save_daily_stats()

    def run(self):
        """Démarre le bot."""
        if not self.token:
            logger.error("Token non configuré!")
            return

        application = Application.builder().token(self.token).build()

        # Handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        application.add_handler(CommandHandler("apistatus", self.api_status_command))
        application.add_handler(CommandHandler("button", self.button_callback))

        # Job récurrent
        application.job_queue.run_repeating(
            self.check_and_predict,
            interval=self.check_interval,
            first=10,
            name='baccara_monitor'
        )

        logger.info("Bot démarré!")
        application.run_polling()


if __name__ == "__main__":
    bot = BaccaraBot()
    bot.run()
