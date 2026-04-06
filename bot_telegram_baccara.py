#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram Baccara
- Envoie un message ⏰ dès qu'une partie commence
- ▶️ devant celui qui EST SUR LE POINT de tirer (a 2 cartes)
- Quand le joueur a 3 cartes : ▶️ banquier SEULEMENT s'il doit tirer selon les règles
- Sinon → message final immédiat
- Édite le message quand la partie se termine
- Efface le stock toutes les 120 secondes
"""

import os
import json
import logging
import asyncio
from datetime import datetime

from telegram.ext import Application

from utils_new import get_latest_results, update_history

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CONFIG_PATH = "config.json"

RANK_DISPLAY = {
    1: "A", 14: "A",
    2: "2", 3: "3", 4: "4", 5: "5",
    6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
    11: "J", 12: "Q", 13: "K"
}


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    env_token = os.environ.get("BOT_TOKEN")
    env_admin = os.environ.get("ADMIN_ID")
    if env_token:
        config["telegram"]["bot_token"] = env_token
    if env_admin:
        config["telegram"]["admin_id"] = int(env_admin)
    return config


def card_value(rank) -> int:
    """Valeur baccara : A=1, 2-9=face, 10/J/Q/K=0."""
    try:
        r = int(rank)
    except (ValueError, TypeError):
        return 0
    if r == 1 or r == 14:
        return 1
    elif r >= 10:
        return 0
    return r


def baccarat_score(cards: list) -> int:
    return sum(card_value(c["R"]) for c in cards) % 10


def fmt_card(card: dict) -> str:
    try:
        r = int(card["R"])
    except (ValueError, TypeError):
        r = 0
    rank = RANK_DISPLAY.get(r, str(r))
    return f"{rank}{card['S']}"


def banker_needs_draw(b_score: int, p_third_value: int) -> bool:
    """
    Règles baccara : le banquier tire-t-il une 3ème carte ?
    (Appliqué quand le joueur a tiré une 3ème carte)
    p_third_value = valeur baccara de la 3ème carte du joueur (0-9)
    """
    if b_score <= 2:
        return True
    if b_score == 3:
        return p_third_value != 8
    if b_score == 4:
        return p_third_value in (2, 3, 4, 5, 6, 7)
    if b_score == 5:
        return p_third_value in (4, 5, 6, 7)
    if b_score == 6:
        return p_third_value in (6, 7)
    return False   # b_score 7, 8, 9 → stand


def next_to_draw(p_cards: list, b_cards: list) -> str:
    """
    Retourne 'player', 'banker' ou '' selon les règles baccara complètes.
    """
    p_score = baccarat_score(p_cards)
    b_score = baccarat_score(b_cards)

    # --- Les deux ont 2 cartes ---
    if len(p_cards) == 2 and len(b_cards) == 2:
        # Naturelle : personne ne tire
        if p_score >= 8 or b_score >= 8:
            return ""
        # Joueur tire si score 0-5
        if p_score <= 5:
            return "player"
        # Joueur stand (6-7) : banquier tire si score 0-5
        if b_score <= 5:
            return "banker"
        return ""

    # --- Joueur a tiré (3 cartes), banquier encore 2 cartes ---
    if len(p_cards) == 3 and len(b_cards) == 2:
        if b_score >= 7:
            return ""   # Banquier stand → pas de tirage
        p_third_val = card_value(p_cards[2]["R"])
        if banker_needs_draw(b_score, p_third_val):
            return "banker"
        return ""       # Banquier ne tire pas → partie effectivement terminée

    return ""


def is_effectively_finished(p_cards: list, b_cards: list) -> bool:
    """
    True si on peut déterminer que la partie est terminée avant que l'API le confirme.
    """
    if not p_cards or not b_cards:
        return False

    p_score = baccarat_score(p_cards)
    b_score = baccarat_score(b_cards)

    # Naturelle (2 cartes chacun, score 8 ou 9)
    if len(p_cards) == 2 and len(b_cards) == 2:
        return p_score >= 8 or b_score >= 8

    # Les deux ont 3 cartes
    if len(p_cards) == 3 and len(b_cards) == 3:
        return True

    # Joueur a 3 cartes, banquier a 2 : banquier ne tire pas
    if len(p_cards) == 3 and len(b_cards) == 2:
        if b_score >= 7:
            return True
        p_third_val = card_value(p_cards[2]["R"])
        return not banker_needs_draw(b_score, p_third_val)

    return False


def compute_winner(p_cards: list, b_cards: list) -> str:
    p = baccarat_score(p_cards)
    b = baccarat_score(b_cards)
    if p > b:
        return "Player"
    if b > p:
        return "Banker"
    return "Tie"


def format_inprogress(game_number: int, game: dict) -> str:
    p_cards = game["player_cards"]
    b_cards = game["banker_cards"]

    p_score = baccarat_score(p_cards)
    b_score = baccarat_score(b_cards)
    p_str = "".join(fmt_card(c) for c in p_cards)
    b_str = "".join(fmt_card(c) for c in b_cards)

    who = next_to_draw(p_cards, b_cards)
    p_prefix = "▶️" if who == "player" else ""
    b_prefix = "▶️" if who == "banker" else ""

    return f"⏰ #N{game_number} {p_prefix}{p_score} ({p_str}) - {b_prefix}{b_score} ({b_str})"


def format_finished(game_number: int, game: dict) -> str:
    p_cards = game["player_cards"]
    b_cards = game["banker_cards"]
    winner = game.get("winner") or compute_winner(p_cards, b_cards)

    p_score = baccarat_score(p_cards)
    b_score = baccarat_score(b_cards)
    total = p_score + b_score

    p_str = "".join(fmt_card(c) for c in p_cards)
    b_str = "".join(fmt_card(c) for c in b_cards)

    r_tag = " #R" if len(p_cards) <= 2 and len(b_cards) <= 2 else ""

    if winner == "Player":
        line1 = f"#N{game_number} ✅{p_score} ({p_str}) - {b_score} ({b_str})"
        line2 = f"#П1 #T{total}{r_tag}"
    elif winner == "Banker":
        line1 = f"#N{game_number} {p_score} ({p_str}) - ✅{b_score} ({b_str})"
        line2 = f"#П2 #T{total}{r_tag}"
    else:
        line1 = f"#N{game_number} {p_score} ({p_str}) 🔰 {b_score} ({b_str})"
        line2 = f"#X #T{total}{r_tag}"

    return f"{line1}\n{line2}"


async def send_to_channels(bot, channels: list, text: str) -> dict:
    message_ids = {}
    for channel_id in channels:
        try:
            msg = await bot.send_message(chat_id=channel_id, text=text)
            message_ids[channel_id] = msg.message_id
            logger.info(f"Message envoyé au canal {channel_id}")
        except Exception as e:
            logger.error(f"Erreur envoi canal {channel_id}: {e}")
    return message_ids


async def edit_in_channels(bot, message_ids: dict, text: str):
    for channel_id, msg_id in message_ids.items():
        try:
            await bot.edit_message_text(chat_id=channel_id, message_id=msg_id, text=text)
            logger.info(f"Message #{msg_id} édité dans le canal {channel_id}")
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.error(f"Erreur édition canal {channel_id}: {e}")


async def run_bot():
    config = load_config()
    token = config["telegram"]["bot_token"]
    channels = config["telegram"]["redirect_channels"]
    check_interval = config["app"].get("check_interval_seconds", 2)

    app = Application.builder().token(token).build()
    bot = app.bot

    history: dict = {}
    pending_msgs: dict = {}   # {game_number: {channel_id: message_id}}
    done_games: set = set()
    last_clear = datetime.now()

    logger.info(f"Bot démarré — {len(channels)} canal(aux), vérif toutes les {check_interval}s, stock effacé toutes les 120s")

    async with app:
        await app.start()

        while True:
            try:
                # Efface le stock toutes les 120 secondes
                if (datetime.now() - last_clear).total_seconds() >= 120:
                    count = len(history)
                    history.clear()
                    last_clear = datetime.now()
                    logger.info(f"Stock effacé ({count} entrées supprimées)")

                results = get_latest_results()
                history = update_history(results, history)

                for result in results:
                    gn = result["game_number"]
                    if gn in done_games:
                        continue

                    game_data = history.get(gn) or result
                    p = game_data.get("player_cards", [])
                    b = game_data.get("banker_cards", [])

                    # Partie terminée : par l'API ou par déduction des règles
                    is_done = result["is_finished"] or (
                        len(p) >= 2 and len(b) >= 2 and is_effectively_finished(p, b)
                    )

                    if is_done:
                        msg_text = format_finished(gn, game_data)
                        logger.info(f"Partie terminée #{gn}:\n{msg_text}")

                        if gn in pending_msgs:
                            await edit_in_channels(bot, pending_msgs[gn], msg_text)
                            del pending_msgs[gn]
                        else:
                            await send_to_channels(bot, channels, msg_text)

                        done_games.add(gn)

                    elif gn not in pending_msgs:
                        # Nouvelle partie : envoie ⏰ si les cartes initiales sont là
                        if len(p) >= 2 and len(b) >= 2:
                            msg_text = format_inprogress(gn, game_data)
                            logger.info(f"Partie en cours #{gn}: {msg_text}")
                            ids = await send_to_channels(bot, channels, msg_text)
                            if ids:
                                pending_msgs[gn] = ids

                    else:
                        # Mise à jour du message ⏰ existant
                        if len(p) >= 2 and len(b) >= 2:
                            msg_text = format_inprogress(gn, game_data)
                            await edit_in_channels(bot, pending_msgs[gn], msg_text)

                await asyncio.sleep(check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur dans la boucle principale: {e}")
                await asyncio.sleep(check_interval)

        await app.stop()


if __name__ == "__main__":
    asyncio.run(run_bot())
