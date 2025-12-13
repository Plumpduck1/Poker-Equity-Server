from flask import Flask, render_template, request, redirect
import os
import random
import sqlite3

from equity import calculate_equity_multi  # (optionally also import describe_hand if you want)
from treys import Evaluator, Card

app = Flask(__name__)

# =============================
# Info modes (ONLY 2)
# =============================

INFO_FULL = "FULL"               # live equities + hole cards (home games)
INFO_DELAYED = "DELAYED_EQUITY"  # 1-street delayed equities + no hole cards (public)

# "previous street" mapping (used by protected mode)
PHASE_BACK = {
    "PREFLOP": None,
    "FLOP": "PREFLOP",
    "TURN": "FLOP",
    "RIVER": "TURN",
    "SHOWDOWN": "RIVER",
}

STREETS = ("PREFLOP", "FLOP", "TURN", "RIVER", "SHOWDOWN")

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

# Position labels per table size (2–10)
POSITION_MAP = {
    2: ["BTN", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["BTN", "SB", "BB", "UTG"],
    5: ["BTN", "SB", "BB", "UTG", "CO"],
    6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
    7: ["BTN", "SB", "BB", "UTG", "UTG+1", "HJ", "CO"],
    8: ["BTN", "SB", "BB", "UTG", "UTG+1", "UTG+2", "HJ", "CO"],
    9: ["BTN", "SB", "BB", "UTG", "UTG+1", "UTG+2", "UTG+3", "HJ", "CO"],
    10:["BTN", "SB", "BB", "UTG", "UTG+1", "UTG+2", "UTG+3", "UTG+4", "HJ", "CO"],
}

def get_positions(players, button_index):
    n = len(players)
    labels = POSITION_MAP.get(n)
    if not labels:
        # Fallback (should never happen if we enforce 2–10)
        labels = ["BTN"] + [f"Seat{i}" for i in range(2, n + 1)]

    return {
        players[(button_index + i) % n]: labels[i]
        for i in range(n)
    }

def iterations_for(players_count: int, phase: str) -> int:
    """
    Adaptive Monte Carlo iterations:
    - More players => fewer iterations to keep responsiveness
    - Later streets => fewer iterations (less unknown, lower variance)
    """
    n = max(2, int(players_count))

    # Base scaled by players (heads-up can afford more)
    base = 2200  # tweakable
    iters = int(base / (n ** 0.9))  # gentle decay

    # Street multiplier (later streets can be lower)
    mult = {
        "PREFLOP": 1.0,
        "FLOP": 0.75,
        "TURN": 0.55,
        "RIVER": 0.40,
    }.get(phase, 0.60)

    iters = int(iters * mult)

    # Clamp to sane limits
    return max(200, min(2000, iters))

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
    n = len(game_state["players"])
    hands = {p: [] for p in game_state["players"]}
    start = (game_state["button_index"] + 1) % n  # first card to SB (or next seat)

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
# Showdown (deterministic winner)
# =============================

def resolve_showdown(game):
    """
    Deterministic final result:
    winner(s) get 100% split.
    This is safe to reveal at hand end in both modes.
    """
    evaluator = Evaluator()
    board = [Card.new(c) for c in game["board"]]

    scores = {}
    for p in game["players"]:
        hole = [Card.new(c) for c in game["hands"][p]]
        scores[p] = evaluator.evaluate(hole, board)

    best = min(scores.values())
    winners = [p for p, s in scores.items() if s == best]

    share = 100.0 / len(winners)
    game["display_equities"] = [share if p in winners else 0.0 for p in game["players"]]
    game["tie_probability"] = 100.0 if len(winners) > 1 else 0.0

# =============================
# Game init
# =============================

def start_new_game(players, button_index, info_mode, manual_button=False):
    n = len(players)
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
        "last_completed_phase": None,   # for delayed mode
        "display_equities": [0.0] * n,
        "display_hand_ranks": {},
        "tie_probability": 0.0,
    }

# =============================
# Equity visibility resolver
# =============================

def resolve_display_info(game):
    phase = game["phase"]
    mode = game["info_mode"]

    # FULL BROADCAST → live equity for this phase
    if mode == INFO_FULL:
        return game["equity_by_phase"].get(phase)

    # PROTECTED MODE → 1-street delayed
    if mode == INFO_DELAYED:
        prev = PHASE_BACK.get(phase)
        if not prev:
            return None  # nothing to show yet at PREFLOP
        return game["equity_by_phase"].get(prev)

    return None

# =============================
# Routes
# =============================

@app.route("/host/config", methods=["GET", "POST"])
def host_config():
    global game_state

    if request.method == "POST":
        players = [p.strip() for p in request.form.getlist("players[]")]
        button_index = int(request.form["button_index"])
        info_mode = request.form.get("info_mode", INFO_DELAYED)

        # enforce 2–10 players
        if len(players) < 2 or len(players) > 10 or any(p == "" for p in players):
            return "Must enter between 2 and 10 players", 400

        if info_mode not in (INFO_FULL, INFO_DELAYED):
            info_mode = INFO_DELAYED

        n = len(players)
        button_index = button_index % n

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

    n = len(game_state["players"])

    # ---------- POST controls ----------
    if request.method == "POST":
        action = request.form.get("action")

        # Misdeal / force button to a specific seat
        if "force_button" in request.form:
            new_btn = int(request.form["force_button"]) % n

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

        # Main flow button (Next Street / Showdown / Next Hand)
        if action == "advance":
            phase = game_state["phase"]

            if phase in ("WAITING", "SHOWDOWN"):
                # decide whether to rotate button
                if game_state.get("manual_button"):
                    next_btn = game_state["button_index"]
                else:
                    next_btn = (game_state["button_index"] - 1) % n

                game_state = start_new_game(
                    game_state["players"],
                    next_btn,
                    game_state["info_mode"],
                    manual_button=False,
                )

                scan_full_deck_sim()
                deal_hole_cards()

            elif phase == "PREFLOP":
                deal_flop()
            elif phase == "FLOP":
                deal_turn()
            elif phase == "TURN":
                deal_river()
            elif phase == "RIVER":
                game_state["phase"] = "SHOWDOWN"

            bump_version()
            return redirect("/host")

        return redirect("/host")

    # ---------- GET: equity / showdown resolution ----------
    phase = game_state["phase"]

    prev_display = list(game_state.get("display_equities", [0.0] * n))
    prev_tie = float(game_state.get("tie_probability", 0.0))

    # SHOWDOWN: deterministic final
    if phase == "SHOWDOWN":
        resolve_showdown(game_state)

        # Cache showdown result for FULL mode consistency (optional)
        game_state["equity_by_phase"][phase] = {
            "equities": list(game_state["display_equities"]),
            "hand_ranks": dict(game_state.get("display_hand_ranks", {})),
            "tie_probability": float(game_state["tie_probability"]),
        }

        game_state["last_completed_phase"] = "SHOWDOWN"

    # NORMAL STREETS: Monte Carlo (cached per street)
    elif phase in ("PREFLOP", "FLOP", "TURN", "RIVER"):
        if phase not in game_state["equity_by_phase"]:
            iters = iterations_for(n, phase)

            equities, tie_prob, hand_ranks = calculate_equity_multi(
                [game_state["hands"][p] for p in game_state["players"]],
                player_names=game_state["players"],
                iterations=iters,
                board_str=game_state["board"],
            )

            game_state["equity_by_phase"][phase] = {
                "equities": equities,
                "hand_ranks": hand_ranks,
                "tie_probability": tie_prob,
            }

            # mark this street as completed (useful for debugging / future)
            game_state["last_completed_phase"] = phase

        info = resolve_display_info(game_state)
        if info:
            game_state["display_equities"] = list(info.get("equities", [0.0] * n))
            game_state["display_hand_ranks"] = dict(info.get("hand_ranks", {}))
            game_state["tie_probability"] = float(info.get("tie_probability", 0.0))
        else:
            game_state["display_equities"] = [0.0] * n
            game_state["display_hand_ranks"] = {}
            game_state["tie_probability"] = 0.0

    else:
        game_state["display_equities"] = [0.0] * n
        game_state["display_hand_ranks"] = {}
        game_state["tie_probability"] = 0.0

    # If display changed due to first-time equity compute (no POST), bump version
    if game_state["display_equities"] != prev_display or game_state["tie_probability"] != prev_tie:
        bump_version()

    positions = get_positions(game_state["players"], game_state["button_index"])

    return render_template(
        "host.html",
        game=game_state,
        positions=positions,
    )

@app.route("/")
def audience_view():
    # Always render; frontend handles "waiting for host"
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

    # Full broadcast: allow hole cards + hand ranks
    # (Audience JS can show them when info_mode === "FULL")
    return public

# =============================
# Run
# =============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
