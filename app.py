from flask import Flask, render_template, request, redirect
import os
import random
import sqlite3

from equity import calculate_equity_multi
from treys import Evaluator, Card

app = Flask(__name__)

# =============================
# Info modes
# =============================

INFO_FULL = "FULL"
INFO_EQUITY_ONLY = "EQUITY_ONLY"
INFO_DELAYED = "DELAYED_EQUITY"

PHASE_BACK = {
    "PREFLOP": None,
    "FLOP": "PREFLOP",
    "TURN": "FLOP",
    "RIVER": "TURN",
}

# =============================
# Database
# =============================

DB_PATH = "poker.db"

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS rfid_cards (
            uid TEXT PRIMARY KEY,
            card TEXT NOT NULL
        )
    """)
    db.commit()

init_db()

# =============================
# Helpers
# =============================

RANKS = "23456789TJQKA"
SUITS = "cdhs"

def fresh_deck():
    return [f"{r}{s}" for r in RANKS for s in SUITS]

def get_positions(players, button_index):
    labels = ["BTN", "SB", "BB", "UTG", "HJ", "CO"]
    return {
        players[(button_index + i) % 6]: labels[i]
        for i in range(6)
    }

# =============================
# Global state (single table MVP)
# =============================

game_state = None

# =============================
# Dealing (simulated)
# =============================

def scan_full_deck_sim():
    game_state["deck"] = fresh_deck()
    random.shuffle(game_state["deck"])
    game_state["deck_pointer"] = 0
    game_state["burned"] = []

def scan_next_card():
    card = game_state["deck"][game_state["deck_pointer"]]
    game_state["deck_pointer"] += 1
    return card

def burn_card():
    game_state["burned"].append(scan_next_card())

def deal_hole_cards():
    hands = {p: [] for p in game_state["players"]}
    start = (game_state["button_index"] + 1) % 6

    for _ in range(2):
        for i in range(6):
            p = game_state["players"][(start + i) % 6]
            hands[p].append(scan_next_card())

    game_state["hands"] = hands
    game_state["phase"] = "PREFLOP"

def deal_flop():
    burn_card()
    game_state["board"] = [scan_next_card() for _ in range(3)]
    game_state["phase"] = "FLOP"

def deal_turn():
    burn_card()
    game_state["board"].append(scan_next_card())
    game_state["phase"] = "TURN"

def deal_river():
    burn_card()
    game_state["board"].append(scan_next_card())
    game_state["phase"] = "RIVER"

# =============================
# Showdown (deterministic)
# =============================

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
        share if p in winners else 0.0
        for p in game["players"]
    ]

    game["tie_probability"] = 100.0 if len(winners) > 1 else 0.0

# =============================
# Game init
# =============================

def start_new_game(players, button_index, info_mode, manual_button=False):
    return {
        "info_mode": info_mode,
        "players": players,
        "button_index": button_index,
        "phase": "WAITING",
        "manual_button": manual_button,

        "deck": [],
        "deck_pointer": 0,
        "burned": [],

        "hands": {},
        "board": [],

        # equity system
        "equity_by_phase": {},
        "display_equities": [0] * 6,
        "display_hand_ranks": {},
        "tie_probability": 0,

        # dealer privacy (HIDDEN by default)
        "hide_equity": True,
    }

# =============================
# Equity visibility resolver
# =============================

def resolve_display_info(game):
    mode = game["info_mode"]
    phase = game["phase"]

    if mode in (INFO_FULL, INFO_EQUITY_ONLY):
        return game["equity_by_phase"].get(phase)

    if mode == INFO_DELAYED:
        prev = PHASE_BACK.get(phase)
        return game["equity_by_phase"].get(prev)

    return None

# =============================
# Routes
# =============================

@app.route("/host/config", methods=["GET", "POST"])
def host_config():
    global game_state

    if request.method == "POST":
        players = request.form.getlist("players[]")
        button_index = int(request.form["button_index"])
        info_mode = request.form.get("info_mode", INFO_DELAYED)

        if len(players) != 6 or any(p.strip() == "" for p in players):
            return "Must enter exactly 6 players", 400

        game_state = start_new_game(players, button_index, info_mode)
        return redirect("/host")

    return render_template("config.html")

@app.route("/host", methods=["GET", "POST"])
def host_view():
    global game_state

    if game_state is None:
        return redirect("/host/config")

    # ---------- POST controls ----------

    if request.method == "POST":
        action = request.form.get("action")

        # ----- Dealer privacy -----
        if "toggle_privacy" in request.form:
            game_state["hide_equity"] = not game_state["hide_equity"]
            return redirect("/host")

       # ----- MISDEAL / FORCE BUTTON -----
        if "force_button" in request.form:
            new_btn = int(request.form["force_button"])

            game_state = start_new_game(
                game_state["players"],
                new_btn,
                game_state["info_mode"],
                manual_button=True,
            )

            scan_full_deck_sim()
            deal_hole_cards()   # 👈 THIS is the key line

            return redirect("/host")



        # ----- PRIMARY FLOW -----
        if action == "advance":

            if game_state["phase"] in ("WAITING", "SHOWDOWN"):

                # decide whether to rotate button
                if game_state.get("manual_button"):
                    next_btn = game_state["button_index"]
                else:
                    next_btn = (game_state["button_index"] - 1) % 6

                game_state = start_new_game(
                    game_state["players"],
                    next_btn,
                    game_state["info_mode"],
                    manual_button=False,  # reset after use
                )

                scan_full_deck_sim()
                deal_hole_cards()   # -> PREFLOP


            elif game_state["phase"] == "PREFLOP":
                deal_flop()

            elif game_state["phase"] == "FLOP":
                deal_turn()

            elif game_state["phase"] == "TURN":
                deal_river()

            elif game_state["phase"] == "RIVER":
                game_state["phase"] = "SHOWDOWN"

            return redirect("/host")

        return redirect("/host")



    # ---------- GET: equity / showdown resolution ----------

    phase = game_state["phase"]

    # --- SHOWDOWN: deterministic result ---
    if phase == "SHOWDOWN":
        resolve_showdown(game_state)

    # --- NORMAL STREETS: Monte Carlo ---
    elif phase in ("PREFLOP", "FLOP", "TURN", "RIVER"):
        equities, tie_prob, hand_ranks = calculate_equity_multi(
            [game_state["hands"][p] for p in game_state["players"]],
            player_names=game_state["players"],
            iterations=500,
            board_str=game_state["board"],
        )

        # cache equity for this phase
        game_state["equity_by_phase"][phase] = {
            "equities": equities,
            "hand_ranks": hand_ranks,
            "tie_probability": tie_prob,
        }

        # resolve what is allowed to be shown
        info = resolve_display_info(game_state)
        if info:
            game_state["display_equities"] = info["equities"]
            game_state["display_hand_ranks"] = info["hand_ranks"]
            game_state["tie_probability"] = info["tie_probability"]
        else:
            game_state["display_equities"] = [0] * 6
            game_state["display_hand_ranks"] = {}
            game_state["tie_probability"] = 0

    # --- WAITING or any other state ---
    else:
        game_state["display_equities"] = [0] * 6
        game_state["display_hand_ranks"] = {}
        game_state["tie_probability"] = 0

    # --- positions always safe ---
    positions = get_positions(
        game_state["players"],
        game_state["button_index"],
    )

    return render_template(
        "host.html",
        game=game_state,
        positions=positions,
    )


@app.route("/")
def audience_view():
    if game_state is None:
        return "Game not configured", 400
    return render_template("audience.html", game=game_state)

@app.route("/game_state")
def game_state_json():
    if game_state is None:
        return {}, 400

    public = dict(game_state)

    if game_state["info_mode"] != INFO_FULL:
        public["hands"] = {}
        public["display_hand_ranks"] = {}

    return public

# =============================
# Run
# =============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
