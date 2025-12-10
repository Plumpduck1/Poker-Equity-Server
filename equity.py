from treys import Evaluator, Card, Deck

# Map Treys rank ints to readable strings
RANK_STR = {0:'2', 1:'3', 2:'4', 3:'5', 4:'6', 5:'7', 6:'8', 7:'9', 8:'T', 9:'J', 10:'Q', 11:'K', 12:'A'}

def calculate_equity_multi(hands_str, player_names, iterations=2000, board_str=None):
    """
    Calculate equities and hand descriptions for multiple players.
    
    hands_str: list of lists of card strings, e.g. [["Ac","Kd"], ["7c","7d"]]
    player_names: list of player names in the same order
    iterations: Monte Carlo simulations
    board_str: list of board card strings or None
    
    Returns: equities list (%), tie %, hand_ranks dict {player_name: description}
    """
    e = Evaluator()
    num_players = len(hands_str)
    hands = [[Card.new(c) for c in h] for h in hands_str]
    board = [Card.new(c) for c in board_str] if board_str else []

    wins = [0] * num_players
    ties = 0

    # Monte Carlo simulations
    for _ in range(iterations):
        deck = Deck()
        # Remove player and board cards
        for h in hands:
            for c in h:
                if c in deck.cards:
                    deck.cards.remove(c)
        for c in board:
            if c in deck.cards:
                deck.cards.remove(c)

        # Complete board to 5 cards
        sim_board = board.copy()
        while len(sim_board) < 5:
            card = deck.draw()
            if isinstance(card, list):
                sim_board.append(card[0])
            else:
                sim_board.append(card)

        scores = [e.evaluate(h, sim_board) for h in hands]
        min_score = min(scores)
        winners = [i for i, s in enumerate(scores) if s == min_score]

        if len(winners) == 1:
            wins[winners[0]] += 1
        else:
            ties += 1

    equities = [w / iterations * 100 for w in wins]
    tie_equity = ties / iterations * 100

    # Hand descriptions using best 5-card hand
    hand_ranks = {}
    for pname, h_str in zip(player_names, hands_str):
        hand_ranks[pname] = describe_hand(h_str, board_str or [])

    return equities, tie_equity, hand_ranks


def describe_hand(hole_cards_str, board_str):
    """
    Return a human-readable description of a player's best hand.
    """
    e = Evaluator()
    hole_cards = [Card.new(c) for c in hole_cards_str]
    board_cards = [Card.new(c) for c in board_str] if board_str else []
    all_cards = hole_cards + board_cards

    if not board_cards:
        # Pre-flop
        if hole_cards_str[0][0] == hole_cards_str[1][0]:
            return f"Pair of {hole_cards_str[0][0]}s"
        else:
            # High card
            ranks = sorted([Card.get_rank_int(c) for c in hole_cards], reverse=True)
            return f"High Card {RANK_STR[ranks[0]]}"
    else:
        # Post-flop
        score = e.evaluate(hole_cards, board_cards)
        rank_class = e.get_rank_class(score)
        class_name = e.class_to_string(rank_class)

        # Build frequency map of ranks
        freq = {}
        for c in all_cards:
            r = Card.get_rank_int(c)
            freq[r] = freq.get(r, 0) + 1
        freq_sorted = sorted(freq.items(), key=lambda x: (-x[1], -x[0]))  # by count, then rank
        ranks_only = [r for r, _ in freq_sorted]

        # Identify high card
        high_card = RANK_STR[max([Card.get_rank_int(c) for c in all_cards])]

        if class_name == "High Card":
            return f"High Card {high_card}"
        elif class_name == "Pair":
            return f"Pair of {RANK_STR[freq_sorted[0][0]]}s"
        elif class_name == "Two Pair":
            return f"Two Pair, {RANK_STR[freq_sorted[0][0]]}s over {RANK_STR[freq_sorted[1][0]]}s"
        elif class_name == "Three of a Kind":
            return f"Three of a Kind, {RANK_STR[freq_sorted[0][0]]}s"
        elif class_name == "Straight":
            # Find straight range in all_cards
            straight_ranks = sorted(set([Card.get_rank_int(c) for c in all_cards]), reverse=True)
            return f"Straight, {RANK_STR[straight_ranks[-1]]} to {RANK_STR[straight_ranks[0]]}"
        elif class_name == "Flush":
            return f"Flush, {high_card} high"
        elif class_name == "Full House":
            return f"Full House, {RANK_STR[freq_sorted[0][0]]}s full of {RANK_STR[freq_sorted[1][0]]}s"
        elif class_name == "Four of a Kind":
            return f"Four of a Kind, {RANK_STR[freq_sorted[0][0]]}s"
        elif class_name == "Straight Flush":
            straight_ranks = sorted(set([Card.get_rank_int(c) for c in all_cards]), reverse=True)
            return f"Straight Flush, {RANK_STR[straight_ranks[-1]]} to {RANK_STR[straight_ranks[0]]}"
        else:
            return class_name
