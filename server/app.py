from flask import Flask, render_template, request, redirect, abort, jsonify
import os
import random
import sqlite3
import requests

from server.equity import calculate_equity_multi
from treys import Evaluator, Card

app = Flask(__name__)

# ======================================================
# Constants / Modes
# ======================================================

INFO_FULL = "FULL"
INFO_DELAYED = "DELAYED_EQUITY"

PHASE_BACK = {
    "PREFLOP": None,
    "FLOP": "PREFLOP",
    "TURN": "FLOP",
    "RIVER": "TURN",
    "SHOWDOWN": "RIVER",
}

STREETS = ("PREFLOP", "FLOP", "TURN", "RIVER", "SHOWDOWN")

# ======================================================
# Pi Command State (single-table)
# ======================================================

PI_COMMAND = {"action": "idle"}

# ======================================================
# Host code (simple security)
# ======================================================

def generate_host_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(random.choice(alphabet) for _ in range(4))

# ======================================================
# Helpers
# ======================================================

def get_positions(players, button_index):
    n = len(players)
    labels = {
        2:  ["BTN", "BB"],
        3:  ["BTN", "SB", "BB"],
        4:  ["BTN", "SB", "BB", "UTG"],
        5:  ["BTN", "SB", "BB", "UTG", "CO"],
        6:  ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
        7:  ["BTN", "SB", "BB", "UTG", "UTG+1", "HJ", "CO"],
        8:  ["BTN", "SB", "BB", "UTG", "UTG+1", "UTG+2", "HJ", "CO"],
        9:  ["BTN", "SB", "BB", "UTG", "UTG+1", "UTG+2", "UTG+3", "HJ", "CO"],
        10: ["BTN", "SB", "BB", "UTG", "UTG+1", "UTG+2", "UTG+3", "UTG+4", "HJ", "CO"],
    }.get(n, [])

    pos = {}
    for i, label in enumerate(labels):
        pos[players[(button_index + i) % n]] = label
    return pos

def iterations_for(players_count, phase):
    base = 2200
    n = max(2, players_count)
    iters = int(base / (n ** 0.9))

    mult = {
        "PREFLOP": 1.0,
        "FLOP": 0.75,
        "TURN": 0.55,
        "RIVER": 0.40,
    }.get(phase, 0.6)

    return max(200, min(2000, int(iters * mult)))

# ======================================================
# Global game state (single table)
# ======================================================

game_state = None

def bump_version():
    if game_state:
        game_state["version"] += 1

# ======================================================
# Game init
# ======================================================

def start_new_game(players, button_index, info_mode, manual_button=False, host_code=None):
    n = len(players)
    return {
        "version": 0,
        "host_code": host_code or generate_host_code(),

        "info_mode": info_mode,
        "players": players,
        "button_index": button_index,
        "phase": "WAITING",
        "manual_button": manual_button,

        # Deck is provided by Pi
        "deck": [],
        "deck_pointer": 0,

        "hands": {},
        "board": [],

        "equity_by_phase": {},
        "last_completed_phase": None,
        "display_equities": [0.0] * n,
        "display_hand_ranks": {},
        "tie_probability": 0.0,
    }

# ======================================================
# Deck consumption (authoritative, deterministic)
# ======================================================

def next_card():
    card = game_state["deck"][game_state["deck_pointer"]]
    game_state["deck_pointer"] += 1
    return card

def deal_hole_cards():
    n = len(game_state["players"])
    hands = {p: [] for p in game_state["players"]}
    start = (game_state["button_index"] + 1) % n

    for _ in range(2):
        for i in range(n):
            p = game_state["players"][(start + i) % n]
            hands[p].append(next_card())

    game_state["hands"] = hands
    game_state["phase"] = "PREFLOP"

def deal_flop():
    game_state["board"] = [next_card() for _ in range(3)]
    game_state["phase"] = "FLOP"

def deal_turn():
    game_state["board"].append(next_card())
    game_state["phase"] = "TURN"

def deal_river():
    game_state["board"].append(next_card())
    game_state["phase"] = "RIVER"

# ======================================================
# Showdown (deterministic)
# ======================================================

def resolve_showdown(game):
    evaluator = Evaluator()
    board = [Card.new(c) for c in game["board"]]

    scores = {}
    for p in game["players"]:
        hole = [Card.new(c) for c in game["hands"][p]]
        scores[p] = evaluator.evaluate(hole, board)

    best = min(scores.values())
    winners = [p for p, s in scores.items() if s == best]
    share = 100.0 / len(winners)

    game["display_equities"] = [
        share if p in winners else 0.0 for p in game["players"]
    ]
    game["tie_probability"] = 100.0 if len(winners) > 1 else 0.0

# ======================================================
# Pi API
# ======================================================

@app.route("/pi/command", methods=["GET", "POST"])
def pi_command():
    global PI_COMMAND
    if request.method == "POST":
        PI_COMMAND = request.json
        return {"ok": True}
    return PI_COMMAND

@app.route("/pi/deck", methods=["POST"])
def receive_deck():
    global game_state

    data = request.json
    deck = data.get("deck") or data.get("ufids")

    if not deck or len(deck) < 7:
        abort(400, "Invalid deck")

    game_state["deck"] = deck
    game_state["deck_pointer"] = 0

    deal_hole_cards()
    bump_version()

    return {"ok": True}

# ======================================================
# Host routes
# ======================================================

@app.route("/host/config", methods=["GET", "POST"])
def host_config():
    global game_state

    if game_state is not None:
        if request.method == "GET":
            return render_template("locked.html", target="config", error=False)

        code = request.form.get("host_code", "").upper()
        if code != game_state.get("host_code"):
            return render_template("locked.html", target="config", error=True)

        return render_template("config.html", game=game_state)

    if request.method == "POST":
        players = [p.strip() for p in request.form.getlist("players[]")]
        if not (2 <= len(players) <= 10):
            return "2–10 players required", 400

        button_index = int(request.form["button_index"]) % len(players)
        info_mode = request.form.get("info_mode", INFO_DELAYED)

        game_state = start_new_game(players, button_index, info_mode)
        bump_version()

        # Tell Pi to prepare scanning
        requests.post(
            f"{request.host_url}pi/command",
            json={"action": "prepare_scan"},
            timeout=2
        )

        return redirect(f"/host?host_code={game_state['host_code']}")

    return render_template("config.html")

@app.route("/host", methods=["GET", "POST"])
def host_view():
    global game_state

    if game_state is None:
        return redirect("/host/config")

    code = request.form.get("host_code") or request.args.get("host_code", "")
    if code.upper() != game_state.get("host_code"):
        return render_template("locked.html", target="host", error=True)

    n = len(game_state["players"])

    if request.method == "POST":

        if request.form.get("action") == "advance":
            phase = game_state["phase"]

            if phase == "PREFLOP": deal_flop()
            elif phase == "FLOP": deal_turn()
            elif phase == "TURN": deal_river()
            elif phase == "RIVER":
                game_state["phase"] = "SHOWDOWN"
                resolve_showdown(game_state)

            bump_version()
            return redirect(f"/host?host_code={game_state['host_code']}")

        if request.form.get("action") == "new_round":
            game_state.update(
                start_new_game(
                    game_state["players"],
                    game_state["button_index"],
                    game_state["info_mode"],
                    game_state["manual_button"],
                    game_state["host_code"],
                )
            )

            requests.post(
                f"{request.host_url}pi/command",
                json={"action": "prepare_scan"},
                timeout=2
            )

            bump_version()
            return redirect(f"/host?host_code={game_state['host_code']}")

    positions = get_positions(game_state["players"], game_state["button_index"])
    return render_template("host.html", game=game_state, positions=positions)

# ======================================================
# Audience routes
# ======================================================

@app.route("/")
def audience_view():
    return render_template("audience.html", game=game_state)

@app.route("/game_state")
def game_state_json():
    if game_state is None:
        return {}, 200

    public = dict(game_state)
    if game_state["info_mode"] == INFO_DELAYED:
        public["hands"] = {}
        public["display_hand_ranks"] = {}

    return public

# ======================================================
# Run
# ======================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
