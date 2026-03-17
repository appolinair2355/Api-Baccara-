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
