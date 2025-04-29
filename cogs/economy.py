import discord
from discord import app_commands
from discord.ext import commands


class Economy(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="balance", description="Check your balance or someone else's."
    )
    async def balance(
        self, interaction: discord.Interaction, user: discord.User = None
    ) -> None:
        """
        This command checks the balance of a user. If no user is specified, it checks the balance of the command invoker.

        :param interaction: The interaction object from Discord.
        :param user: The user whose balance to check. If None, defaults to the command invoker.
        """
        user = user or interaction.user

        # Get the user's balance (it will be 0 if the user is newly created)
        balance = await self.bot.database.get_balance(user.id)

        embed = discord.Embed(
            title=f"{user.name}'s Balance",
            description=f"💰 {balance} coins",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="setbalance", description="Set a user's balance. (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_balance(
        self, interaction: discord.Interaction, user: discord.User, amount: int
    ) -> None:
        """
        This command sets the balance of a user. Only users with administrator permissions can use this command.

        :param interaction: The interaction object from Discord.
        :param user: The user whose balance to set.
        :param amount: The amount to set the user's balance to.
        """

        if amount < 0:
            await interaction.response.send_message(
                "Amount must be positive.", ephemeral=True
            )
            return

        await self.bot.database.set_balance(user.id, amount)
        await interaction.response.send_message(
            f"✅ Set {user.mention}'s balance to {amount} coins."
        )

    @app_commands.command(
        name="gamestats",
        description="Check your game stats or someone else's.",
    )
    async def game_stats(
        self, interaction: discord.Interaction, user: discord.User = None
    ) -> None:
        """
        This command checks the game stats of a user. If no user is specified, it checks the stats of the command invoker.

        :param interaction: The interaction object from Discord.
        :param user: The user whose game stats to check. If None, defaults to the command invoker.
        """
        user = user or interaction.user

        # Get the user's game stats (it will be empty if the user is newly created)
        stats = await self.bot.database.get_user_game_stats(user.id)

        game_stats = stats["game_stats"]

        # Mapping column names to readable names
        stat_names = [
            ("Gambles Won", game_stats[1]),
            ("Gambles Lost", game_stats[2]),
            ("Gambles Played", game_stats[3]),
            ("Gambles Total Winnings", game_stats[4]),
            ("Gambles Total Losses", game_stats[5]),
            ("Blackjacks Won", game_stats[6]),
            ("Blackjacks Lost", game_stats[7]),
            ("Blackjacks Played", game_stats[8]),
            ("Blackjacks Total Winnings", game_stats[9]),
            ("Blackjacks Total Losses", game_stats[10]),
            ("Slots Won", game_stats[11]),
            ("Slots Lost", game_stats[12]),
            ("Slots Played", game_stats[13]),
            ("Slots Total Winnings", game_stats[14]),
            ("Slots Total Losses", game_stats[15]),
            ("Wordles Won", game_stats[16]),
            ("Wordles Lost", game_stats[17]),
            ("Wordles Played", game_stats[18]),
            ("Roulette Won", game_stats[19]),
            ("Roulette Lost", game_stats[20]),
            ("Roulette Played", game_stats[21]),
            ("Roulette Total Winnings", game_stats[22]),
            ("Roulette Total Losses", game_stats[23]),
            ("Duel Stats (JSON)", game_stats[24]),
        ]

        # Make an embed for a clean look
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Game Stats",
            color=discord.Color.blue(),
        )

        for name, value in stat_names:
            embed.add_field(name=name, value=value, inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(Economy(bot))
