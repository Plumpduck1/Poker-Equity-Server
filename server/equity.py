from treys import Evaluator, Card, Deck

# ---------------------------------
# Rank mapping
# ---------------------------------

RANK_STR = {
    0: '2', 1: '3', 2: '4', 3: '5', 4: '6',
    5: '7', 6: '8', 7: '9', 8: 'T', 9: 'J',
    10: 'Q', 11: 'K', 12: 'A'
}

# ---------------------------------
# Straight detection (5-card only)
# ---------------------------------

def find_five_card_straight(cards):
    """
    Returns:
        ("A", "5") for wheel straight
        (low_rank_int, high_rank_int) for normal straight
        None if no straight exists
    """
    ranks = set(Card.get_rank_int(c) for c in cards)

    # Wheel: A-2-3-4-5
    if {12, 0, 1, 2, 3}.issubset(ranks):
        return ("A", "5")

    # Normal straights
    for high in range(12, 3, -1):
        window = {high - i for i in range(5)}
        if window.issubset(ranks):
            return (high - 4, high)

    return None

# ---------------------------------
# Equity calculation
# ---------------------------------

def calculate_equity_multi(hands_str, player_names, iterations=2000, board_str=None):
    evaluator = Evaluator()
    num_players = len(hands_str)

    hands = [[Card.new(c) for c in h] for h in hands_str]
    board = [Card.new(c) for c in board_str] if board_str else []

    wins = [0.0] * num_players
    tie_count = 0

    for _ in range(iterations):
        deck = Deck()

        # Remove known cards
        for h in hands:
            for c in h:
                if c in deck.cards:
                    deck.cards.remove(c)

        for c in board:
            if c in deck.cards:
                deck.cards.remove(c)

        # Complete board
        sim_board = board.copy()
        while len(sim_board) < 5:
            card = deck.draw()
            sim_board.append(card[0] if isinstance(card, list) else card)

        scores = [evaluator.evaluate(h, sim_board) for h in hands]
        best_score = min(scores)
        winners = [i for i, s in enumerate(scores) if s == best_score]

        # Split pot equity
        share = 1.0 / len(winners)
        for w in winners:
            wins[w] += share

        if len(winners) > 1:
            tie_count += 1

    equities = [(w / iterations) * 100 for w in wins]
    tie_probability = (tie_count / iterations) * 100

    hand_ranks = {
        pname: describe_hand(h, board_str or [])
        for pname, h in zip(player_names, hands_str)
    }

    return equities, tie_probability, hand_ranks

# ---------------------------------
# Hand description
# ---------------------------------

def describe_hand(hole_cards_str, board_str):
    evaluator = Evaluator()

    hole_cards = [Card.new(c) for c in hole_cards_str]
    board_cards = [Card.new(c) for c in board_str] if board_str else []
    all_cards = hole_cards + board_cards

    # -------- Preflop --------
    if not board_cards:
        if hole_cards_str[0][0] == hole_cards_str[1][0]:
            return f"Pair of {hole_cards_str[0][0]}s"
        ranks = sorted((Card.get_rank_int(c) for c in hole_cards), reverse=True)
        return f"High Card {RANK_STR[ranks[0]]}"

    score = evaluator.evaluate(hole_cards, board_cards)
    rank_class = evaluator.get_rank_class(score)
    class_name = evaluator.class_to_string(rank_class)

    # Frequency map
    freq = {}
    for c in all_cards:
        r = Card.get_rank_int(c)
        freq[r] = freq.get(r, 0) + 1

    freq_sorted = sorted(freq.items(), key=lambda x: (-x[1], -x[0]))
    high_card = RANK_STR[max(freq.keys())]

    # -------- Descriptions --------

    if class_name == "High Card":
        return f"High Card {high_card}"

    if class_name == "Pair":
        return f"Pair of {RANK_STR[freq_sorted[0][0]]}s"

    if class_name == "Two Pair":
        return f"Two Pair, {RANK_STR[freq_sorted[0][0]]}s over {RANK_STR[freq_sorted[1][0]]}s"

    if class_name == "Three of a Kind":
        return f"Three of a Kind, {RANK_STR[freq_sorted[0][0]]}s"

    if class_name == "Straight":
        result = find_five_card_straight(all_cards)
        if result == ("A", "5"):
            return "Straight, A to 5"
        low, high = result
        return f"Straight, {RANK_STR[low]} to {RANK_STR[high]}"

    if class_name == "Flush":
        return f"Flush, {high_card} high"

    if class_name == "Full House":
        return f"Full House, {RANK_STR[freq_sorted[0][0]]}s full of {RANK_STR[freq_sorted[1][0]]}s"

    if class_name == "Four of a Kind":
        return f"Four of a Kind, {RANK_STR[freq_sorted[0][0]]}s"

    if class_name == "Straight Flush":
        result = find_five_card_straight(all_cards)
        if result == ("A", "5"):
            return "Straight Flush, A to 5"

        low, high = result
        if high == 12 and low == 8:
            return "Royal Flush"

        return f"Straight Flush, {RANK_STR[low]} to {RANK_STR[high]}"

    return class_name
