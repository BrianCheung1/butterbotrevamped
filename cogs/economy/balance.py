import discord
from discord import app_commands
from discord.ext import commands
from utils.formatting import format_number


class Balance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_owner_check(interaction: discord.Interaction) -> bool:
        return (
            interaction.user.id == interaction.client.owner_id
            or interaction.user.id == 1047615361886982235
        )

    @app_commands.command(
        name="balance", description="Check your balance or someone else's."
    )
    @app_commands.describe(user="The user to check the balance of.")
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
        name="setbalance", description="Set a user's balance. (Admin only)"
    )
    @app_commands.check(is_owner_check)
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
