import discord
import random
from discord import app_commands
from discord.ext import commands
from typing import Optional
from constants.game_config import GameEventType
from collections import defaultdict
from utils.formatting import format_number


def calculate_percentage_amount(balance: int, action: Optional[str]) -> Optional[int]:
    if action == "all":
        return balance
    elif action == "half":
        return balance // 2
    elif action == "25%":
        return balance // 4
    return None


def validate_amount(amount: Optional[int], balance: int) -> Optional[str]:
    if amount is None or amount <= 0:
        return "Invalid amount"
    if amount > balance:
        return f"You don't have enough balance to play blackjack. Current balance is ${format_number(balance)}."
    return None


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
    ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    deck = ranks * 24
    random.shuffle(deck)
    return deck


def draw_card(deck):
    if not deck:
        deck.extend(create_deck())
    return deck.pop()


def format_hand(hand):
    return " ".join(EMOJI_MAP.get(card, card) for card in hand)


def calculate_hand_value(hand):
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


def update_stats(stats, won, lost):
    stats["blackjacks_played"] += 1
    if won:
        stats["blackjacks_won"] += 1
    elif lost:
        stats["blackjacks_lost"] += 1


def is_soft_17(hand):
    return (
        calculate_hand_value(hand) == 17
        and "A" in hand
        and sum(1 for card in hand if card == "A") > 0
    )


def create_result_embed(
    player_hand, dealer_hand, outcome, prev_balance, result_text, stats, display_bet
):
    embed = discord.Embed(
        title="Blackjack Results",
        description=f"Bet Amount: ${format_number(display_bet)}",
        color=discord.Color.green(),
    )
    embed.add_field(
        name=f"Your final hand ({calculate_hand_value(player_hand)})",
        value=format_hand(player_hand),
        inline=False,
    )
    embed.add_field(
        name=f"Dealer's hand ({calculate_hand_value(dealer_hand)})",
        value=format_hand(dealer_hand),
        inline=False,
    )
    embed.add_field(
        name="Prev Balance", value=f"${format_number(prev_balance)}", inline=True
    )
    embed.add_field(
        name="Current Balance",
        value=f"${format_number(prev_balance + outcome)}",
        inline=True,
    )
    embed.add_field(
        name="Result",
        value=f"{result_text} ${format_number(abs(outcome))}",
        inline=True,
    )
    embed.set_footer(
        text=f"Blackjacks Won: {stats['blackjacks_won']} | "
        f"Blackjacks Lost: {stats['blackjacks_lost']} | "
        f"Blackjacks Tied: {stats['blackjacks_played'] - stats['blackjacks_won'] - stats['blackjacks_lost']} | "
        f"Blackjacks Played: {stats['blackjacks_played']}",
    )
    return embed


class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blackjack", description="Play a game of blackjack")
    @app_commands.describe(
        amount="The amount to bet", action="Choose a percentage of your balance"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Half", value="half"),
            app_commands.Choice(name="25%", value="25%"),
        ]
    )
    async def blackjack(
        self,
        interaction: discord.Interaction,
        amount: Optional[app_commands.Range[int, 1, None]] = None,
        action: Optional[app_commands.Choice[str]] = None,
    ) -> None:

        user_id = interaction.user.id

        if user_id in self.bot.active_blackjack_players:
            await interaction.response.send_message(
                "You are already in a Blackjack game!", ephemeral=True
            )
            return

        await interaction.response.defer()
        balance = await self.bot.database.user_db.get_balance(user_id)

        if amount and action:
            await interaction.edit_original_response(
                content="You can only choose one option: amount or action."
            )
            return

        if action and not amount:
            amount = calculate_percentage_amount(balance, action.value)

        error = validate_amount(amount, balance)
        if error:
            await interaction.edit_original_response(content=error)
            return

        # Add the user to the active games set
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
    def __init__(self, bot, user_id, deck, player_hand, dealer_hand, amount, stats):
        super().__init__(timeout=180)
        self.bot = bot
        self.user_id = user_id
        self.deck = deck
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.original_amount = amount
        self.amount = amount
        self.interaction = None
        self.standing = False
        self.stats = stats
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your game!", ephemeral=True
            )
            return False
        self.interaction = interaction
        return True

    async def on_timeout(self):
        self.bot.active_blackjack_players.discard(self.user_id)
        current_balance = await self.bot.database.user_db.get_balance(self.user_id)
        if self.interaction:
            await self.interaction.edit_original_response(
                content=f"⏰ Game timed out due to inactivity. You lost your bet of ${format_number(self.amount)}.",
                view=None,
            )
        elif self.message:
            await self.message.edit(
                content=f"⏰ Game timed out due to inactivity. You lost your bet of ${format_number(self.amount)}.",
                embed=None,
                view=None,
            )

        # Apply consequences (loss of bet and update stats)
        # await self.bot.database.user_db.set_balance(
        #     self.user_id, current_balance - self.amount
        # )
        await self.bot.database.user_db.increment_balance(self.user_id, -self.amount)
        await self.bot.database.game_db.set_user_game_stats(
            self.user_id, GameEventType.BLACKJACK, False, self.amount
        )

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player_hand.append(draw_card(self.deck))
        player_value = calculate_hand_value(self.player_hand)

        if player_value > 21:
            await self.end_game(interaction)
        else:
            await self.update_game(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.standing = True
        await self.end_game(interaction)

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.success)
    async def double_down(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        current_balance = await self.bot.database.user_db.get_balance(self.user_id)

        if self.amount * 2 > current_balance:
            await interaction.response.send_message(
                f"You don't have enough balance to double down.\nCurrent Balance: ${format_number(current_balance)}\nCurrent Bet: ${format_number(self.amount)}",
                ephemeral=True,
            )
            return

        if len(self.player_hand) != 2:
            await interaction.response.send_message(
                "You can only double down on your first move.", ephemeral=True
            )
            return

        self.amount *= 2
        self.player_hand.append(draw_card(self.deck))

        await self.end_game(interaction)

    async def update_game(self, interaction):
        embed = discord.Embed(title="Blackjack", color=discord.Color.blue())
        embed.add_field(
            name=f"Your hand {calculate_hand_value(self.player_hand)}",
            value=format_hand(self.player_hand),
        )
        embed.add_field(
            name=f"Dealer shows {calculate_hand_value(self.dealer_hand[0])}",
            value=f"{EMOJI_MAP.get(self.dealer_hand[0])} ❓",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def end_game(self, interaction):
        current_balance = await self.bot.database.user_db.get_balance(self.user_id)
        player_value = calculate_hand_value(self.player_hand)
        dealer_value = calculate_hand_value(self.dealer_hand)
        prev_balance = current_balance
        busted = False
        if player_value > 21:
            busted = True
        while not busted and (dealer_value < 17 or is_soft_17(self.dealer_hand)):
            self.dealer_hand.append(draw_card(self.deck))
            dealer_value = calculate_hand_value(self.dealer_hand)

        # Determine outcome
        if busted or player_value > 21:
            result_text = "You busted! 💥 Dealer wins"
            won, lost = False, True
            outcome = -self.amount
        elif dealer_value > 21 or player_value > dealer_value:
            result_text = "🎉You win"
            won, lost = True, False
            outcome = self.amount
        elif player_value < dealer_value:
            result_text = "😞 Dealer wins"
            won, lost = False, True
            outcome = -self.amount
        else:
            result_text = "🤝It's a tie"
            won, lost = False, False
            outcome = 0

        update_stats(self.stats, won, lost)
        win_value = True if won else False if lost else None
        embed = create_result_embed(
            self.player_hand,
            self.dealer_hand,
            outcome,
            prev_balance,
            result_text,
            self.stats,
            display_bet=self.original_amount,
        )

        await interaction.response.edit_message(embed=embed, view=None)
        # await self.bot.database.user_db.set_balance(
        #     self.user_id, current_balance + outcome
        # )
        await self.bot.database.user_db.increment_balance(self.user_id, outcome)
        await self.bot.database.game_db.set_user_game_stats(
            self.user_id, GameEventType.BLACKJACK, win_value, abs(outcome)
        )
        self.bot.active_blackjack_players.discard(self.user_id)
        self.stop()


async def perform_blackjack(bot, interaction, user_id, amount, action, balance):
    stats_raw = await bot.database.game_db.get_user_game_stats(user_id)
    stats = defaultdict(int, stats_raw.get("game_stats", {}))
    prev_balance = balance

    deck = create_deck()
    player_hand = [draw_card(deck), draw_card(deck)]
    dealer_hand = [draw_card(deck), draw_card(deck)]

    player_value = calculate_hand_value(player_hand)
    dealer_value = calculate_hand_value(dealer_hand)

    if player_value == 21:
        if dealer_value == 21:
            won, lost = False, False
            result = "Push! Both you and the dealer have blackjack. 🤝"
            outcome = 0
        else:
            result = "Blackjack! You win with a natural 21! 🎉 You win"
            outcome = int(amount * 1.5)
            won, lost = True, False
        update_stats(stats, won, lost)
        win_value = True if won else False if lost else None
        embed = discord.Embed(
            title="Blackjack",
            description=f"Bet Amount ${format_number(amount)}",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Your hand (Blackjack)", value=format_hand(player_hand), inline=False
        )
        embed.add_field(
            name="Dealer's hand", value=format_hand(dealer_hand), inline=False
        )
        embed.add_field(
            name="Prev Balance", value=f"${format_number(prev_balance)}", inline=False
        )
        embed.add_field(
            name="Current Balance",
            value=f"${format_number(prev_balance + outcome)}",
            inline=False,
        )
        embed.add_field(
            name="Result",
            value=f"{result} ${format_number(abs(outcome))}",
            inline=False,
        )
        embed.set_footer(
            text=f"Blackjacks Won: {stats['blackjacks_won']} | "
            f"Blackjacks Lost: {stats['blackjacks_lost']} | "
            f"Blackjacks Tied: {stats['blackjacks_played'] - stats['blackjacks_won'] - stats['blackjacks_lost']} | "
            f"Blackjacks Played: {stats['blackjacks_played']}"
        )
        await interaction.edit_original_response(embed=embed, view=None)
        # await bot.database.user_db.set_balance(user_id, balance + outcome)
        await bot.database.user_db.increment_balance(user_id, outcome)
        await bot.database.game_db.set_user_game_stats(
            user_id,
            GameEventType.BLACKJACK,
            win_value,
            outcome,
        )
        bot.active_blackjack_players.discard(user_id)
        return

    embed = discord.Embed(
        title="Blackjack",
        description=f"Bet Amount: ${format_number(amount)}",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name=f"Your hand {player_value}",
        value=f"{format_hand(player_hand)}",
    )
    embed.add_field(
        name=f"Dealer shows {calculate_hand_value([dealer_hand[0]])}",
        value=f"{EMOJI_MAP.get(dealer_hand[0])} ❓",
        inline=False,
    )

    view = BlackjackView(bot, user_id, deck, player_hand, dealer_hand, amount, stats)
    message = await interaction.edit_original_response(embed=embed, view=view)
    view.message = message  # Store message reference in the view


async def setup(bot):
    await bot.add_cog(Blackjack(bot))
