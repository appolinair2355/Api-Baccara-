# -*- coding: utf-8 -*-
import random
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict, deque
import numpy as np
from strategies_intervalles import StrategieIntervalles

# === CONSTANTES ===
ENSEIGNES = ["♠️", "♣️", "♦️", "♥️"]
symbol_to_number = {"♣️": 1, "♠️": 0, "♥️": 3, "♦️": 2}
number_to_symbol = {v: k for k, v in symbol_to_number.items()}

# === GESTIONNAIRE DE STRATÉGIES ===
class StrategyManager:
    def __init__(self):
        self.strategie_intervalles = StrategieIntervalles()
        self.strategies = []
        self.current_strategy_index = 0
        self.last_prediction = None
        self._current_strategy = "intervalles"
        self._alternance_mode = False

    def generate_prediction(self, history):
        """Génère une prédiction en utilisant UNIQUEMENT la stratégie intervalles."""
        # Utiliser uniquement la stratégie intervalles
        prediction = self.strategie_intervalles.generer_prediction(history)
        if prediction:
            print("[StrategyManager] Utilisation de la stratégie intervalles")
            return prediction
        else:
            taille_historique = getattr(getattr(self.strategie_intervalles, "analyseur", None), "taille_historique", None)
            if taille_historique is not None:
                print(f"[StrategyManager] La stratégie intervalles n'a pas généré de prédiction (attente de {taille_historique} jeux)")
            else:
                print("[StrategyManager] La stratégie intervalles n'a pas généré de prédiction")
            return None
    
    def set_strategy(self, strategy_name: str):
        """Définit la stratégie active."""
        if strategy_name == "intervalles":
            self.current_strategy_index = 0
            self._current_strategy = "intervalles"
        elif strategy_name == "simple":
            self.current_strategy_index = 1
            self._current_strategy = "simple"
        elif strategy_name == "rotation":
            self.current_strategy_index = 2
            self._current_strategy = "rotation"
        print(f"[StrategyManager] Stratégie changée pour: {strategy_name}")
    
    def toggle_alternance(self):
        """Active/désactive le mode alternance."""
        self._alternance_mode = not self._alternance_mode
        print(f"[StrategyManager] Mode alternance: {'activé' if self._alternance_mode else 'désactivé'}")


# === STRATÉGIE 3 CARTES ===
class StrategyTroisCartes:
    """
    Stratégie 3 Cartes:
    Quand le joueur ET le banquier ont tous les deux 3 cartes au jeu N,
    on prédit la 3ème carte du banquier au jeu N+2.
    La prédiction de l'enseigne est basée sur la fréquence historique.
    """

    SUIT_EMOJI = {0: '♠️', 1: '♣️', 2: '♦️', 3: '♥️'}
    SUIT_NAME  = {0: 'PIQUE', 1: 'TRÈFLE', 2: 'CARREAU', 3: 'CŒUR'}

    def detect_three_card_games(self, history: Dict) -> Dict:
        """Retourne les jeux terminés où joueur ET banquier ont exactement 3 cartes."""
        result = {}
        for game_num, data in history.items():
            if not data.get('is_finished', False):
                continue
            p_cards = data.get('player_cards', [])
            b_cards = data.get('banker_cards', [])
            if len(p_cards) == 3 and len(b_cards) == 3:
                third_banker = b_cards[2]
                suit_code = third_banker.get('S', None)
                if isinstance(suit_code, int):
                    suit_emoji = self.SUIT_EMOJI.get(suit_code, '?')
                    suit_name  = self.SUIT_NAME.get(suit_code, '?')
                else:
                    suit_emoji = str(suit_code) if suit_code else '?'
                    suit_name  = str(suit_code) if suit_code else '?'
                result[game_num] = {
                    'third_banker_suit_code': suit_code,
                    'third_banker_suit':      suit_emoji,
                    'third_banker_suit_name': suit_name,
                    'banker_cards':           b_cards,
                    'player_cards':           p_cards,
                }
        return result

    def _best_suit(self, three_card_games: Dict, exclude_game: int = None):
        """
        Retourne (suit_emoji, count, confidence) de l'enseigne la plus fréquente
        parmi les 3ème cartes banquier historiques.
        """
        suit_counts = {}
        for game_num, data in three_card_games.items():
            if exclude_game is not None and game_num == exclude_game:
                continue
            suit = data['third_banker_suit']
            if suit and suit != '?':
                suit_counts[suit] = suit_counts.get(suit, 0) + 1

        if not suit_counts:
            return None, 0, 0.0

        total      = sum(suit_counts.values())
        best_suit  = max(suit_counts, key=suit_counts.get)
        confidence = suit_counts[best_suit] / total
        return best_suit, suit_counts[best_suit], confidence

    def generate_prediction(self, history: Dict, already_predicted: set):
        """
        Génère une prédiction si un jeu 3-cartes récent n'a pas encore été traité.
        Retourne un dict de prédiction ou None.
        """
        three_card_games = self.detect_three_card_games(history)
        if not three_card_games:
            return None

        for game_num in sorted(three_card_games.keys(), reverse=True):
            if game_num in already_predicted:
                continue

            target_game = game_num + 2
            best_suit, count, confidence = self._best_suit(three_card_games, exclude_game=game_num)

            if not best_suit:
                best_suit  = three_card_games[game_num]['third_banker_suit']
                count      = 1
                confidence = 0.5

            print(f"[TroisCartes] Jeu #{game_num}: joueur+banquier=3 cartes → "
                  f"Prédiction {best_suit} au jeu #{target_game} (conf={confidence:.0%})")

            return {
                'trigger_game':   game_num,
                'target_game':    target_game,
                'predicted_suit': best_suit,
                'sample_count':   len(three_card_games),
                'suit_count':     count,
                'confidence':     confidence,
                'trigger_data':   three_card_games[game_num],
            }

        return None
