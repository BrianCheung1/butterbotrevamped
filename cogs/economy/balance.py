import os

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_or_mod_check
from utils.formatting import format_number

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class Balance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="balance", description="Check your balance or someone else's."
    )
    @app_commands.describe(user="The user to check the balance of.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def balance(
        self, interaction: discord.Interaction, user: discord.User = None
    ):
        """
        This command checks the balance of a user. If no user is specified, it checks the balance of the command invoker.

        :param interaction: The interaction object from Discord.
        :param user: The user whose balance to check. If None, defaults to the command invoker.
        """
        user = user or interaction.user
        balance = await self.bot.database.user_db.get_balance(user.id)

        embed = discord.Embed(
            title=f"{user.name}'s Balance",
            description=f"💰 ${format_number(balance)}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="set-balance", description="Set a user's balance. (Admin only)"
    )
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
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

        await self.bot.database.user_db.set_balance(user.id, amount)
        await interaction.response.send_message(
            f"✅ Set {user.mention}'s balance to ${format_number(amount)}."
        )


async def setup(bot):
    await bot.add_cog(Balance(bot))
