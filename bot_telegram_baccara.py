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
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, JobQueue,
    MessageHandler, filters, ConversationHandler
)
from web_server import start_web_server, set_bot

# Import des modules locaux
from strategies import StrategyManager, StrategyTroisCartes
from strategies_intervalles import StrategieIntervalles
from utils_new import get_latest_results, update_history

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
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Fichier de configuration {self.config_path} non trouvé!")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de parsing JSON: {e}")
            raise

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
        self.strategy_manager = StrategyManager()
        self.strategy_trois_cartes = StrategyTroisCartes()
        self.trois_cartes_predicted = set()  # Jeux déjà prédits par la stratégie 3-cartes
        self.daily_stats = self._load_daily_stats()
        self.active_predictions = []
        self.is_running = True   # Collecte de données active dès le démarrage
        self.predictions_enabled = True  # Envoi de prédictions actif par défaut
        self.last_check = None
        self.last_api_game = None

        # Traductions
        self.translations = self._load_translations()

        logger.info(f"Bot initialisé - Canal: {self.main_channel}, Admin: {self.admin_id}")

    def _load_translations(self) -> Dict:
        """Charge les traductions multilingues."""
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
            },
            'ES': {
                'prediction_title': '🔮 PREDICCIÓN BACCARA',
                'symbol': 'Palo',
                'game': 'Juego #',
                'confidence': 'Confianza',
                'strategy': 'Estrategia',
                'waiting_result': '⏳ Esperando resultado...',
                'win': '✅ GANADO',
                'loss': '❌ PERDIDO',
                'verified': 'Resultado verificado',
                'next_check': 'Próximo análisis en {} segundos',
                'bot_started': '🤖 Bot iniciado! Monitoreo activo.',
                'bot_stopped': '🛑 Bot detenido.',
                'no_prediction': 'Sin predicción por el momento.',
                'stats_title': '📊 ESTADÍSTICAS DE HOY',
                'total': 'Total',
                'wins': 'Ganados',
                'losses': 'Perdidos',
                'win_rate': 'Tasa de acierto',
                'admin_only': '⚠️ Solo el admin puede usar este comando.',
                'config_updated': '✅ Configuración actualizada.',
                'current_config': '⚙️ Configuración actual',
                'status_running': '🟢 Bot en ejecución',
                'status_stopped': '🔴 Bot detenido',
                'last_check': 'Última verificación',
                'predictions_pending': 'Predicciones pendientes',
                'games_history': 'Juegos en historial'
            },
            'DE': {
                'prediction_title': '🔮 BACCARA VORHERSAGE',
                'symbol': 'Farbe',
                'game': 'Spiel #',
                'confidence': 'Vertrauen',
                'strategy': 'Strategie',
                'waiting_result': '⏳ Warte auf Ergebnis...',
                'win': '✅ GEWONNEN',
                'loss': '❌ VERLOREN',
                'verified': 'Ergebnis überprüft',
                'next_check': 'Nächste Analyse in {} Sekunden',
                'bot_started': '🤖 Bot gestartet! Aktive Überwachung.',
                'bot_stopped': '🛑 Bot gestoppt.',
                'no_prediction': 'Momentan keine Vorhersage.',
                'stats_title': '📊 HEUTIGE STATISTIK',
                'total': 'Gesamt',
                'wins': 'Gewonnen',
                'losses': 'Verloren',
                'win_rate': 'Erfolgsrate',
                'admin_only': '⚠️ Nur Admin kann diesen Befehl verwenden.',
                'config_updated': '✅ Konfiguration aktualisiert.',
                'current_config': '⚙️ Aktuelle Konfiguration',
                'status_running': '🟢 Bot läuft',
                'status_stopped': '🔴 Bot gestoppt',
                'last_check': 'Letzte Überprüfung',
                'predictions_pending': 'Ausstehende Vorhersagen',
                'games_history': 'Spiele im Verlauf'
            },
            'RU': {
                'prediction_title': '🔮 ПРЕДСКАЗАНИЕ БАККАРА',
                'symbol': 'Масть',
                'game': 'Игра #',
                'confidence': 'Уверенность',
                'strategy': 'Стратегия',
                'waiting_result': '⏳ Ожидание результата...',
                'win': '✅ ВЫИГРЫШ',
                'loss': '❌ ПРОИГРЫШ',
                'verified': 'Результат проверен',
                'next_check': 'Следующий анализ через {} секунд',
                'bot_started': '🤖 Бот запущен! Активное наблюдение.',
                'bot_stopped': '🛑 Бот остановлен.',
                'no_prediction': 'Пока нет предсказаний.',
                'stats_title': '📊 СТАТИСТИКА ЗА СЕГОДНЯ',
                'total': 'Всего',
                'wins': 'Выигрыши',
                'losses': 'Проигрыши',
                'win_rate': 'Процент побед',
                'admin_only': '⚠️ Только админ может использовать эту команду.',
                'config_updated': '✅ Конфигурация обновлена.',
                'current_config': '⚙️ Текущая конфигурация',
                'status_running': '🟢 Бот работает',
                'status_stopped': '🔴 Бот остановлен',
                'last_check': 'Последняя проверка',
                'predictions_pending': 'Ожидающие предсказания',
                'games_history': 'Игр в истории'
            },
            'AR': {
                'prediction_title': '🔮 توقع البكارات',
                'symbol': 'الرمز',
                'game': 'لعبة #',
                'confidence': 'الثقة',
                'strategy': 'الاستراتيجية',
                'waiting_result': '⏳ في انتظار النتيجة...',
                'win': '✅ فوز',
                'loss': '❌ خسارة',
                'verified': 'تم التحقق من النتيجة',
                'next_check': 'التحليل التالي بعد {} ثانية',
                'bot_started': '🤖 تم تشغيل البوت! المراقبة نشطة.',
                'bot_stopped': '🛑 تم إيقاف البوت.',
                'no_prediction': 'لا يوجد توقع في الوقت الحالي.',
                'stats_title': '📊 إحصائيات اليوم',
                'total': 'المجموع',
                'wins': 'الفوز',
                'losses': 'الخسارة',
                'win_rate': 'معدل الفوز',
                'admin_only': '⚠️ المشرف فقط يمكنه استخدام هذا الأمر.',
                'config_updated': '✅ تم تحديث الإعدادات.',
                'current_config': '⚙️ الإعدادات الحالية',
                'status_running': '🟢 البوت يعمل',
                'status_stopped': '🔴 البوت متوقف',
                'last_check': 'آخر فحص',
                'predictions_pending': 'توقعات معلقة',
                'games_history': 'ألعاب في السجل'
            }
        }

    def _t(self, key: str) -> str:
        """Récupère une traduction."""
        return self.translations.get(self.language, self.translations['FR']).get(key, key)

    def _is_admin(self, user_id: int) -> bool:
        """Vérifie si l'utilisateur est l'admin."""
        return user_id == self.admin_id

    def _load_daily_stats(self) -> Dict:
        """Charge les statistiques journalières."""
        today = datetime.now().strftime('%Y-%m-%d')
        stats_path = self.config.get('paths', 'daily_stats', 'daily_stats.json')
        try:
            with open(stats_path, 'r') as f:
                stats = json.load(f)
                return stats.get(today, {'total_predictions': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0})
        except FileNotFoundError:
            return {'total_predictions': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0}

    def _save_daily_stats(self):
        """Sauvegarde les statistiques journalières."""
        today = datetime.now().strftime('%Y-%m-%d')
        stats_path = self.config.get('paths', 'daily_stats', 'daily_stats.json')
        try:
            with open(stats_path, 'r') as f:
                stats = json.load(f)
        except FileNotFoundError:
            stats = {}

        stats[today] = self.daily_stats
        with open(stats_path, 'w') as f:
            json.dump(stats, f, indent=4)

    # ========== COMMANDES TELEGRAM ==========

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /start - Menu principal."""
        user = update.effective_user
        logger.info(f"User {user.id} started the bot")

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
            f"Ce bot analyse les patterns du Baccara et envoie des prédictions.\n\n"
            f"📡 Canal: `{self.main_channel}`\n"
            f"🌍 Langue: `{self.language}`\n"
            f"⏱ Intervalle: `{self.check_interval}s`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /stats - Affiche les statistiques."""
        await update.message.reply_text(self._format_stats(), parse_mode='Markdown')

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /status - État du bot."""
        await update.message.reply_text(self._build_status_text(), parse_mode='Markdown')

    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /config - Modifie la configuration (admin only)."""
        user = update.effective_user

        if not self._is_admin(user.id):
            await update.message.reply_text(self._t('admin_only'))
            return

        text, reply_markup = self._build_config_message()
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    def _build_config_message(self):
        """Construit le message de configuration avec son clavier."""
        keyboard = [
            [InlineKeyboardButton("🌍 Langue", callback_data='cfg_language'),
             InlineKeyboardButton("⏱ Intervalle", callback_data='cfg_interval')],
            [InlineKeyboardButton("🔄 Redirection", callback_data='cfg_redirect'),
             InlineKeyboardButton("✅ Tentatives", callback_data='cfg_attempts')]
        ]
        text = (
            f"⚙️ *{self._t('current_config')}*\n\n"
            f"🌍 Langue: `{self.language}`\n"
            f"⏱ Intervalle: `{self.check_interval}s`\n"
            f"✅ Tentatives: `{self.verification_attempts}`\n"
            f"📡 Canal: `{self.main_channel}`\n"
            f"🔄 Redirection: `{len(self.redirect_channels)} canaux`"
        )
        return text, InlineKeyboardMarkup(keyboard)

    def _build_status_text(self) -> str:
        """Construit le texte de statut."""
        collecte = "🟢 Active" if self.is_running else "🔴 Arrêtée"
        predictions = "🟢 Activées" if self.predictions_enabled else "🔴 Désactivées"
        last_check = self.last_check.strftime('%H:%M:%S') if self.last_check else 'Jamais'
        last_game = f"#{self.last_api_game['game_number']}" if self.last_api_game else 'En attente...'
        return (
            f"📊 *État du Bot*\n\n"
            f"📡 Collecte de données : {collecte}\n"
            f"🔮 Envoi de prédictions : {predictions}\n"
            f"🕐 {self._t('last_check')}: `{last_check}`\n"
            f"🔢 Dernier jeu API: `{last_game}`\n"
            f"📋 {self._t('predictions_pending')}: `{len(self.active_predictions)}`\n"
            f"🎮 {self._t('games_history')}: `{len(self.history)}`\n\n"
            f"📡 Canal: `{self.main_channel}`\n"
            f"👤 Admin: `{self.admin_id}`"
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gère les callbacks de tous les boutons inline."""
        query = update.callback_query
        await query.answer()
        user = query.from_user

        # ── Boutons du menu principal ──────────────────────────────────────
        if query.data == 'start_bot':
            if self._is_admin(user.id):
                await self._start_bot(query)
            else:
                await query.edit_message_text(self._t('admin_only'))

        elif query.data == 'stop_bot':
            if self._is_admin(user.id):
                await self._stop_bot(query, context)
            else:
                await query.edit_message_text(self._t('admin_only'))

        elif query.data == 'stats':
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data='menu')]]
            await query.edit_message_text(
                self._format_stats(),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        elif query.data == 'status':
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data='menu')]]
            await query.edit_message_text(
                self._build_status_text(),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        elif query.data == 'config':
            if not self._is_admin(user.id):
                await query.edit_message_text(self._t('admin_only'))
                return
            text, reply_markup = self._build_config_message()
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        elif query.data == 'menu':
            keyboard = [
                [InlineKeyboardButton("▶️ Démarrer", callback_data='start_bot'),
                 InlineKeyboardButton("⏹ Arrêter", callback_data='stop_bot')],
                [InlineKeyboardButton("📊 Statistiques", callback_data='stats'),
                 InlineKeyboardButton("⚙️ Configuration", callback_data='config')],
                [InlineKeyboardButton("📈 Status", callback_data='status')]
            ]
            await query.edit_message_text(
                "🎰 *Bot Baccara* — Menu principal",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        # ── Boutons de configuration ───────────────────────────────────────
        elif query.data == 'cfg_language':
            if not self._is_admin(user.id):
                await query.edit_message_text(self._t('admin_only'))
                return
            langs = ['FR', 'EN', 'ES', 'DE', 'RU', 'AR']
            keyboard = [
                [InlineKeyboardButton(
                    f"{'✅ ' if lg == self.language else ''}{lg}",
                    callback_data=f'set_lang_{lg}'
                ) for lg in langs],
                [InlineKeyboardButton("🔙 Retour", callback_data='config')]
            ]
            await query.edit_message_text(
                f"🌍 *Choisir la langue*\nLangue actuelle: `{self.language}`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        elif query.data.startswith('set_lang_'):
            if not self._is_admin(user.id):
                await query.edit_message_text(self._t('admin_only'))
                return
            new_lang = query.data.replace('set_lang_', '')
            self.language = new_lang
            self.config.update('app', 'language', new_lang)
            text, reply_markup = self._build_config_message()
            await query.edit_message_text(
                f"✅ Langue changée en `{new_lang}`\n\n" + text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif query.data == 'cfg_interval':
            if not self._is_admin(user.id):
                await query.edit_message_text(self._t('admin_only'))
                return
            options = [15, 30, 60, 120]
            keyboard = [
                [InlineKeyboardButton(
                    f"{'✅ ' if iv == self.check_interval else ''}{iv}s",
                    callback_data=f'set_interval_{iv}'
                ) for iv in options],
                [InlineKeyboardButton("🔙 Retour", callback_data='config')]
            ]
            await query.edit_message_text(
                f"⏱ *Choisir l'intervalle de vérification*\nActuel: `{self.check_interval}s`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        elif query.data.startswith('set_interval_'):
            if not self._is_admin(user.id):
                await query.edit_message_text(self._t('admin_only'))
                return
            new_interval = int(query.data.replace('set_interval_', ''))
            self.check_interval = new_interval
            self.config.update('app', 'check_interval_seconds', new_interval)
            text, reply_markup = self._build_config_message()
            await query.edit_message_text(
                f"✅ Intervalle changé à `{new_interval}s`\n\n" + text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif query.data == 'cfg_attempts':
            if not self._is_admin(user.id):
                await query.edit_message_text(self._t('admin_only'))
                return
            options = [1, 2, 3, 5, 10]
            keyboard = [
                [InlineKeyboardButton(
                    f"{'✅ ' if n == self.verification_attempts else ''}{n}",
                    callback_data=f'set_attempts_{n}'
                ) for n in options],
                [InlineKeyboardButton("🔙 Retour", callback_data='config')]
            ]
            await query.edit_message_text(
                f"✅ *Nombre de tentatives de vérification*\nActuel: `{self.verification_attempts}`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        elif query.data.startswith('set_attempts_'):
            if not self._is_admin(user.id):
                await query.edit_message_text(self._t('admin_only'))
                return
            new_attempts = int(query.data.replace('set_attempts_', ''))
            self.verification_attempts = new_attempts
            self.config.update('app', 'verification_attempts', new_attempts)
            text, reply_markup = self._build_config_message()
            await query.edit_message_text(
                f"✅ Tentatives changées à `{new_attempts}`\n\n" + text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif query.data == 'cfg_redirect':
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data='config')]]
            await query.edit_message_text(
                f"🔄 *Canaux de redirection*\n\n"
                f"Canaux actuels: `{self.redirect_channels if self.redirect_channels else 'Aucun'}`\n\n"
                f"Pour modifier, utilisez la commande:\n`/redirect CHANNEL_ID`",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

    async def _start_bot(self, query):
        """Active l'envoi de prédictions."""
        if not self.predictions_enabled:
            self.predictions_enabled = True
            await query.edit_message_text(
                f"✅ {self._t('bot_started')}\n"
                f"Prédictions activées. Surveillance toutes les {self.check_interval} secondes."
            )
        else:
            await query.edit_message_text("✅ Les prédictions sont déjà actives.")

    async def _stop_bot(self, query, context):
        """Désactive l'envoi de prédictions (la collecte de données continue)."""
        self.predictions_enabled = False
        await query.edit_message_text(
            f"🛑 {self._t('bot_stopped')}\n"
            f"_La collecte de données continue en arrière-plan._",
            parse_mode='Markdown'
        )

    def _format_stats(self) -> str:
        """Formate les statistiques."""
        total = self.daily_stats['total_predictions']
        wins = self.daily_stats['wins']
        losses = self.daily_stats['losses']
        win_rate = self.daily_stats['win_rate']

        return (
            f"📊 *{self._t('stats_title')}*\n\n"
            f"• {self._t('total')}: {total}\n"
            f"• {self._t('wins')}: {wins} ✅\n"
            f"• {self._t('losses')}: {losses} ❌\n"
            f"• {self._t('win_rate')}: {win_rate:.1%}"
        )

    # ========== LOGIQUE PRINCIPALE ==========

    async def check_and_predict(self, context: ContextTypes.DEFAULT_TYPE):
        """Fonction principale exécutée périodiquement.
        La collecte de données est TOUJOURS active.
        Les prédictions ne sont envoyées que si predictions_enabled = True.
        """
        try:
            logger.info("Checking for new data...")
            self.last_check = datetime.now()

            # 1. Récupérer les nouveaux résultats (toujours)
            results = get_latest_results()
            if not results:
                logger.warning("No data from API")
                return

            # 2. Mémoriser le dernier jeu récupéré (toujours, même sans prédictions)
            self.last_api_game = max(results, key=lambda r: r['game_number'])

            # 3. Mettre à jour l'historique
            old_len = len(self.history)
            self.history = update_history(results, self.history)
            new_games = len(self.history) - old_len

            if new_games > 0:
                logger.info(f"Added {new_games} new games")

            # 4. Si les prédictions sont désactivées, on s'arrête ici
            if not self.predictions_enabled:
                return

            # 3. Vérifier les prédictions en attente
            await self._verify_pending_predictions(context)

            # 4. Générer de nouvelles prédictions (stratégie 3 cartes)
            prediction = self.strategy_trois_cartes.generate_prediction(
                self.history, self.trois_cartes_predicted
            )

            if prediction:
                self.trois_cartes_predicted.add(prediction['trigger_game'])
                logger.info(
                    f"New prediction: {prediction['predicted_suit']} "
                    f"for game #{prediction['target_game']}"
                )
                message_id = await self._send_prediction(context, prediction)

                self.active_predictions.append({
                    'prediction': prediction,
                    'timestamp': datetime.now(),
                    'verified': False,
                    'result': None,
                    'message_id': message_id,
                    'check_offset': 0,
                })

                self.daily_stats['total_predictions'] += 1
                self._save_daily_stats()

        except Exception as e:
            logger.error(f"Error in check_and_predict: {e}")
            if self.notify_on_error:
                await self._notify_admin(context, f"Error: {e}")

    SUIT_NAMES = {'♠️': 'Pique', '♣️': 'Trèfle', '♦️': 'Carreau', '♥️': 'Cœur'}
    OFFSET_EMOJIS = {0: '0️⃣', 1: '1️⃣', 2: '2️⃣', 3: '3️⃣'}

    async def _send_prediction(self, context: ContextTypes.DEFAULT_TYPE, prediction: Dict) -> Optional[int]:
        """Envoie la prédiction vers le canal et retourne le message_id."""
        suit = prediction['predicted_suit']
        suit_name = self.SUIT_NAMES.get(suit, suit)
        game_num = prediction['target_game']

        text = (
            f"🎰 PRÉDICTION #{game_num}\n"
            f"🎯 Couleur: {suit} {suit_name}\n"
            f"⏳ Statut: EN ATTENTE DU RÉSULTAT..."
        )

        msg = None
        try:
            msg = await context.bot.send_message(
                chat_id=self.main_channel,
                text=text
            )
            logger.info(f"Prediction sent to {self.main_channel} (msg_id={msg.message_id})")

            for redirect_id in self.redirect_channels:
                if redirect_id:
                    try:
                        await context.bot.send_message(
                            chat_id=redirect_id,
                            text=text
                        )
                    except Exception as e:
                        logger.error(f"Redirect failed to {redirect_id}: {e}")

        except Exception as e:
            logger.error(f"Failed to send prediction: {e}")

        return msg.message_id if msg else None

    async def _verify_pending_predictions(self, context: ContextTypes.DEFAULT_TYPE):
        """Vérifie les prédictions en attente avec vérification progressive N, N+1, N+2, N+3."""
        for pred_data in self.active_predictions[:]:
            if pred_data['verified']:
                continue

            prediction = pred_data['prediction']
            target_game = prediction['target_game']
            predicted_suit = prediction['predicted_suit']
            offset = pred_data.get('check_offset', 0)

            # Vérifier les offsets depuis le dernier point d'arrêt
            while offset <= 3:
                check_game = target_game + offset

                # Si le jeu n'est pas encore dans l'historique, on attend
                if check_game not in self.history:
                    break

                game_data = self.history[check_game]

                # Si le jeu n'est pas encore terminé, on attend
                if not game_data.get('is_finished'):
                    break

                # Le jeu est disponible : vérifier la couleur dans les cartes du joueur
                player_cards = game_data.get('player_cards', [])
                found = self._check_symbol_in_cards(predicted_suit, player_cards)

                if found:
                    await self._resolve_prediction(context, pred_data, 'win', offset)
                    break
                else:
                    if offset == 3:
                        # Dernier offset atteint sans succès : PERDU
                        await self._resolve_prediction(context, pred_data, 'loss', offset)
                        break
                    else:
                        # Passer à l'offset suivant
                        pred_data['check_offset'] = offset + 1
                        offset += 1

    async def _resolve_prediction(self, context, pred_data, result, offset: int = 0):
        """Résout une prédiction en éditant le message original."""
        prediction = pred_data['prediction']
        pred_data['verified'] = True
        pred_data['result'] = result

        suit = prediction['predicted_suit']
        suit_name = self.SUIT_NAMES.get(suit, suit)
        game_num = prediction['target_game']

        if result == 'win':
            self.daily_stats['wins'] += 1
            offset_emoji = self.OFFSET_EMOJIS.get(offset, '')
            status = f"✅{offset_emoji} GAGNÉ"
        else:
            self.daily_stats['losses'] += 1
            status = "❌ PERDU"

        text = (
            f"🎰 PRÉDICTION #{game_num}\n"
            f"🎯 Couleur: {suit} {suit_name}\n"
            f"📊 Statut: {status}"
        )

        # Mettre à jour le win rate
        total = self.daily_stats['total_predictions']
        wins = self.daily_stats['wins']
        self.daily_stats['win_rate'] = wins / total if total > 0 else 0

        # Éditer le message original, ou envoyer un nouveau si pas de message_id
        message_id = pred_data.get('message_id')
        try:
            if message_id:
                await context.bot.edit_message_text(
                    chat_id=self.main_channel,
                    message_id=message_id,
                    text=text
                )
            else:
                await context.bot.send_message(
                    chat_id=self.main_channel,
                    text=text
                )
        except Exception as e:
            logger.error(f"Failed to update prediction result: {e}")

        self._save_daily_stats()

    def _check_symbol_in_cards(self, symbol: str, cards: List[Dict]) -> bool:
        """Vérifie si un symbole est dans les cartes.
        Supporte les deux formats : emoji (ex: '♠️') et entier (ex: 0).
        """
        symbol_int_map = {'♠️': 0, '♣️': 1, '♦️': 2, '♥️': 3}
        target_int = symbol_int_map.get(symbol, -1)

        for card in cards:
            if not isinstance(card, dict):
                continue
            s = card.get('S')
            # Comparaison directe emoji → emoji (format utils_new.py)
            if s == symbol:
                return True
            # Comparaison entier → entier (format alternatif)
            if isinstance(s, int) and s == target_int:
                return True
            # raw field (utilisé dans certains formats)
            raw = card.get('raw')
            if isinstance(raw, int) and raw == target_int:
                return True
        return False

    async def _notify_admin(self, context: ContextTypes.DEFAULT_TYPE, message: str):
        """Notifie l'admin en cas d'erreur."""
        try:
            await context.bot.send_message(
                chat_id=self.admin_id,
                text=f"⚠️ *Alerte Admin*\n\n{message}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

    # ========== COMMANDES CARTES / JEU ==========

    def _format_cards(self, cards: List[Dict]) -> str:
        """Formate une liste de cartes en texte lisible : ex. ♠️2  ♦️7  ♥️K"""
        if not cards:
            return '—'
        rank_labels = {
            1: 'A', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'
        }
        parts = []
        for c in cards:
            suit = c.get('S', '?')
            rank = c.get('R', '?')
            if isinstance(rank, int):
                label = rank_labels.get(rank, str(rank % 10) if rank >= 10 else str(rank))
            else:
                label = str(rank)
            parts.append(f"{suit}{label}")
        return '  '.join(parts)

    def _format_single_game(self, game_number: int, game_data: Dict, title: str = "") -> str:
        """Formate les infos complètes d'un jeu."""
        player_cards = game_data.get('player_cards', [])
        banker_cards = game_data.get('banker_cards', [])
        winner = game_data.get('winner')
        score = game_data.get('score', {})
        is_finished = game_data.get('is_finished', False)

        p_score = score.get('S1', '?') if score else '?'
        b_score = score.get('S2', '?') if score else '?'

        if winner == 'Player':
            winner_str = "👤 Joueur gagne"
        elif winner == 'Banker':
            winner_str = "🏦 Banquier gagne"
        elif winner == 'Tie':
            winner_str = "🤝 Égalité"
        else:
            winner_str = "⏳ En cours"

        etat = "✅ Terminé" if is_finished else "⏳ En cours"

        header = f"*{title}* " if title else ""
        return (
            f"{header}🎴 *Jeu #{game_number}*\n"
            f"├ 👤 Joueur  : `{self._format_cards(player_cards)}`\n"
            f"├ 🏦 Banquier: `{self._format_cards(banker_cards)}`\n"
            f"├ 🏆 Gagnant : {winner_str}\n"
            f"├ 📊 Score   : `{p_score} - {b_score}`\n"
            f"└ {etat}"
        )

    # ========== FORMAT COMPACT DES PARTIES ==========

    def _fmt_rank(self, r) -> str:
        """Convertit le rang brut en label: 0→10, 1→A, 11→J, 12→Q, 13→K."""
        rank_labels = {0: '10', 1: 'A', 10: '10', 11: 'J', 12: 'Q', 13: 'K'}
        if isinstance(r, int):
            return rank_labels.get(r, str(r))
        return str(r)

    def _fmt_cards_inline(self, cards: List[Dict]) -> str:
        """Formate les cartes en ligne collée: ex. 8♦️2♣️J♦️"""
        parts = []
        for c in cards:
            r = self._fmt_rank(c.get('R', '?'))
            s = c.get('S', '?')
            parts.append(f"{r}{s}")
        return ''.join(parts)

    def _format_game_line(self, game_number: int, game_data: Dict) -> str:
        """
        Formate un jeu en une ligne compacte.
        Exemple joueur en cours  : ⏰#N502. ▶️10(8♣️J♥️) - 20(A♠️9♥️)
        Exemple banquier en cours : ⏰#N499. 19(9♣️10♥️) - ▶️14(Q♠️K♥️)
        Exemple terminé           : #N485. 0(8♦️2♣️J♦️) - ✅5(10♦️5♠️) #T5
        Exemple nul               : #N485. 3(8♦️2♣️) 🔰 3(10♦️5♠️) #T6
        """
        is_finished = game_data.get('is_finished', False)
        p_cards = game_data.get('player_cards', [])
        b_cards = game_data.get('banker_cards', [])
        p_cards_str = self._fmt_cards_inline(p_cards)
        b_cards_str = self._fmt_cards_inline(b_cards)
        score = game_data.get('score', {}) or {}
        p_score = score.get('S1', '')
        b_score = score.get('S2', '')

        if not is_finished:
            p_count = len(p_cards)
            b_count = len(b_cards)
            # Si le joueur a plus de cartes que le banquier → c'est le tour du banquier
            if p_count > b_count:
                p_marker = ''
                b_marker = '▶️'
            else:
                # Sinon (égal ou banquier en avance) → joueur en cours
                p_marker = '▶️'
                b_marker = ''
            p_score_str = str(p_score) if p_score != '' else ''
            b_score_str = str(b_score) if b_score != '' else ''
            p_part = f"{p_marker}{p_score_str}({p_cards_str})" if p_cards_str else f"{p_marker}(—)"
            b_part = f"{b_marker}{b_score_str}({b_cards_str})" if b_cards_str else f"{b_marker}(—)"
            return f"⏰#N{game_number}. {p_part} - {b_part}"

        winner = game_data.get('winner')

        if winner == 'Tie':
            sep = '🔰'
            p_prefix = ''
            b_prefix = ''
        else:
            sep = '-'
            p_prefix = '✅' if winner == 'Player' else ''
            b_prefix = '✅' if winner == 'Banker' else ''

        try:
            total = int(p_score) + int(b_score)
            total_str = f"#T{total}"
        except (TypeError, ValueError):
            total_str = "#T?"

        return (
            f"#N{game_number}. "
            f"{p_prefix}{p_score}({p_cards_str}) "
            f"{sep} "
            f"{b_prefix}{b_score}({b_cards_str}) "
            f"{total_str}"
        )

    async def parties_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /parties - Affiche les jeux récupérés de l'API en format compact."""
        await update.message.reply_text("⏳ Récupération des données...", parse_mode='Markdown')

        # Récupérer les données fraîches de l'API
        results = get_latest_results()

        lines = ["🎰 *Parties Baccara en cours / récentes*\n"]

        if results:
            results_sorted = sorted(results, key=lambda r: r['game_number'])
            for r in results_sorted:
                lines.append(self._format_game_line(r['game_number'], r))
        else:
            lines.append("⚠️ Aucune donnée disponible depuis l'API.")

        # Historique récent (8 dernières parties terminées)
        finished = {k: v for k, v in self.history.items() if v.get('is_finished')}
        if finished:
            recent_nums = sorted(finished.keys(), reverse=True)[:8]
            # Exclure ceux déjà dans les résultats API
            api_nums = {r['game_number'] for r in results} if results else set()
            extra = [n for n in sorted(recent_nums) if n not in api_nums]
            if extra:
                lines.append("\n📋 *Historique récent:*")
                for num in extra:
                    lines.append(self._format_game_line(num, finished[num]))

        text = '\n'.join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n_...tronqué_"

        try:
            await update.message.reply_text(text, parse_mode='Markdown')
        except Exception:
            await update.message.reply_text(text)

    # ========== COMMANDE REDIRECTION ==========

    async def redirect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /redirect [add|remove|list] [CHANNEL_ID]
        - /redirect list              → affiche les canaux
        - /redirect add -1001234567  → ajoute un canal
        - /redirect remove -1001234  → retire un canal
        - /redirect -1001234567      → raccourci pour add
        """
        user = update.effective_user
        if not self._is_admin(user.id):
            await update.message.reply_text(self._t('admin_only'))
            return

        args = context.args or []

        # Pas d'argument ou 'list'
        if not args or args[0].lower() == 'list':
            if self.redirect_channels:
                ch_list = '\n'.join(f"• `{c}`" for c in self.redirect_channels)
                text = f"📡 *Canaux de redirection actifs:*\n{ch_list}"
            else:
                text = (
                    "📡 Aucun canal de redirection configuré.\n\n"
                    "*Commandes:*\n"
                    "`/redirect add -1001234567890` — ajouter\n"
                    "`/redirect remove -1001234567890` — retirer\n"
                    "`/redirect list` — lister"
                )
            await update.message.reply_text(text, parse_mode='Markdown')
            return

        # Raccourci: /redirect ID (sans add/remove)
        if args[0] not in ('add', 'remove') and len(args) == 1:
            args = ['add'] + args

        action = args[0].lower()

        if len(args) < 2:
            await update.message.reply_text(
                "❌ ID manquant.\nExemple: `/redirect add -1001234567890`",
                parse_mode='Markdown'
            )
            return

        try:
            channel_id = int(args[1])
        except ValueError:
            await update.message.reply_text(
                "❌ ID invalide. L'ID doit être un entier.\nExemple: `-1001234567890`",
                parse_mode='Markdown'
            )
            return

        if action == 'add':
            if channel_id in self.redirect_channels:
                await update.message.reply_text(
                    f"⚠️ Canal `{channel_id}` déjà dans la liste.", parse_mode='Markdown'
                )
            else:
                self.redirect_channels.append(channel_id)
                self.config.update('telegram', 'redirect_channels', self.redirect_channels)
                await update.message.reply_text(
                    f"✅ Canal `{channel_id}` ajouté aux redirections.\n"
                    f"Total: {len(self.redirect_channels)} canal(aux)",
                    parse_mode='Markdown'
                )

        elif action == 'remove':
            if channel_id in self.redirect_channels:
                self.redirect_channels.remove(channel_id)
                self.config.update('telegram', 'redirect_channels', self.redirect_channels)
                await update.message.reply_text(
                    f"✅ Canal `{channel_id}` retiré des redirections.\n"
                    f"Total restant: {len(self.redirect_channels)}",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"⚠️ Canal `{channel_id}` non trouvé dans la liste.", parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(
                "❌ Action inconnue. Utilisez `add`, `remove` ou `list`.", parse_mode='Markdown'
            )

    async def jeu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /jeu - Affiche le dernier jeu terminé avec ses cartes."""
        # Trouver le dernier jeu terminé dans l'historique
        finished_games = {k: v for k, v in self.history.items() if v.get('is_finished')}

        if not finished_games:
            # Aucun jeu terminé, afficher le dernier récupéré (prématch)
            if self.last_api_game is None:
                await update.message.reply_text(
                    "⏳ *Aucune donnée disponible pour l'instant.*\n"
                    "Le bot est en train de collecter les résultats, réessaie dans 30 secondes.",
                    parse_mode='Markdown'
                )
                return

            g = self.last_api_game
            await update.message.reply_text(
                f"⏳ *Jeu en attente*\n\n"
                f"🔢 Numéro : `#{g.get('game_number', '?')}`\n"
                f"📡 Statut : Prématch / En cours\n\n"
                f"_Aucun jeu terminé en mémoire pour l'instant._",
                parse_mode='Markdown'
            )
            return

        # Dernier jeu terminé
        last_num = max(finished_games.keys())
        last_game = finished_games[last_num]

        # Bloc principal
        text = "🎰 *DERNIER JEU BACCARA*\n\n"
        text += self._format_single_game(last_num, last_game)

        # Historique des 4 jeux précédents
        previous = sorted([k for k in finished_games if k != last_num], reverse=True)[:4]
        if previous:
            text += "\n\n```\n─────────────────```\n"
            text += "📋 *Jeux précédents :*\n\n"
            for num in previous:
                g = finished_games[num]
                winner = g.get('winner', '')
                icon = "👤" if winner == 'Player' else "🏦" if winner == 'Banker' else "🤝"
                p_cards = self._format_cards(g.get('player_cards', []))
                b_cards = self._format_cards(g.get('banker_cards', []))
                text += (
                    f"*Jeu #{num}* {icon}\n"
                    f"  👤 `{p_cards}`  🏦 `{b_cards}`\n\n"
                )

        text += f"\n_🎮 Total en mémoire : {len(finished_games)} jeux_"

        await update.message.reply_text(text, parse_mode='Markdown')

    async def dernier_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /dernier - Alias de /jeu."""
        await self.jeu_command(update, context)

    # ========== UPLOAD DE FICHIERS ==========

    async def upload_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /upload."""
        await update.message.reply_text(
            "📎 Envoyez un fichier .txt ou .pdf contenant la liste des costumes."
        )

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite les documents uploadés."""
        document = update.message.document
        file_name = document.file_name.lower()

        if file_name.endswith('.txt') or file_name.endswith('.pdf'):
            # Créer le dossier uploads
            uploads_dir = self.config.get('paths', 'uploads_dir', 'uploads/')
            os.makedirs(uploads_dir, exist_ok=True)

            # Télécharger
            file = await context.bot.get_file(document.file_id)
            temp_path = os.path.join(uploads_dir, document.file_name)
            await file.download_to_drive(temp_path)

            await update.message.reply_text(
                f"✅ Fichier `{document.file_name}` reçu!\n"
                f"Traitement en cours...",
                parse_mode='Markdown'
            )

            # TODO: Logique de traitement du fichier
        else:
            await update.message.reply_text(
                "❌ Format non supporté. Envoyez un fichier .txt ou .pdf"
            )

    # ========== DÉMARRAGE ==========

    def run(self):
        """Démarre le bot."""
        if not self.token:
            logger.error("Bot token not configured!")
            return

        # Démarrer le serveur HTTP pour Render.com (port 10000 par défaut)
        web_port = int(os.environ.get("PORT", 10000))
        set_bot(self)
        start_web_server(port=web_port)

        application = Application.builder().token(self.token).build()

        # Commandes
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("config", self.config_command))
        application.add_handler(CommandHandler("upload", self.upload_command))
        application.add_handler(CommandHandler("dernier", self.dernier_command))
        application.add_handler(CommandHandler("jeu", self.jeu_command))
        application.add_handler(CommandHandler("parties", self.parties_command))
        application.add_handler(CommandHandler("redirect", self.redirect_command))

        # Callbacks inline (boutons)
        application.add_handler(CallbackQueryHandler(self.button_callback))

        # Documents
        application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))

        # Job récurrent
        application.job_queue.run_repeating(
            self.check_and_predict,
            interval=self.check_interval,
            first=10,
            name='baccara_monitor'
        )

        logger.info("Starting Baccara Bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = BaccaraBot()
    bot.run()
