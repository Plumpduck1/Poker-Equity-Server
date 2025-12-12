from flask import Flask, render_template, request, redirect
import random, os
from equity import calculate_equity_multi

app = Flask(__name__)

# -----------------------------
# Constants & Helpers
# -----------------------------

RANKS = "23456789TJQKA"
SUITS = "cdhs"


def get_positions(players, button_index):
    """
    Correct 6-max position mapping.
    players = fixed seat order (clockwise)
    button_index = index of BTN in players
    """
    pos_map = {}
    n = len(players)

    mapping = {
        0: "BTN",
        1: "SB",
        2: "BB",
        3: "UTG",
        4: "HJ",
        5: "CO",
    }

    for offset, pos in mapping.items():
        seat = (button_index + offset) % n
        pos_map[players[seat]] = pos

    return pos_map



def fresh_deck():
    return [f"{r}{s}" for r in RANKS for s in SUITS]


# -----------------------------
# Global State
# -----------------------------

game_state = None


# -----------------------------
# Deck / Dealing Logic
# -----------------------------

def scan_full_deck_sim():
    """
    Simulate scanning all 52 cards.
    deck[0] is the TOP of deck (first card dealt).
    """
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
    """
    Deal hole cards SB → BTN, 2 rounds.
    """
    hands = {p: [] for p in game_state["players"]}

    # SB is immediately left of BTN
    start = (game_state["button_index"] + 1) % 6

    for _ in range(2):
        for i in range(6):
            seat = (start + i) % 6
            player = game_state["players"][seat]
            hands[player].append(scan_next_card())

    game_state["hands"] = hands
    game_state["phase"] = "PREFLOP"

    # ALWAYS initialize equity fields
    num_players = len(game_state["players"])
    game_state["equities"] = [0.0] * num_players
    game_state["tie_probability"] = 0.0
    game_state["hand_ranks"] = {p: "" for p in game_state["players"]}



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
        "button_index": button_index,   # index of BTN
        "phase": "WAITING",              # WAITING | PREFLOP | FLOP | TURN | RIVER
        "deck": [],
        "deck_pointer": 0,
        "burned": [],
        "hands": {},
        "board": [],
        "equities": [0] * 6,
        "hand_ranks": {p: "" for p in players},
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
            return "Error: Must enter exactly 6 player names", 400

        game_state = start_new_game(players, button_index)
        return redirect("/host")

    return render_template("config.html")


@app.route("/host", methods=["GET", "POST"])
def host_view():
    global game_state

    

    if game_state is None:
        return redirect("/host/config")

    if request.method == "POST":
        action = request.form.get("action")
        
        # -----------------------------
        # Dealer privacy toggle
        # -----------------------------
        if "toggle_privacy" in request.form:
            game_state["hide_equity"] = not game_state.get("hide_equity", False)
            return redirect("/host")

        # -----------------------------
        # Manual BTN override
        # -----------------------------
        if "set_btn" in request.form:
            btn_index = int(request.form.get("set_btn"))
            game_state["button_index"] = btn_index
            return redirect("/host")

        # -----------------------------
        # New Hand
        # -----------------------------
        if action == "new_hand":
            game_state["button_index"] = (game_state["button_index"] - 1) % 6
            game_state["phase"] = "WAITING"
            game_state["deck"] = []
            game_state["deck_pointer"] = 0
            game_state["burned"] = []
            game_state["hands"] = {}
            game_state["board"] = []
            game_state["equities"] = [0] * 6
            game_state["hand_ranks"] = {p: "" for p in game_state["players"]}
            return redirect("/host")

        # -----------------------------
        # Scan Deck (simulated)
        # -----------------------------
        if action == "scan_deck" and game_state["phase"] == "WAITING":
            scan_full_deck_sim()
            return redirect("/host")

        # -----------------------------
        # Deal Hole Cards
        # -----------------------------
        if action == "deal_hole" and game_state["phase"] == "WAITING":
            deal_hole_cards()
            return redirect("/host")

        # -----------------------------
        # Deal Next Street
        # -----------------------------
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
        equities, tie_probability, hand_ranks = calculate_equity_multi(
            [game_state["hands"][p] for p in game_state["players"]],
            player_names=game_state["players"],
            iterations=5000,
            board_str=game_state["board"],
        )

        game_state["equities"] = equities
        game_state["tie_probability"] = tie_probability
        game_state["hand_ranks"] = hand_ranks
    else:
        # SAFE defaults so host never crashes
        game_state["equities"] = [0.0] * len(game_state["players"])
        game_state["tie_probability"] = 0.0
        game_state["hand_ranks"] = {p: "" for p in game_state["players"]}



    positions = get_positions(
        game_state["players"],
        game_state["button_index"],
    )

    player_equity_pairs = list(zip(game_state["players"], game_state["equities"]))

    return render_template(
        "host.html",
        game=game_state,
        positions=positions,
        player_equity_pairs=player_equity_pairs,
    )



@app.route("/", methods=["GET"])
def audience_view():
    if game_state is None:
        return "Game not configured", 400

    player_equity_pairs = list(zip(game_state["players"], game_state["equities"]))
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


# -----------------------------
# Run
# -----------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)