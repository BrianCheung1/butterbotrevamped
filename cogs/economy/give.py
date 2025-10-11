import discord
from discord import app_commands
from utils.base_cog import BaseGameCog


class Give(BaseGameCog):
    def __init__(self, bot):
        super().__init__(bot)

    @app_commands.command(name="give", description="Give another player money")
    @app_commands.describe(amount="The amount to give")
    async def give(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        amount: app_commands.Range[int, 1, None],
    ):
        await interaction.response.defer()
        user_id = interaction.user.id
        target_id = user.id

        if await self.check_blackjack_conflict(user_id, interaction):
            return

        if await self.check_self_transaction(user_id, target_id, interaction):
            await interaction.edit_original_response(
                content="You can't give money to yourself!"
            )
            return

        if await self.check_bot_target(user, interaction):
            await interaction.edit_original_response(
                content="You can't give money to bots!"
            )
            return

        if not await self.validate_balance(user_id, amount, interaction, deferred=True):
            return

        await self.deduct_balance(user_id, amount)
        await self.add_balance(target_id, amount)

        self.log_transaction(user_id, "GIVE", amount, f"Recipient: {target_id}")

        await interaction.edit_original_response(
            content=f"✅ You've successfully given ${amount:,} to {user.mention}!"
        )


async def setup(bot):
    await bot.add_cog(Give(bot))
