from treys import Evaluator, Card, Deck

def calculate_equity_multi(hands_str, iterations=2000, board_str=None):
    """
    hands_str: list of lists of card strings
    iterations: number of Monte Carlo simulations
    board_str: list of board cards, e.g. ["2c","7h","Td"], or None for pre-flop
    Returns: equities list (percent) for each hand + tie %
    """
    e = Evaluator()
    num_players = len(hands_str)
    hands = [[Card.new(c) for c in h] for h in hands_str]

    board = []
    if board_str:
        board = [Card.new(c) for c in board_str]

    wins = [0] * num_players
    ties = 0

    for _ in range(iterations):
        deck = Deck()

        # Remove player cards
        for h in hands:
            for c in h:
                if c in deck.cards:
                    deck.cards.remove(c)

        # Remove board cards
        for c in board:
            if c in deck.cards:
                deck.cards.remove(c)

        # Draw remaining board to make 5 cards
        sim_board = board.copy()
        while len(sim_board) < 5:
            card = deck.draw()
            if isinstance(card, list):
                sim_board.append(card[0])
            else:
                sim_board.append(card)

        # Evaluate hands
        scores = [e.evaluate(h, sim_board) for h in hands]
        min_score = min(scores)
        winners = [i for i, s in enumerate(scores) if s == min_score]

        if len(winners) == 1:
            wins[winners[0]] += 1
        else:
            ties += 1

    equities = [w / iterations * 100 for w in wins]
    tie_equity = ties / iterations * 100
    return equities, tie_equity
