import discord
from discord import app_commands
from utils.base_cog import BaseGameCog
from utils.formatting import format_number


class Give(BaseGameCog):
    def __init__(self, bot):
        super().__init__(bot)

    @app_commands.command(name="give", description="Give another player money")
    @app_commands.describe(amount="The amount to give")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def give(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: app_commands.Range[int, 1, None],
    ):
        user_id = interaction.user.id
        target_id = user.id

        # Check conflicts BEFORE deferring
        if await self.check_blackjack_conflict(user_id, interaction):
            return

        if await self.check_self_transaction(user_id, target_id, interaction):
            return

        if await self.check_bot_target(user, interaction):
            return

        # Defer after quick checks
        await interaction.response.defer()

        # SINGLE balance fetch - reuse everywhere
        balance = await self.get_balance(user_id)

        # Pass balance to avoid redundant fetch
        if not await self.validate_balance(
            user_id, amount, interaction, deferred=True, balance=balance
        ):
            return

        # Update balances
        await self.deduct_balance(user_id, amount)
        await self.add_balance(target_id, amount)

        # Log transaction
        self.log_transaction(user_id, "GIVE", amount, f"Recipient: {target_id}")

        # Response
        await interaction.edit_original_response(
            content=f"✅ You've successfully given ${format_number(amount)} to {user.mention}!"
        )


async def setup(bot):
    await bot.add_cog(Give(bot))
