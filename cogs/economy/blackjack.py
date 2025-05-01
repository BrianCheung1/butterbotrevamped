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
        return "Invalid roll amount."
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
    deck = ranks * 4
    random.shuffle(deck)
    return deck


def draw_card(deck):
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
        await interaction.response.defer()

        user_id = interaction.user.id
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

        await perform_blackjack(
            self.bot,
            interaction,
            user_id,
            amount,
            action.value if action else None,
        )


async def perform_blackjack(bot, interaction, user_id, amount, action):
    stats_raw = await bot.database.game_db.get_user_game_stats(user_id)
    stats = defaultdict(int, stats_raw.get("game_stats", {}))

    deck = create_deck()
    player_hand = [draw_card(deck), draw_card(deck)]
    dealer_hand = [draw_card(deck), draw_card(deck)]

    embed = discord.Embed(
        title="Blackjack",
        description="Welcome to Blackjack!",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name=f"Your hand {calculate_hand_value(player_hand)}",
        value=f"{format_hand(player_hand)}",
    )
    embed.add_field(
        name=f"Dealer shows {calculate_hand_value(dealer_hand[0])}",
        value=f"{EMOJI_MAP.get(dealer_hand[0])} ❓",
        inline=False,
    )

    await interaction.edit_original_response(
        embed=embed,
    )


async def setup(bot):
    await bot.add_cog(Blackjack(bot))
