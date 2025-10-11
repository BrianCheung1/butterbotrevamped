import asyncio
import random

import discord
from discord import app_commands
from utils.balance_helper import validate_amount
from utils.base_cog import BaseGameCog


class Heist(BaseGameCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.active_heist_creators = set()
        self.active_heist_users = set()

    @app_commands.command(name="heist", description="Join a heist to rob the bank!")
    async def heist(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        if await self.check_blackjack_conflict(user_id, interaction):
            return

        if user_id in self.active_heist_users:
            await interaction.response.send_message(
                "❌ You're already in a heist!", ephemeral=True
            )
            return

        if user_id in self.active_heist_creators:
            await interaction.response.send_message(
                "❌ You already started a heist. Wait for it to finish before starting another one!",
                ephemeral=True,
            )
            return

        self.active_heist_creators.add(user_id)
        view = HeistButtonView(self.bot, interaction, self.active_heist_creators)
        await interaction.response.send_message(
            "💣 A heist is being planned! Click below to join...",
            view=view,
        )

        followup_message = await interaction.original_response()
        view.message = followup_message
        asyncio.create_task(self.start_countdown(view, followup_message, user_id))

    async def start_countdown(self, view, followup_message, user_id):
        key_moments = [60, 30, 10, 5, 4, 3, 2, 1]
        for remaining in range(60, 0, -1):
            if remaining in key_moments:
                try:
                    await followup_message.edit(
                        content=f"💣 A heist is being planned!\n⏳ Starting in **{remaining}** seconds!"
                    )
                except Exception as e:
                    print(f"[Countdown Edit Error] {e}")
            await asyncio.sleep(1)

        for button in view.children:
            button.disabled = True

        try:
            await followup_message.edit(
                content="💣 A heist is being planned!\n💥 The heist has started! Time's up, no more joining!",
                view=view,
            )
        except Exception as e:
            print(f"[Final Edit Error] {e}")

        await view.on_finish()
        self.active_heist_creators.discard(user_id)


class HeistButtonView(discord.ui.View):
    def __init__(
        self, bot, interaction: discord.Interaction, active_heist_sessions: set[int]
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.interaction = interaction
        self.participants = []
        self.participant_bets = {}
        self.active_heist_sessions = active_heist_sessions
        self.message = None

    def get_dynamic_win_chance(self):
        num = len(self.participants)
        return min(0.35 + 0.05 * (num - 1), 0.55)

    @discord.ui.button(label="💰 Join Heist", style=discord.ButtonStyle.green)
    async def join_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user = interaction.user
        if user.id in self.participant_bets:
            await interaction.response.send_message(
                "❌ You already joined the heist!", ephemeral=True
            )
            return
        await interaction.response.send_modal(HeistBetModal(self.bot, self, user))

    async def on_finish(self):
        if not self.participants:
            return

        win_chance = self.get_dynamic_win_chance()

        win_messages = [
            "escaped the cops with a fat stack!",
            "made it out with the loot and lived to tell the tale!",
            "ran off with the cash and never looked back!",
        ]
        lose_messages = [
            "was caught by the guards trying to make a quick getaway!",
            "fumbled the bag and got busted!",
            "tripped the alarm and got caught red-handed!",
            "was too slow and got arrested by the cops!",
        ]

        winner_mentions = []
        loser_mentions = []
        for user_id in self.participants:
            bet = self.participant_bets[user_id]
            if random.random() <= win_chance:
                cog = self.bot.cogs.get("Heist")
                await cog.add_balance(user_id, bet * 2)
                winner_mentions.append(
                    f"<@{user_id}> {random.choice(win_messages)} with **${bet * 2:,}**!"
                )
                await self.bot.database.heist_db.set_user_heist_stats(
                    user_id, win=True, amount=bet
                )
            else:
                loser_mentions.append(
                    f"<@{user_id}> {random.choice(lose_messages)} and lost **${bet:,}**."
                )
                await self.bot.database.heist_db.set_user_heist_stats(
                    user_id, win=False, amount=bet
                )

        result_message = "💥 The heist is over!\n"
        if winner_mentions:
            result_message += f"🏆 Winners: {', '.join(winner_mentions)}\n"
        if loser_mentions:
            result_message += f"💀 Caught: {', '.join(loser_mentions)}\n"
        if not winner_mentions:
            result_message += "Nobody made it out alive..."

        try:
            await self.message.channel.send(result_message)
        except Exception as e:
            print(f"[Result Message Error] {e}")

        heist_cog = self.bot.cogs.get("Heist")
        if heist_cog:
            for user_id in self.participants:
                heist_cog.active_heist_users.discard(user_id)

        self.participants.clear()
        self.participant_bets.clear()


class HeistBetModal(discord.ui.Modal, title="Enter Your Heist Bet"):
    def __init__(self, bot, view: HeistButtonView, user: discord.User):
        super().__init__()
        self.bot = bot
        self.view = view
        self.user = user

        self.bet_input = discord.ui.TextInput(
            label="Bet Amount",
            placeholder="Enter your bet (e.g., 500)",
            required=True,
            max_length=10,
        )
        self.add_item(self.bet_input)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = self.user.id

        if all(button.disabled for button in self.view.children):
            await interaction.response.send_message(
                "❌ The heist has already started! You can't join now.", ephemeral=True
            )
            return

        if not self.bet_input.value.isdigit():
            await interaction.response.send_message(
                "❌ Invalid bet amount.", ephemeral=True
            )
            return

        bet = int(self.bet_input.value)
        if bet <= 0:
            await interaction.response.send_message(
                "❌ Bet must be more than 0.", ephemeral=True
            )
            return
        cog = self.bot.cogs.get("Heist")
        balance = await cog.get_balance(user_id)
        error = validate_amount(bet, balance)
        if error:
            await interaction.response.send_message(
                f"❌ Not enough balance. {error}", ephemeral=True
            )
            return

        await cog.deduct_balance(user_id, bet)
        self.view.participants.append(user_id)
        self.view.participant_bets[user_id] = bet
        self.bot.cogs["Heist"].active_heist_users.add(user_id)

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} joined the heist with **${bet:,}**!",
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            f"❌ Something went wrong. {error}", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Heist(bot))
