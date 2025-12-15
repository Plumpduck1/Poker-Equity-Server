from flask import Flask, render_template, request, redirect, abort
import os
import random
import sqlite3
import string

from equity import calculate_equity_multi
from treys import Evaluator, Card

app = Flask(__name__)

# =============================
# Info modes (ONLY 2)
# =============================

INFO_FULL = "FULL"               # live equities + hole cards (home games)
INFO_DELAYED = "DELAYED_EQUITY"  # 1-street delayed equities + no hole cards

PHASE_BACK = {
    "PREFLOP": None,
    "FLOP": "PREFLOP",
    "TURN": "FLOP",
    "RIVER": "TURN",
    "SHOWDOWN": "RIVER",
}

STREETS = ("PREFLOP", "FLOP", "TURN", "RIVER", "SHOWDOWN")

# =============================
# Host code (simple security)
# =============================

def generate_host_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(random.choice(alphabet) for _ in range(4))

# =============================
# Database (RFID future-proof)
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
    """
    Real poker positions, 2–10 players, button-relative
    """
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

    iters = int(iters * mult)
    return max(200, min(2000, iters))

# =============================
# Global state (single table)
# =============================

game_state = None

def bump_version():
    if game_state is not None:
        game_state["version"] += 1

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
    n = len(game_state["players"])
    hands = {p: [] for p in game_state["players"]}
    start = (game_state["button_index"] + 1) % n

    for _ in range(2):
        for i in range(n):
            p = game_state["players"][(start + i) % n]
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
        share if p in winners else 0.0 for p in game["players"]
    ]
    game["tie_probability"] = 100.0 if len(winners) > 1 else 0.0

# =============================
# Game init
# =============================

def start_new_game(players, button_index, info_mode, manual_button=False, host_code=None):
    """
    IMPORTANT:
    - host_code must persist across the lifetime of the game session
      otherwise you lock yourself out when you start a new hand.
    """
    n = len(players)
    return {
        "version": 0,
        "host_code": host_code or generate_host_code(),

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

        "equity_by_phase": {},
        "last_completed_phase": None,
        "display_equities": [0.0] * n,
        "display_hand_ranks": {},
        "tie_probability": 0.0,
    }

# =============================
# Equity visibility
# =============================

def resolve_display_info(game):
    if game["info_mode"] == INFO_FULL:
        return game["equity_by_phase"].get(game["phase"])

    if game["info_mode"] == INFO_DELAYED:
        prev = PHASE_BACK.get(game["phase"])
        return game["equity_by_phase"].get(prev) if prev else None

    return None

# =============================
# Routes
# =============================

@app.route("/host/config", methods=["GET", "POST"])
def host_config():
    global game_state

    # =============================
    # GAME EXISTS → LOCKED
    # =============================
    if game_state is not None:

        # GET → show lock screen
        if request.method == "GET":
            return render_template("locked.html", target="config", error=False)

        # POST → validate code
        code = request.form.get("host_code", "").upper()

        if code != game_state.get("host_code"):
            return render_template("locked.html", target="config", error=True)

        # ✅ Correct code → allow reconfiguration
        return render_template("config.html", game=game_state)

    # =============================
    # NO GAME → NORMAL CONFIG
    # =============================
    if request.method == "POST":
        players = [p.strip() for p in request.form.getlist("players[]")]

        if not (2 <= len(players) <= 10):
            return "2–10 players required", 400

        button_index = int(request.form["button_index"]) % len(players)
        info_mode = request.form.get("info_mode", INFO_DELAYED)

        game_state = start_new_game(players, button_index, info_mode)
        scan_full_deck_sim()
        deal_hole_cards()
        bump_version()

        return redirect(f"/host?host_code={game_state['host_code']}")

    return render_template("config.html")




@app.route("/host", methods=["GET", "POST"])
def host_view():
    global game_state

    if game_state is None:
        return redirect("/host/config")

    # 🔐 validate code
    code = request.form.get("host_code") or request.args.get("host_code", "")
    code = code.upper()

    if code != game_state.get("host_code"):
        return render_template("locked.html", target="host", error=True)

    n = len(game_state["players"])

    # ---------- POST actions ----------
    if request.method == "POST":

        if "force_button" in request.form:
            new_btn = int(request.form["force_button"]) % n
            game_state.update(
                start_new_game(game_state["players"], new_btn, game_state["info_mode"], True)
            )
            scan_full_deck_sim()
            deal_hole_cards()
            bump_version()
            return redirect(f"/host?host_code={game_state['host_code']}")

        if request.form.get("action") == "advance":
            phase = game_state["phase"]

            if phase in ("WAITING", "SHOWDOWN"):
                next_btn = (
                    game_state["button_index"]
                    if game_state["manual_button"]
                    else (game_state["button_index"] - 1) % n
                )
                game_state.update(
                    start_new_game(game_state["players"], next_btn, game_state["info_mode"])
                )
                scan_full_deck_sim()
                deal_hole_cards()

            elif phase == "PREFLOP": deal_flop()
            elif phase == "FLOP": deal_turn()
            elif phase == "TURN": deal_river()
            elif phase == "RIVER": game_state["phase"] = "SHOWDOWN"

            bump_version()
            return redirect(f"/host?host_code={game_state['host_code']}")

    positions = get_positions(game_state["players"], game_state["button_index"])
    return render_template("host.html", game=game_state, positions=positions)

@app.route("/")
def audience_view():
    return render_template("audience.html", game=game_state)

@app.route("/game_state")
def game_state_json():
    if game_state is None:
        return {}, 200

    public = dict(game_state)

    # Protected mode: do NOT leak hole cards or hand ranks
    if game_state["info_mode"] == INFO_DELAYED:
        public["hands"] = {}
        public["display_hand_ranks"] = {}

    return public

# =============================
# Run
# =============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
