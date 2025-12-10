from flask import Flask, render_template, request
import random
from equity import calculate_equity_multi  # updated equity calculation

app = Flask(__name__)

# --- Initial game state ---
players = ["Charles", "Peter", "Ryan", "Mihir", "Xavier", "Danial"]
positions_order = ["UTG", "HJ", "CO", "BTN", "SB", "BB"]

def new_game():
    hands_pool = [f"{r}{s}" for r in "23456789TJQKA" for s in "cdhs"]
    hands = {}
    for p in players:
        hands[p] = random.sample(hands_pool, 2)
        for c in hands[p]:
            hands_pool.remove(c)
    return {
        "players": players[:],
        "positions": dict(zip(players, positions_order)),
        "hands": hands,
        "board": [],
        "equities": [0]*len(players),
        "tie": 0,
        "hand_ranks": {p: "" for p in players}
    }

game_state = new_game()

# --- Helper to rotate positions ---
def rotate_positions():
    global game_state
    game_state["players"] = game_state["players"][1:] + [game_state["players"][0]]
    game_state["positions"] = dict(zip(game_state["players"], positions_order))

# --- Routes ---
@app.route("/host", methods=["GET", "POST"])
def host_view():
    global game_state
    if request.method == "POST":
        action = request.form.get("action")
        deck = [f"{r}{s}" for r in "23456789TJQKA" for s in "cdhs"]
        used = [c for h in game_state["hands"].values() for c in h] + game_state["board"]
        deck = [c for c in deck if c not in used]
        random.shuffle(deck)

        if action == "flop" and len(game_state["board"]) == 0:
            game_state["board"] += [deck.pop() for _ in range(3)]
        elif action == "turn" and len(game_state["board"]) == 3:
            game_state["board"].append(deck.pop())
        elif action == "river" and len(game_state["board"]) == 4:
            game_state["board"].append(deck.pop())
        elif action == "reset":
            rotate_positions()
            hands_pool = [f"{r}{s}" for r in "23456789TJQKA" for s in "cdhs"]
            hands = {}
            for p in game_state["players"]:
                hands[p] = random.sample(hands_pool, 2)
                for c in hands[p]:
                    hands_pool.remove(c)
            game_state["hands"] = hands
            game_state["board"] = []
            game_state["equities"] = [0]*len(players)
            game_state["tie"] = 0
            game_state["hand_ranks"] = {p: "" for p in game_state["players"]}

    # --- Calculate equities and hand ranks ---
    equities, tie, hand_ranks = calculate_equity_multi(
        [game_state["hands"][p] for p in game_state["players"]],
        player_names=game_state["players"],
        iterations=2000,
        board_str=game_state["board"]
    )
    game_state["equities"] = equities
    game_state["tie"] = tie
    game_state["hand_ranks"] = hand_ranks

    player_equity_pairs = list(zip(game_state["players"], game_state["equities"]))
    return render_template("host.html", game=game_state, player_equity_pairs=player_equity_pairs)

@app.route("/", methods=["GET"])
def audience_view():
    player_equity_pairs = list(zip(game_state["players"], game_state["equities"]))
    return render_template("audience.html", game=game_state, player_equity_pairs=player_equity_pairs)

@app.route("/game_state")
def game_state_json():
    return game_state

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
