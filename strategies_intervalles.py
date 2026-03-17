#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stratégie d'analyse par intervalles - Cœur du système de prédiction
Analyse les patterns réguliers dans l'apparition des enseignes
"""

import json
import math
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from datetime import datetime

class IntervalAnalyseur:
    """Analyse les intervalles entre apparitions des cartes."""

    def __init__(self, min_games: int = 50):
        self.min_games = min_games
        self.enseigne_actuelle = None
        self.intervalle_choisi = None
        self.debut_cycle = None
        self.cycle_predictions = []
        self.taille_historique = 0

        # Mapping des symboles
        self.symbol_map = {
            0: 'PIQUE', 1: 'TREFLE', 2: 'CARREAU', 3: 'COEUR',
            '♠️': 'PIQUE', '♣️': 'TREFLE', '♦️': 'CARREAU', '♥️': 'COEUR'
        }
        self.reverse_map = {v: k for k, v in self.symbol_map.items() if isinstance(k, int)}

    def extraire_symboles_joueur(self, history: Dict) -> List[Tuple[int, str]]:
        """Extrait les symboles des cartes du joueur de l'historique."""
        symboles = []

        for game_num, game_data in sorted(history.items()):
            if not game_data.get('is_finished', False):
                continue

            player_cards = game_data.get('player_cards', [])

            for card in player_cards:
                if isinstance(card, dict) and 'S' in card:
                    symbol_code = card['S']
                    symbol_name = self.symbol_map.get(symbol_code, f"UNKNOWN_{symbol_code}")
                    symboles.append((game_num, symbol_name))

        self.taille_historique = len(symboles)
        return symboles

    def calculer_intervalles(self, symboles: List[Tuple[int, str]]) -> Dict:
        """Calcule les intervalles entre apparitions pour chaque enseigne."""
        intervalles = defaultdict(lambda: {'positions': [], 'ecarts': []})

        # Grouper par enseigne
        for game_num, symbol in symboles:
            intervalles[symbol]['positions'].append(game_num)

        # Calculer les écarts
        for enseigne, data in intervalles.items():
            positions = sorted(data['positions'])
            if len(positions) >= 2:
                ecarts = [positions[i+1] - positions[i] for i in range(len(positions)-1)]
                intervalles[enseigne]['ecarts'] = ecarts
                intervalles[enseigne]['min'] = min(ecarts)
                intervalles[enseigne]['max'] = max(ecarts)
                intervalles[enseigne]['moyen'] = sum(ecarts) / len(ecarts)
                intervalles[enseigne]['count'] = len(positions)
            else:
                intervalles[enseigne]['min'] = float('inf')
                intervalles[enseigne]['max'] = 0
                intervalles[enseigne]['moyen'] = 0
                intervalles[enseigne]['ecarts'] = []
                intervalles[enseigne]['count'] = len(positions)

        return dict(intervalles)

    def calculer_score_exploitabilite(self, intervalles: Dict) -> Dict:
        """
        Calcule un score d'exploitabilité basé sur la régularité.
        Un intervalle régulier vaut mieux qu'un intervalle court mais irrégulier.
        """
        scores = {}

        for enseigne, data in intervalles.items():
            if data['count'] < 3 or not data['ecarts']:
                scores[enseigne] = 0
                continue

            ecarts = data['ecarts']
            moyen = data['moyen']

            # Calcul de la variance (régularité)
            variance = sum((e - moyen) ** 2 for e in ecarts) / len(ecarts)
            ecart_type = math.sqrt(variance)

            # Coefficient de variation (plus c'est faible, plus c'est régulier)
            cv = ecart_type / moyen if moyen > 0 else float('inf')

            # Score de régularité (0-1, 1 = parfaitement régulier)
            regularite = max(0, 1 - cv)

            # Bonus pour les intervalles courts (mais pas trop)
            # Un intervalle de 3-8 est idéal (ni trop court ni trop long)
            if 3 <= moyen <= 8:
                bonus_intervalle = 1.0
            elif 8 < moyen <= 15:
                bonus_intervalle = 0.8
            else:
                bonus_intervalle = 0.6

            # Pénalité si trop peu d'occurrences
            if data['count'] < 5:
                bonus_count = 0.5
            elif data['count'] < 10:
                bonus_count = 0.8
            else:
                bonus_count = 1.0

            # Score final
            score = regularite * bonus_intervalle * bonus_count
            scores[enseigne] = score

            # Debug info
            data['regularite'] = regularite
            data['cv'] = cv
            data['score'] = score

        return scores

    def choisir_enseigne_optimale(self, scores: Dict) -> Optional[str]:
        """Choisit l'enseigne avec le meilleur score."""
        if not scores:
            return None

        # Filtrer les scores > 0
        valid_scores = {k: v for k, v in scores.items() if v > 0}

        if not valid_scores:
            return None

        # Choisir le meilleur
        meilleure = max(valid_scores, key=valid_scores.get)
        return meilleure

    def generer_prediction_cycle(self, dernier_jeu: int) -> Optional[Dict]:
        """Génère une prédiction dans le cycle actuel."""
        if not self.enseigne_actuelle or not self.intervalle_choisi:
            return None

        # Vérifier si on a déjà fait 3 prédictions
        if len(self.cycle_predictions) >= 3:
            # Réinitialiser le cycle
            self.enseigne_actuelle = None
            self.intervalle_choisi = None
            self.cycle_predictions = []
            return None

        # Calculer le prochain jeu cible
        intervalle_moyen = self.intervalle_choisi['moyen']

        if len(self.cycle_predictions) == 0:
            # Première prédiction: dernier + intervalle
            jeu_cible = int(dernier_jeu + intervalle_moyen)
        else:
            # Prédictions suivantes: ajouter l'intervalle à chaque fois
            dernier_cible = self.cycle_predictions[-1]['game_number']
            jeu_cible = int(dernier_cible + intervalle_moyen)

        # Créer la prédiction
        prediction = {
            'symbol': self._get_symbol_emoji(self.enseigne_actuelle),
            'symbol_name': self.enseigne_actuelle,
            'game_number': jeu_cible,
            'confidence': min(0.95, 0.5 + (self.intervalle_choisi.get('regularite', 0) * 0.5)),
            'strategy_used': 'intervalles',
            'cycle_position': len(self.cycle_predictions) + 1,
            'timestamp': datetime.now().isoformat()
        }

        self.cycle_predictions.append(prediction)
        return prediction

    def _get_symbol_emoji(self, name: str) -> str:
        """Convertit le nom en emoji."""
        mapping = {
            'PIQUE': '♠️', 'TREFLE': '♣️',
            'CARREAU': '♦️', 'COEUR': '♥️'
        }
        return mapping.get(name, name)


class StrategieIntervalles:
    """Stratégie principale basée sur l'analyse des intervalles."""

    def __init__(self, min_games: int = 50):
        self.analyseur = IntervalAnalyseur(min_games)
        self.min_games = min_games

    def generer_prediction(self, history: Dict) -> Optional[Dict]:
        """Génère une prédiction basée sur l'analyse des intervalles."""

        # 1. Extraire les symboles
        symboles = self.analyseur.extraire_symboles_joueur(history)

        if len(symboles) < self.min_games:
            print(f"[StrategieIntervalles] Pas assez de données: {len(symboles)}/{self.min_games}")
            return None

        # 2. Si on est déjà dans un cycle, continuer
        if self.analyseur.enseigne_actuelle and len(self.analyseur.cycle_predictions) < 3:
            dernier_jeu = max(history.keys()) if history else 0
            return self.analyseur.generer_prediction_cycle(dernier_jeu)

        # 3. Calculer les intervalles
        intervalles = self.analyseur.calculer_intervalles(symboles)

        # 4. Calculer les scores
        scores = self.analyseur.calculer_score_exploitabilite(intervalles)

        # 5. Choisir la meilleure enseigne
        meilleure = self.analyseur.choisir_enseigne_optimale(scores)

        if not meilleure:
            print("[StrategieIntervalles] Aucune enseigne exploitable trouvée")
            return None

        # 6. Initialiser le cycle
        self.analyseur.enseigne_actuelle = meilleure
        self.analyseur.intervalle_choisi = intervalles[meilleure]
        self.analyseur.cycle_predictions = []

        print(f"[StrategieIntervalles] Nouveau cycle sur {meilleure} "
              f"(intervalle moyen: {intervalles[meilleure]['moyen']:.1f}, "
              f"score: {scores[meilleure]:.2f})")

        # 7. Générer la première prédiction
        dernier_jeu = max(history.keys()) if history else 0
        prediction = self.analyseur.generer_prediction_cycle(dernier_jeu)

        # 8. Ajouter les détails de l'analyse
        if prediction:
            prediction['analysis'] = {
                'intervalle_moyen': intervalles[meilleure]['moyen'],
                'intervalle_min': intervalles[meilleure]['min'],
                'intervalle_max': intervalles[meilleure]['max'],
                'regularite': intervalles[meilleure].get('regularite', 0),
                'occurrences': intervalles[meilleure]['count']
            }
            prediction['message_html'] = self._format_message(prediction)

        return prediction

    def _format_message(self, prediction: Dict) -> str:
        """Formate le message de prédiction."""
        sym = prediction['symbol']
        game = prediction['game_number']
        conf = prediction['confidence']
        cycle = prediction['cycle_position']

        analysis = prediction.get('analysis', {})
        moyen = analysis.get('intervalle_moyen', 0)

        return (
            f"🎯 *Prédiction {cycle}/3*\n"
            f"Enseigne: {sym}\n"
            f"Jeu cible: #{game}\n"
            f"Confiance: {conf:.0%}\n"
            f"Intervalle moyen: {moyen:.1f}"
        )


if __name__ == "__main__":
    # Test rapide
    print("Test de StrategieIntervalles...")

    # Données de test
    history = {}
    # Simuler des données avec CARREAU régulier
    for i in range(1, 51):
        if i % 10 == 0:  # CARREAU tous les 10 jeux
            symbol = 2  # CARREAU
        else:
            symbol = (i % 3)  # Autres symboles aléatoires

        history[i] = {
            "player_cards": [{"S": symbol, "R": (i % 13) + 1}],
            "is_finished": True
        }

    strategie = StrategieIntervalles(min_games=20)
    pred = strategie.generer_prediction(history)

    if pred:
        print(f"✅ Prédiction générée: {pred['symbol']} pour jeu #{pred['game_number']}")
    else:
        print("❌ Aucune prédiction")
