#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module optimisé de récupération des données API 1xBet
Utilise les meilleures pratiques: cache, retry, async, parsing robuste
"""

import requests
import json
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
import threading

logger = logging.getLogger(__name__)

@dataclass
class GameResult:
    """Structure typée pour un résultat de jeu."""
    game_number: int
    player_cards: List[Dict]
    banker_cards: List[Dict]
    player_score: int
    banker_score: int
    winner: str  # 'player', 'banker', 'tie'
    timestamp: datetime
    is_finished: bool
    raw_data: Dict = None

class BaccaraAPIClient:
    """Client API optimisé pour le Baccara 1xBet."""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.base_url = self.config.get('api', {}).get('url', 
            "https://1xbet.com/service-api/LiveFeed/GetSportsShortZip")
        self.params = self.config.get('api', {}).get('params', {
            "sports": 236,
            "champs": 2050671,
            "lng": "en",
            "gr": 285,
            "country": 96,
            "virtualSports": "true",
            "groupChamps": "true"
        })
        self.timeout = self.config.get('api', {}).get('timeout', 30)

        # Session HTTP persistante (keep-alive)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        })

        # Cache et stats
        self._cache = {}
        self._cache_ttl = 5  # secondes
        self._last_fetch = None
        self._consecutive_errors = 0
        self._max_retries = 3
        self._retry_delay = 1

        # Thread safety
        self._lock = threading.Lock()

        logger.info("BaccaraAPIClient initialisé")

    def fetch_data(self, force_refresh: bool = False) -> Optional[Dict]:
        """
        Récupère les données avec cache et retry intelligent.

        Args:
            force_refresh: Force la mise à jour même si le cache est valide

        Returns:
            Données JSON ou None en cas d'erreur
        """
        with self._lock:
            # Vérifier le cache
            if not force_refresh and self._is_cache_valid():
                logger.debug("Utilisation du cache")
                return self._cache.get('data')

            # Tentatives avec retry
            for attempt in range(self._max_retries):
                try:
                    logger.debug(f"Tentative {attempt + 1}/{self._max_retries}")

                    response = self.session.get(
                        self.base_url,
                        params=self.params,
                        timeout=self.timeout,
                        headers={'Cache-Control': 'no-cache'}
                    )

                    # Vérifier le statut
                    response.raise_for_status()

                    # Parser le JSON
                    data = response.json()

                    # Valider la structure
                    if not self._validate_response(data):
                        raise ValueError("Structure de réponse invalide")

                    # Mettre à jour le cache
                    self._cache = {
                        'data': data,
                        'timestamp': datetime.now(),
                        'etag': response.headers.get('ETag')
                    }

                    self._last_fetch = datetime.now()
                    self._consecutive_errors = 0

                    logger.info(f"Données récupérées avec succès ({len(str(data))} caractères)")
                    return data

                except requests.exceptions.Timeout:
                    logger.warning(f"Timeout (tentative {attempt + 1})")
                    time.sleep(self._retry_delay * (attempt + 1))

                except requests.exceptions.ConnectionError as e:
                    logger.error(f"Erreur de connexion: {e}")
                    self._consecutive_errors += 1
                    time.sleep(self._retry_delay * 2)

                except requests.exceptions.HTTPError as e:
                    logger.error(f"Erreur HTTP {e.response.status_code}: {e}")
                    if e.response.status_code == 429:  # Rate limit
                        time.sleep(5)
                    else:
                        break

                except Exception as e:
                    logger.error(f"Erreur inattendue: {e}")
                    break

            self._consecutive_errors += 1
            logger.error(f"Échec après {self._max_retries} tentatives")
            return None

    def _is_cache_valid(self) -> bool:
        """Vérifie si le cache est encore valide."""
        if not self._cache or 'timestamp' not in self._cache:
            return False
        age = (datetime.now() - self._cache['timestamp']).total_seconds()
        return age < self._cache_ttl

    def _validate_response(self, data: Dict) -> bool:
        """Valide la structure de la réponse API."""
        if not isinstance(data, dict):
            return False
        if 'Value' not in data:
            return False
        if not isinstance(data['Value'], list):
            return False
        return True

    def extract_baccara_games(self, data: Dict) -> List[Dict]:
        """
        Extrait les jeux de Baccara des données brutes.

        Returns:
            Liste des jeux Baccara avec leurs données
        """
        games = []

        try:
            sports_list = data.get('Value', [])

            for sport in sports_list:
                if sport.get('N') == 'Baccarat' or 'baccarat' in sport.get('N', '').lower():
                    leagues = sport.get('L', [])

                    for league in leagues:
                        league_games = league.get('G', []) if isinstance(league, dict) else []

                        for game in league_games:
                            parsed = self._parse_game(game)
                            if parsed:
                                games.append(parsed)

        except Exception as e:
            logger.error(f"Erreur d'extraction: {e}")

        logger.info(f"{len(games)} jeux Baccara extraits")
        return games

    def _parse_game(self, game_data: Dict) -> Optional[GameResult]:
        """
        Parse un jeu individuel et extrait les informations pertinentes.
        """
        try:
            # Numéro du jeu
            game_number = self._extract_game_number(game_data)
            if not game_number:
                return None

            # Scores et cartes
            player_score, player_cards = self._extract_player_data(game_data)
            banker_score, banker_cards = self._extract_banker_data(game_data)

            # Déterminer le gagnant
            winner = self._determine_winner(game_data, player_score, banker_score)

            # Vérifier si le jeu est terminé
            is_finished = game_data.get('S', 0) == 3  # 3 = terminé

            return GameResult(
                game_number=game_number,
                player_cards=player_cards,
                banker_cards=banker_cards,
                player_score=player_score,
                banker_score=banker_score,
                winner=winner,
                timestamp=datetime.now(),
                is_finished=is_finished,
                raw_data=game_data
            )

        except Exception as e:
            logger.debug(f"Erreur de parsing du jeu: {e}")
            return None

    def _extract_game_number(self, game_data: Dict) -> Optional[int]:
        """Extrait le numéro du jeu."""
        # Essayer plusieurs champs possibles
        for field in ['DI', 'I', 'id', 'gameId']:
            if field in game_data:
                try:
                    return int(game_data[field])
                except (ValueError, TypeError):
                    continue
        return None

    def _extract_player_data(self, game_data: Dict) -> Tuple[int, List[Dict]]:
        """Extrait les données du joueur."""
        cards = []
        score = 0

        try:
            # Chercher dans les scores de marché (MS)
            market_scores = game_data.get('MS', [])
            if len(market_scores) >= 1:
                score = int(market_scores[0])

            # Chercher les cartes dans les événements (E)
            events = game_data.get('E', [])
            for event in events:
                if 'O1' in event:  # Outcome 1 = Joueur
                    card_value = event.get('O1')
                    if card_value:
                        cards.append({
                            'value': card_value,
                            'type': 'player'
                        })

            # Alternative: chercher dans SC (Scores Complets)
            if not cards and 'SC' in game_data:
                sc_data = game_data['SC']
                if isinstance(sc_data, dict):
                    player_sc = sc_data.get('P', {})  # Player
                    if player_sc:
                        score = player_sc.get('T', 0)  # Total
                        cards = player_sc.get('C', [])  # Cards

        except Exception as e:
            logger.debug(f"Erreur extraction joueur: {e}")

        return score, cards

    def _extract_banker_data(self, game_data: Dict) -> Tuple[int, List[Dict]]:
        """Extrait les données du banquier."""
        cards = []
        score = 0

        try:
            market_scores = game_data.get('MS', [])
            if len(market_scores) >= 2:
                score = int(market_scores[1])

            events = game_data.get('E', [])
            for event in events:
                if 'O2' in event:  # Outcome 2 = Banquier
                    card_value = event.get('O2')
                    if card_value:
                        cards.append({
                            'value': card_value,
                            'type': 'banker'
                        })

            # Alternative: SC
            if not cards and 'SC' in game_data:
                sc_data = game_data['SC']
                if isinstance(sc_data, dict):
                    banker_sc = sc_data.get('B', {})  # Banker
                    if banker_sc:
                        score = banker_sc.get('T', 0)
                        cards = banker_sc.get('C', [])

        except Exception as e:
            logger.debug(f"Erreur extraction banquier: {e}")

        return score, cards

    def _determine_winner(self, game_data: Dict, player_score: int, banker_score: int) -> str:
        """Détermine le gagnant du jeu."""
        # Essayer d'abord le champ winner explicite
        winner = game_data.get('W', '').lower()
        if winner in ['player', 'banker', 'tie']:
            return winner

        # Sinon comparer les scores
        if player_score > banker_score:
            return 'player'
        elif banker_score > player_score:
            return 'banker'
        else:
            return 'tie'

    def get_latest_results(self, force_refresh: bool = False) -> List[GameResult]:
        """
        Méthode principale: récupère et parse les derniers résultats.

        Returns:
            Liste des GameResult
        """
        data = self.fetch_data(force_refresh)
        if not data:
            return []

        games = self.extract_baccara_games(data)

        # Filtrer uniquement les jeux terminés avec des données valides
        valid_games = [
            g for g in games 
            if g.is_finished and g.game_number and (g.player_cards or g.banker_cards)
        ]

        logger.info(f"{len(valid_games)} jeux valides trouvés")
        return valid_games

    def get_stats(self) -> Dict:
        """Retourne les statistiques du client."""
        return {
            'last_fetch': self._last_fetch.isoformat() if self._last_fetch else None,
            'consecutive_errors': self._consecutive_errors,
            'cache_valid': self._is_cache_valid(),
            'cache_age': (datetime.now() - self._cache['timestamp']).total_seconds() 
                        if self._cache else None
        }

    def close(self):
        """Ferme proprement la session."""
        self.session.close()
        logger.info("Session API fermée")


# Fonctions de compatibilité avec l'ancien code
def get_latest_results_legacy(config: Dict = None) -> List[Dict]:
    """Fonction legacy pour compatibilité."""
    client = BaccaraAPIClient(config)
    games = client.get_latest_results()
    client.close()

    # Convertir en format legacy (dict simple)
    results = []
    for game in games:
        results.append({
            'game_number': game.game_number,
            'player_cards': game.player_cards,
            'banker_cards': game.banker_cards,
            'is_finished': game.is_finished,
            'winner': game.winner
        })

    return results


def update_history(results: List[Dict], history: Dict) -> Dict:
    """Met à jour l'historique avec les nouveaux résultats."""
    for result in results:
        if result.get('is_finished'):
            game_num = result['game_number']
            if game_num and game_num not in history:
                history[game_num] = {
                    'player_cards': result.get('player_cards', []),
                    'banker_cards': result.get('banker_cards', []),
                    'is_finished': True,
                    'winner': result.get('winner'),
                    'timestamp': datetime.now().isoformat()
                }
                logger.debug(f"Jeu #{game_num} ajouté à l'historique")

    return history


# Singleton pour réutilisation
_client_instance = None

def get_api_client(config: Dict = None) -> BaccaraAPIClient:
    """Retourne une instance singleton du client API."""
    global _client_instance
    if _client_instance is None:
        _client_instance = BaccaraAPIClient(config)
    return _client_instance


if __name__ == "__main__":
    # Test du client
    logging.basicConfig(level=logging.INFO)

    print("Test du client API Baccara...")
    client = BaccaraAPIClient()

    results = client.get_latest_results()
    print(f"\n{len(results)} jeux trouvés:")

    for game in results[:5]:  # Afficher les 5 premiers
        print(f"  Jeu #{game.game_number}: "
              f"Joueur {game.player_score} vs Banquier {game.banker_score} "
              f"({game.winner})")

    stats = client.get_stats()
    print(f"\nStats client: {stats}")

    client.close()
