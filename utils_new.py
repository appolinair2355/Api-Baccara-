import requests

def get_latest_results():
    try:
        print("[API] Récupération des résultats depuis l'API...")
        API_URL = "https://1xbet.com/service-api/LiveFeed/GetSportsShortZip?sports=236&champs=2050671&lng=en&gr=285&country=96&virtualSports=true&groupChamps=true"
        response = requests.get(API_URL, timeout=30)
        data = response.json()
        
        if "Value" in data and isinstance(data["Value"], list):
            # Chercher le baccara dans la liste des sports
            baccara_data = None
            for sport in data["Value"]:
                if sport.get("N") == "Baccarat" and "L" in sport:
                    baccara_data = sport
                    break
            
            if baccara_data and "L" in baccara_data:
                games = baccara_data["L"]
                results = []
                
                for game in games:
                    # Vérifier si le jeu a les données nécessaires
                    if "DI" in game and "MS" in game:
                        game_number = int(game["DI"])  # Numéro du jeu
                        
                        # Extraire les cartes des joueurs (MS = Market Scores)
                        market_scores = game.get("MS", [])
                        
                        # Pour le baccara, nous devons interpréter les scores
                        # MS contient généralement les scores des différents marchés
                        player_cards = []
                        banker_cards = []
                        
                        # Le jeu est terminé s'il a un résultat
                        is_game_finished = len(market_scores) > 0
                        
                        # Essayer d'extraire les cartes depuis les structures disponibles
                        # Cette partie peut nécessiter des ajustements selon la structure exacte
                        if "E" in game:  # Events/Results
                            for event in game["E"]:
                                if "O1" in event:  # Outcome 1 (Player)
                                    player_cards.append({"S": event.get("O1", 0)})
                                if "O2" in event:  # Outcome 2 (Banker)  
                                    banker_cards.append({"S": event.get("O2", 0)})
                        
                        # Si pas de cartes dans les events, utiliser une logique alternative
                        if not player_cards and not banker_cards:
                            # Utiliser les market scores pour déterminer les cartes
                            # C'est une approximation - la vraie structure peut varier
                            if len(market_scores) >= 2:
                                player_cards = [{"S": market_scores[0] % 4}]  # Convertir en enseigne
                                banker_cards = [{"S": market_scores[1] % 4 if len(market_scores) > 1 else 0}]
                        
                        results.append({
                            "game_number": game_number,
                            "player_cards": player_cards,
                            "banker_cards": banker_cards,
                            "is_finished": is_game_finished
                        })
                        
                        print(f"[API] Jeu #{game_number} - Cartes du joueur : {player_cards}, Cartes du banquier : {banker_cards}, Terminé : {is_game_finished}")
                
                return results
            else:
                print("[API] Aucune donnée de baccara trouvée dans la réponse")
                # Afficher la structure pour débogage
                print(f"[API] Structure reçue: {list(data.keys())}")
                if "Value" in data:
                    print(f"[API] Nombre de sports: {len(data['Value'])}")
                    for i, sport in enumerate(data["Value"][:5]):  # Premier 5 sports
                        print(f"[API] Sport {i}: {sport.get('N', 'Unknown')} (ID: {sport.get('I', 'Unknown')})")
                
        else:
            print("[API] Structure de réponse inattendue")
            
    except Exception as e:
        print(f"[API] Erreur lors de la récupération des résultats : {e}")
        import traceback
        traceback.print_exc()
    
    return []

def update_history(results, history):
    print("[Historique] Mise à jour de l'historique des résultats...")
    for result in results:
        if result["is_finished"]:
            game_number = result["game_number"]
            if game_number not in history:  # Éviter les doublons
                history[game_number] = {
                    "player_cards": result["player_cards"],
                    "banker_cards": result["banker_cards"],
                    "is_finished": result["is_finished"]
                }
                print(f"[Historique] Jeu #{game_number} ajouté à l'historique.")
    return history
