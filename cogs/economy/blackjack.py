import random
from collections import defaultdict
from typing import Optional

import discord
from constants.game_config import GameEventType
from discord import app_commands
from utils.balance_helper import calculate_percentage_amount
from utils.base_cog import BaseGameCog
from utils.formatting import format_number

EMOJI_MAP = {
    "A": ":a:",
    "2": ":two:",
    "3": ":three:",
    "4": ":four:",
    "5": ":five:",
    "6": ":six:",
    "7": ":seven:",
    "8": ":eight:",
    "9": ":nine:",
    "10": ":keycap_ten:",
    "J": ":regional_indicator_j:",
    "Q": ":regional_indicator_q:",
    "K": ":regional_indicator_k:",
}


def create_deck():
    """Create and shuffle a deck."""
    ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    deck = ranks * 24
    random.shuffle(deck)
    return deck


def draw_card(deck):
    """Draw a card from deck, reshuffle if needed."""
    if not deck:
        deck.extend(create_deck())
    return deck.pop()


def format_hand(hand):
    """Convert hand to emoji string."""
    return " ".join(EMOJI_MAP.get(card, card) for card in hand)


def calculate_hand_value(hand):
    """Calculate hand value, accounting for Aces."""
    value = 0
    aces = 0
    for card in hand:
        if card in ["J", "Q", "K"]:
            value += 10
        elif card == "A":
            value += 11
            aces += 1
        else:
            value += int(card)
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value


def get_card_value_for_split(card):
    """Get numeric value of card for split comparison."""
    if card in ["J", "Q", "K"]:
        return 10
    elif card == "A":
        return 1
    else:
        return int(card)


def can_split(hand):
    """Check if hand can be split."""
    return len(hand) == 2 and get_card_value_for_split(
        hand[0]
    ) == get_card_value_for_split(hand[1])


def is_soft_17(hand):
    """Check if hand is soft 17 (17 with Ace counted as 11)."""
    return calculate_hand_value(hand) == 17 and "A" in hand


def is_blackjack(hand):
    """Check if hand is natural blackjack."""
    return len(hand) == 2 and calculate_hand_value(hand) == 21


def create_result_embed(
    color, hands_info, dealer_hand, total_outcome, prev_balance, stats, display_bet
):
    """Create standardized blackjack result embed."""
    embed = discord.Embed(
        title="Blackjack Results",
        description=f"Original Bet: ${format_number(display_bet)}",
        color=color,
    )

    # Add each hand
    for i, (hand, outcome, result_text) in enumerate(hands_info):
        hand_name = f"Hand {i+1}" if len(hands_info) > 1 else "Your hand"
        embed.add_field(
            name=f"{hand_name} ({calculate_hand_value(hand)})",
            value=f"{format_hand(hand)}",
            inline=True,
        )

    embed.add_field(
        name=f"Dealer's hand ({calculate_hand_value(dealer_hand)})",
        value=format_hand(dealer_hand),
        inline=False,
    )

    embed.add_field(
        name="Previous Balance", value=f"${format_number(prev_balance)}", inline=True
    )
    embed.add_field(
        name="Current Balance",
        value=f"${format_number(prev_balance + total_outcome)}",
        inline=True,
    )
    embed.add_field(
        name="Total Result",
        value=f"{'Won' if total_outcome > 0 else 'Lost' if total_outcome < 0 else 'Push'} ${format_number(abs(total_outcome))}",
        inline=True,
    )

    ties = (
        stats["blackjacks_played"] - stats["blackjacks_won"] - stats["blackjacks_lost"]
    )
    embed.set_footer(
        text=f"Blackjacks Won: {stats['blackjacks_won']} | "
        f"Blackjacks Lost: {stats['blackjacks_lost']} | "
        f"Blackjacks Tied: {ties} | "
        f"Blackjacks Played: {stats['blackjacks_played']}"
    )
    return embed


async def perform_blackjack(bot, interaction, user_id, amount, action, balance):
    """Execute a blackjack game."""
    stats_raw = await bot.database.game_db.get_user_game_stats(user_id)
    stats = defaultdict(int, stats_raw.get("game_stats", {}))

    deck = create_deck()
    player_hand = [draw_card(deck), draw_card(deck)]
    dealer_hand = [draw_card(deck), draw_card(deck)]

    player_value = calculate_hand_value(player_hand)
    dealer_value = calculate_hand_value(dealer_hand)

    # Handle natural blackjack
    if player_value == 21:
        stats["blackjacks_played"] += 1

        if dealer_value == 21:
            won, lost = False, False
            result = "Push! Both you and the dealer have blackjack. 🤝"
            outcome = 0
            color = discord.Color.gold()
        else:
            won, lost = True, False
            result = "Blackjack! You win with a natural 21! 🎉 Won"
            outcome = int(amount * 1.5)
            color = discord.Color.green()

        stats["blackjacks_won"] += 1 if won else 0
        stats["blackjacks_lost"] += 1 if lost else 0

        win_value = True if won else False if lost else None
        hands_info = [(player_hand, outcome, result)]
        embed = create_result_embed(
            color, hands_info, dealer_hand, outcome, balance, stats, display_bet=amount
        )

        await interaction.edit_original_response(embed=embed, view=None)
        await bot.database.user_db.increment_balance(user_id, outcome)
        await bot.database.game_db.set_user_game_stats(
            user_id, GameEventType.BLACKJACK, win_value, abs(outcome)
        )
        bot.active_blackjack_players.discard(user_id)
        return

    # Continue with normal gameplay
    embed = discord.Embed(
        title="Blackjack",
        description=f"Bet Amount: ${format_number(amount)}",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name=f"Your hand ({player_value})",
        value=f"{format_hand(player_hand)}\nBet: ${format_number(amount)}",
    )
    embed.add_field(
        name=f"Dealer shows ({calculate_hand_value([dealer_hand[0]])})",
        value=f"{EMOJI_MAP.get(dealer_hand[0])} ❓",
        inline=False,
    )

    view = BlackjackView(bot, user_id, deck, [player_hand], dealer_hand, amount, stats)
    view.update_button_states()
    message = await interaction.edit_original_response(embed=embed, view=view)
    view.message = message


class Blackjack(BaseGameCog):
    """Blackjack game cog."""

    @app_commands.command(name="blackjack", description="Play a game of blackjack")
    @app_commands.describe(
        amount="The amount to bet", action="Choose a percentage of your balance"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="100%", value="100%"),
            app_commands.Choice(name="75%", value="75%"),
            app_commands.Choice(name="50%", value="50%"),
            app_commands.Choice(name="25%", value="25%"),
        ]
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def blackjack(
        self,
        interaction: discord.Interaction,
        amount: Optional[app_commands.Range[int, 1, None]] = None,
        action: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        """Blackjack command using unified handler."""
        user_id = interaction.user.id

        # Specific check for blackjack (not using pre_game_checks since we have custom logic)
        if user_id in self.bot.active_blackjack_players:
            await interaction.response.send_message(
                "You are already in a Blackjack game!", ephemeral=True
            )
            return

        await interaction.response.defer()

        # Validate parameters
        if not action and not amount:
            await interaction.edit_original_response(
                content="You must specify an amount or choose a blackjack option.",
            )
            return

        if amount and action:
            await interaction.edit_original_response(
                content="You can only choose one option: amount or action."
            )
            return

        balance = await self.get_balance(user_id)

        if action and not amount:
            amount = calculate_percentage_amount(balance, action.value)

        if not await self.validate_balance(
            user_id, amount, interaction, deferred=True, balance=balance
        ):
            return

        # Add player to active blackjack players
        self.bot.active_blackjack_players.add(user_id)
        await perform_blackjack(
            self.bot,
            interaction,
            user_id,
            amount,
            action.value if action else None,
            balance,
        )


class BlackjackView(discord.ui.View):
    """View for blackjack gameplay."""

    def __init__(self, bot, user_id, deck, hands, dealer_hand, bet_per_hand, stats):
        super().__init__(timeout=180)
        self.bot = bot
        self.user_id = user_id
        self.deck = deck
        self.hands = hands
        self.dealer_hand = dealer_hand
        self.original_bet = bet_per_hand
        self.bets = [bet_per_hand] * len(hands)
        self.current_hand = 0
        self.interaction = None
        self.stats = stats
        self.message = None
        self.first_move_done = [False] * len(hands)
        self.hand_finished = [False] * len(hands)
        self.split_aces = any("A" in hand for hand in hands if len(hands) > 1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your game!", ephemeral=True
            )
            return False
        self.interaction = interaction
        return True

    async def on_timeout(self):
        """Handle timeout."""
        self.bot.active_blackjack_players.discard(self.user_id)
        total_bet = sum(self.bets)

        msg = f"⏰ Game timed out due to inactivity. You lost your bet of ${format_number(total_bet)}."

        if self.interaction:
            await self.interaction.edit_original_response(content=msg, view=None)
        elif self.message:
            await self.message.edit(content=msg, embed=None, view=None)

        await self.bot.database.user_db.increment_balance(self.user_id, -total_bet)
        await self.bot.database.game_db.set_user_game_stats(
            self.user_id, GameEventType.BLACKJACK, False, total_bet
        )

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, row=0)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Hit button."""
        current_hand = self.hands[self.current_hand]

        if self.split_aces and len(self.hands) > 1:
            await interaction.response.send_message(
                "You cannot hit after splitting aces!", ephemeral=True
            )
            return

        if len(current_hand) == 2 and calculate_hand_value(current_hand) == 21:
            await interaction.response.send_message(
                "You cannot hit on a natural 21!", ephemeral=True
            )
            return

        self.first_move_done[self.current_hand] = True
        self.hands[self.current_hand].append(draw_card(self.deck))
        player_value = calculate_hand_value(self.hands[self.current_hand])

        if player_value > 21 or player_value == 21:
            self.hand_finished[self.current_hand] = True
            await self.next_hand_or_finish(interaction)
        else:
            await self.update_game(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, row=0)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Stand button."""
        self.first_move_done[self.current_hand] = True
        self.hand_finished[self.current_hand] = True
        await self.next_hand_or_finish(interaction)

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.success, row=1)
    async def double_down(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Double down button."""
        current_balance = await self.bot.database.user_db.get_balance(self.user_id)

        if self.bets[self.current_hand] * 2 > current_balance:
            await interaction.response.send_message(
                f"You don't have enough balance to double down.\nCurrent Balance: ${format_number(current_balance)}\nCurrent Bet: ${format_number(self.bets[self.current_hand])}",
                ephemeral=True,
            )
            return

        if len(self.hands[self.current_hand]) != 2:
            await interaction.response.send_message(
                "You can only double down on your first move.", ephemeral=True
            )
            return

        if self.split_aces and len(self.hands) > 1:
            await interaction.response.send_message(
                "You cannot double down after splitting aces!", ephemeral=True
            )
            return

        self.bets[self.current_hand] *= 2
        self.hands[self.current_hand].append(draw_card(self.deck))
        self.hand_finished[self.current_hand] = True

        await self.next_hand_or_finish(interaction)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.blurple, row=1)
    async def split(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Split button."""
        current_balance = await self.bot.database.user_db.get_balance(self.user_id)

        if not can_split(self.hands[self.current_hand]):
            await interaction.response.send_message(
                "You can only split pairs!", ephemeral=True
            )
            return

        if len(self.hands[self.current_hand]) != 2:
            await interaction.response.send_message(
                "You can only split on your first move.", ephemeral=True
            )
            return

        if len(self.hands) >= 4:
            await interaction.response.send_message(
                "You can only split up to 4 hands!", ephemeral=True
            )
            return

        if self.bets[self.current_hand] > current_balance:
            await interaction.response.send_message(
                f"You don't have enough balance to split.\nCurrent Balance: ${format_number(current_balance)}\nRequired: ${format_number(self.bets[self.current_hand])}",
                ephemeral=True,
            )
            return

        # Perform split
        original_hand = self.hands[self.current_hand]
        card1, card2 = original_hand[0], original_hand[1]

        self.hands[self.current_hand] = [card1, draw_card(self.deck)]
        new_hand = [card2, draw_card(self.deck)]

        self.hands.insert(self.current_hand + 1, new_hand)
        self.bets.insert(self.current_hand + 1, self.bets[self.current_hand])
        self.first_move_done.insert(self.current_hand + 1, False)
        self.hand_finished.insert(self.current_hand + 1, False)

        if card1 == "A":
            self.split_aces = True
            self.hand_finished[self.current_hand] = True
            self.hand_finished[self.current_hand + 1] = True
        else:
            if calculate_hand_value(self.hands[self.current_hand]) == 21:
                self.hand_finished[self.current_hand] = True
            if calculate_hand_value(new_hand) == 21:
                self.hand_finished[self.current_hand + 1] = True

        await self.update_game(interaction)

    @discord.ui.button(label="Fold", style=discord.ButtonStyle.danger, row=2)
    async def fold(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Fold button - lose half of current hand bet."""
        half_loss = self.bets[self.current_hand] // 2
        current_balance = await self.bot.database.user_db.get_balance(self.user_id)

        self.stats["blackjacks_played"] += 1
        self.stats["blackjacks_lost"] += 1

        hands_info = [
            (self.hands[self.current_hand], -half_loss, "Folded - Lost half bet")
        ]
        embed = create_result_embed(
            discord.Color.orange(),
            hands_info,
            self.dealer_hand,
            -half_loss,
            current_balance,
            self.stats,
            display_bet=self.original_bet,
        )

        await self.bot.database.user_db.increment_balance(self.user_id, -half_loss)
        await self.bot.database.game_db.set_user_game_stats(
            self.user_id, GameEventType.BLACKJACK, False, half_loss
        )

        await interaction.response.edit_message(embed=embed, view=None)
        self.bot.active_blackjack_players.discard(self.user_id)
        self.stop()

    async def next_hand_or_finish(self, interaction):
        """Move to next hand or finish game."""
        if self.split_aces and len(self.hands) > 1:
            for i in range(len(self.hands)):
                self.hand_finished[i] = True

        if (
            self.current_hand < len(self.hands)
            and calculate_hand_value(self.hands[self.current_hand]) == 21
            and len(self.hands[self.current_hand]) == 2
        ):
            self.hand_finished[self.current_hand] = True

        # Find next unfinished hand
        next_hand = None
        for i in range(self.current_hand + 1, len(self.hands)):
            if not self.hand_finished[i]:
                next_hand = i
                break

        if next_hand is not None:
            self.current_hand = next_hand
            await self.update_game(interaction)
        else:
            await self.end_game(interaction)

    async def update_game(self, interaction):
        """Update game display."""
        embed = discord.Embed(title="Blackjack", color=discord.Color.blue())

        for i, hand in enumerate(self.hands):
            status = ""
            if i == self.current_hand and not self.hand_finished[i]:
                status = " ← Playing"
            elif self.hand_finished[i]:
                status = " ✓ Finished"

            hand_name = f"Hand {i+1}" if len(self.hands) > 1 else "Your hand"
            embed.add_field(
                name=f"{hand_name} ({calculate_hand_value(hand)}){status}",
                value=f"{format_hand(hand)}\nBet: ${format_number(self.bets[i])}",
                inline=True,
            )

        embed.add_field(
            name=f"Dealer shows ({calculate_hand_value([self.dealer_hand[0]])})",
            value=f"{EMOJI_MAP.get(self.dealer_hand[0])} ❓",
            inline=False,
        )

        self.update_button_states()
        await interaction.response.edit_message(embed=embed, view=self)

    def update_button_states(self):
        """Enable/disable buttons based on game state."""
        current_hand = (
            self.hands[self.current_hand] if self.current_hand < len(self.hands) else []
        )

        # Disable all if current hand finished
        if (
            self.current_hand >= len(self.hands)
            or self.hand_finished[self.current_hand]
        ):
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            return

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "Split":
                    child.disabled = (
                        not can_split(current_hand)
                        or len(current_hand) != 2
                        or len(self.hands) >= 4
                        or self.split_aces
                    )
                elif child.label == "Double Down":
                    child.disabled = (
                        len(current_hand) != 2
                        or (self.split_aces and len(self.hands) > 1)
                        or calculate_hand_value(current_hand) == 21
                    )
                elif child.label == "Fold":
                    child.disabled = self.first_move_done[self.current_hand]
                elif child.label == "Hit":
                    child.disabled = (self.split_aces and len(self.hands) > 1) or (
                        len(current_hand) == 2
                        and calculate_hand_value(current_hand) == 21
                    )
                elif child.label == "Stand":
                    child.disabled = False

    async def end_game(self, interaction):
        """Calculate final outcome and end game."""
        current_balance = await self.bot.database.user_db.get_balance(self.user_id)
        prev_balance = current_balance

        # Play out dealer's hand
        dealer_value = calculate_hand_value(self.dealer_hand)
        while dealer_value < 17 or is_soft_17(self.dealer_hand):
            self.dealer_hand.append(draw_card(self.deck))
            dealer_value = calculate_hand_value(self.dealer_hand)

        # Calculate outcomes for each hand
        hands_info = []
        total_outcome = 0
        overall_won = 0
        overall_lost = 0

        for i, hand in enumerate(self.hands):
            player_value = calculate_hand_value(hand)
            bet = self.bets[i]

            if player_value > 21:
                result_text = "Busted! 💥"
                outcome = -bet
                overall_lost += 1
            elif dealer_value > 21 or player_value > dealer_value:
                if is_blackjack(hand):
                    result_text = "Blackjack! 🎉 Won"
                    outcome = int(bet * 1.5)
                else:
                    result_text = "Won! 🎉"
                    outcome = bet
                overall_won += 1
            elif player_value < dealer_value:
                result_text = "Lost 😞"
                outcome = -bet
                overall_lost += 1
            else:  # Push
                if is_blackjack(hand) and is_blackjack(self.dealer_hand):
                    result_text = "Push - Both Blackjack! 🤝"
                else:
                    result_text = "Push 🤝"
                outcome = 0

            hands_info.append((hand, outcome, result_text))
            total_outcome += outcome

        # Determine overall outcome
        if total_outcome > 0:
            color = discord.Color.green()
            won, lost = True, False
        elif total_outcome < 0:
            color = discord.Color.red()
            won, lost = False, True
        else:
            color = discord.Color.gold()
            won, lost = False, False

        # Update stats
        self.stats["blackjacks_played"] += 1
        self.stats["blackjacks_won"] += 1 if won else 0
        self.stats["blackjacks_lost"] += 1 if lost else 0

        win_value = True if won else False if lost else None

        embed = create_result_embed(
            color,
            hands_info,
            self.dealer_hand,
            total_outcome,
            prev_balance,
            self.stats,
            display_bet=self.original_bet,
        )

        await interaction.response.edit_message(embed=embed, view=None)
        await self.bot.database.user_db.increment_balance(self.user_id, total_outcome)
        await self.bot.database.game_db.set_user_game_stats(
            self.user_id, GameEventType.BLACKJACK, win_value, abs(total_outcome)
        )
        self.bot.active_blackjack_players.discard(self.user_id)
        self.stop()


async def setup(bot):
    await bot.add_cog(Blackjack(bot))
