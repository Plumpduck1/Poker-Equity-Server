from flask import Flask, render_template, request, redirect
import os
import random
import sqlite3
from equity import calculate_equity_multi

app = Flask(__name__)

# -----------------------------
# Database
# -----------------------------

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

# -----------------------------
# Constants & Helpers
# -----------------------------

RANKS = "23456789TJQKA"
SUITS = "cdhs"

def fresh_deck():
    return [f"{r}{s}" for r in RANKS for s in SUITS]

def get_positions(players, button_index):
    mapping = {
        0: "BTN",
        1: "SB",
        2: "BB",
        3: "UTG",
        4: "HJ",
        5: "CO",
    }
    pos_map = {}
    n = len(players)
    for offset, pos in mapping.items():
        seat = (button_index + offset) % n
        pos_map[players[seat]] = pos
    return pos_map

# -----------------------------
# Global State
# -----------------------------

game_state = None

# -----------------------------
# Deck / Dealing Logic (SIMULATED)
# -----------------------------

def scan_full_deck_sim():
    deck = fresh_deck()
    random.shuffle(deck)
    game_state["deck"] = deck
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
            seat = (start + i) % 6
            player = game_state["players"][seat]
            hands[player].append(scan_next_card())

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

# -----------------------------
# Game Initialisation
# -----------------------------

def start_new_game(players, button_index):
    return {
        "hide_equity": False,
        "players": players,
        "button_index": button_index,
        "phase": "WAITING",
        "deck": [],
        "deck_pointer": 0,
        "burned": [],
        "hands": {},
        "board": [],
        "equities": [0] * 6,
        "hand_ranks": {p: "" for p in players},
        "tie_probability": 0,
    }

# -----------------------------
# Routes
# -----------------------------

@app.route("/host/config", methods=["GET", "POST"])
def host_config():
    global game_state

    if request.method == "POST":
        players = request.form.getlist("players[]")
        button_index = int(request.form["button_index"])

        if len(players) != 6 or any(p.strip() == "" for p in players):
            return "Must enter exactly 6 players", 400

        game_state = start_new_game(players, button_index)
        return redirect("/host")

    return render_template("config.html")

@app.route("/host", methods=["GET", "POST"])
def host_view():
    global game_state

    if game_state is None:
        return redirect("/host/config")

    # -----------------------------
    # RFID POST (from Pi)
    # -----------------------------
    if request.method == "POST" and request.form.get("uid"):
        uid = request.form.get("uid")

        db = get_db()
        row = db.execute(
            "SELECT card FROM rfid_cards WHERE uid = ?",
            (uid,)
        ).fetchone()

        if not row:
            return "Unknown card UID", 400

        card = row[0]
        print(f"RFID scan: {uid} → {card}")

        # Phase 1: acknowledge scan only
        # Phase 2 will inject into game flow

        return "OK", 200

    # -----------------------------
    # UI POST actions
    # -----------------------------
    if request.method == "POST":
        action = request.form.get("action")

        if "toggle_privacy" in request.form:
            game_state["hide_equity"] = not game_state["hide_equity"]
            return redirect("/host")

        if "set_btn" in request.form:
            game_state["button_index"] = int(request.form["set_btn"])
            return redirect("/host")

        if action == "new_hand":
            game_state = start_new_game(
                game_state["players"],
                (game_state["button_index"] - 1) % 6
            )
            return redirect("/host")

        if action == "scan_deck" and game_state["phase"] == "WAITING":
            scan_full_deck_sim()
            return redirect("/host")

        if action == "deal_hole" and game_state["phase"] == "WAITING":
            deal_hole_cards()
            return redirect("/host")

        if action == "next_street":
            if game_state["phase"] == "PREFLOP":
                deal_flop()
            elif game_state["phase"] == "FLOP":
                deal_turn()
            elif game_state["phase"] == "TURN":
                deal_river()
            return redirect("/host")

        return redirect("/host")

    # -----------------------------
    # GET: Equity calculation
    # -----------------------------
    if game_state["phase"] in ("PREFLOP", "FLOP", "TURN", "RIVER"):
        equities, tie_prob, hand_ranks = calculate_equity_multi(
            [game_state["hands"][p] for p in game_state["players"]],
            player_names=game_state["players"],
            iterations=5000,
            board_str=game_state["board"],
        )

        game_state["equities"] = equities
        game_state["hand_ranks"] = hand_ranks
        game_state["tie_probability"] = tie_prob

    positions = get_positions(
        game_state["players"],
        game_state["button_index"],
    )

    player_equity_pairs = list(
        zip(game_state["players"], game_state["equities"])
    )

    return render_template(
        "host.html",
        game=game_state,
        positions=positions,
        player_equity_pairs=player_equity_pairs,
    )

@app.route("/api/register_card", methods=["POST"])
def register_card():
    data = request.get_json()
    uid = data["uid"]
    card = data["card"]

    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO rfid_cards (uid, card) VALUES (?, ?)",
        (uid, card)
    )
    db.commit()

    return {"status": "registered", "uid": uid, "card": card}, 200

@app.route("/")
def audience_view():
    if game_state is None:
        return "Game not configured", 400

    player_equity_pairs = list(
        zip(game_state["players"], game_state["equities"])
    )

    return render_template(
        "audience.html",
        game=game_state,
        player_equity_pairs=player_equity_pairs,
    )

@app.route("/game_state")
def game_state_json():
    if game_state is None:
        return {}, 400
    return game_state

@app.route("/_debug/db")
def debug_db():
    db = get_db()
    rows = db.execute("SELECT * FROM rfid_cards").fetchall()
    return {
        "rfid_cards": rows
    }

# -----------------------------
# Run
# -----------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
