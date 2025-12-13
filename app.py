from flask import Flask, render_template, request, redirect
import os
import random
import sqlite3

from equity import calculate_equity_multi
from treys import Evaluator, Card

app = Flask(__name__)

# =============================
# Info modes (ONLY 2)
# =============================

INFO_FULL = "FULL"               # live equities + hole cards (home games)
INFO_DELAYED = "DELAYED_EQUITY"  # 1-street delayed equities + no hole cards (public)

PHASE_BACK = {
    "PREFLOP": None,
    "FLOP": "PREFLOP",
    "TURN": "FLOP",
    "RIVER": "TURN",
    "SHOWDOWN": "RIVER",
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
    return {players[(button_index + i) % 6]: labels[i] for i in range(6)}

# =============================
# Global state (single table MVP)
# =============================

game_state = None

def bump_version():
    """
    Audience polls /game_state and only updates UI when version changes.
    Bump ONLY when the public display should change.
    """
    global game_state
    if game_state is not None:
        game_state["version"] = int(game_state.get("version", 0)) + 1

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
        "version": 0,

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
        "equity_by_phase": {},          # cache per phase
        "last_completed_phase": None,   # ✅ REQUIRED for delayed mode
        "display_equities": [0] * 6,
        "display_hand_ranks": {},
        "tie_probability": 0,
    }

# =============================
# Equity visibility resolver
# =============================

def resolve_display_info(game):
    phase = game["phase"]
    mode = game["info_mode"]

    # FULL BROADCAST → live equity
    if mode == INFO_FULL:
        return game["equity_by_phase"].get(phase)

    # PROTECTED MODE → delayed equity
    if mode == INFO_DELAYED:
        last = game.get("last_completed_phase")
        if not last:
            return None

        # Never show current street equity
        if last == phase:
            prev = PHASE_BACK.get(last)
            return game["equity_by_phase"].get(prev)

        # Show the most recently completed street
        return game["equity_by_phase"].get(last)

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

        # Start immediately so host is at PREFLOP
        scan_full_deck_sim()
        deal_hole_cards()
        bump_version()

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

        # Misdeal / force button
        if "force_button" in request.form:
            new_btn = int(request.form["force_button"])

            game_state = start_new_game(
                game_state["players"],
                new_btn,
                game_state["info_mode"],
                manual_button=True,
            )

            scan_full_deck_sim()
            deal_hole_cards()
            bump_version()
            return redirect("/host")

        # Main flow button
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
                    manual_button=False,
                )

                scan_full_deck_sim()
                deal_hole_cards()

            elif game_state["phase"] == "PREFLOP":
                deal_flop()

            elif game_state["phase"] == "FLOP":
                deal_turn()

            elif game_state["phase"] == "TURN":
                deal_river()

            elif game_state["phase"] == "RIVER":
                game_state["phase"] = "SHOWDOWN"

            bump_version()
            return redirect("/host")

        return redirect("/host")

    # ---------- GET: equity / showdown resolution ----------
    phase = game_state["phase"]

    # Track whether public display changes (to bump version only when needed)
    prev_display = list(game_state.get("display_equities", [0] * 6))
    prev_tie = float(game_state.get("tie_probability", 0))

    if phase == "SHOWDOWN":
        resolve_showdown(game_state)

        # cache showdown too (useful for FULL mode consistency)
        game_state["equity_by_phase"][phase] = {
            "equities": list(game_state["display_equities"]),
            "hand_ranks": dict(game_state.get("display_hand_ranks", {})),
            "tie_probability": game_state["tie_probability"],
        }

        # mark showdown as completed for delayed logic
        game_state["last_completed_phase"] = "SHOWDOWN"

    elif phase in ("PREFLOP", "FLOP", "TURN", "RIVER"):
        # compute + cache equity once per phase
        if phase not in game_state["equity_by_phase"]:
            equities, tie_prob, hand_ranks = calculate_equity_multi(
                [game_state["hands"][p] for p in game_state["players"]],
                player_names=game_state["players"],
                iterations=500,
                board_str=game_state["board"],
            )

            game_state["equity_by_phase"][phase] = {
                "equities": equities,
                "hand_ranks": hand_ranks,
                "tie_probability": tie_prob,
            }

            # ✅ THIS was missing in your code
            game_state["last_completed_phase"] = phase

        # resolve what can be shown publicly/host display-equity
        info = resolve_display_info(game_state)
        if info:
            game_state["display_equities"] = info["equities"]
            game_state["display_hand_ranks"] = info.get("hand_ranks", {})
            game_state["tie_probability"] = info.get("tie_probability", 0)
        else:
            game_state["display_equities"] = [0] * 6
            game_state["display_hand_ranks"] = {}
            game_state["tie_probability"] = 0

    else:
        game_state["display_equities"] = [0] * 6
        game_state["display_hand_ranks"] = {}
        game_state["tie_probability"] = 0

    # If delayed equities became available without a POST action, bump version now
    if game_state["display_equities"] != prev_display or game_state["tie_probability"] != prev_tie:
        bump_version()

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
    # Always render the page
    # Frontend will handle "not configured" state
    return render_template("audience.html", game=game_state)


@app.route("/game_state")
def game_state_json():
    if game_state is None:
        return {}, 200

    public = dict(game_state)

    # PROTECTED MODE — hide sensitive info
    if game_state["info_mode"] == INFO_DELAYED:
        public["hands"] = {}
        public["display_hand_ranks"] = {}

    # FULL BROADCAST — allow everything
    elif game_state["info_mode"] == INFO_FULL:
        # hands are already in game_state
        # display_hand_ranks already populated
        pass

    return public


# =============================
# Run
# =============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
