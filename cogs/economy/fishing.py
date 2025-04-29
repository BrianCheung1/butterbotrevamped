import discord
import random
from discord import app_commands
from discord.ext import commands
from constants.economy_config import MINING_RARITY_TIERS


class Fishing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Precompute the total weight and rarity tier information when the cog is initialized.
        self.rarities = list(MINING_RARITY_TIERS.items())

    @app_commands.command(name="fish", description="fish for money")
    async def fish(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Weighted Random Selection of Rarity using random.choices
        rarities, weights = zip(
            *[(rarity, info["weight"]) for rarity, info in self.rarities]
        )
        selected_rarity = random.choices(rarities, weights, k=1)[
            0
        ]  # Select a rarity based on weight

        # Randomly pick an item from the selected rarity tier
        rarity_info = MINING_RARITY_TIERS[selected_rarity]
        fished_item = random.choice(rarity_info["items"])

        # Randomly determine the value of the fished item within the value range
        value = random.randint(
            rarity_info["value_range"][0], rarity_info["value_range"][1]
        )

        # Update user's work stats (total fished value and items fished)
        await self.bot.database.set_work_stats(interaction.user.id, value, "fishing")
        balance = await self.bot.database.get_balance(interaction.user.id)
        await self.bot.database.set_balance(interaction.user.id, balance + value)

        # Send the result to the user
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Fishing Results",
            description=f"You fished a **{fished_item}** worth **{value}** coins!\nCurrent balance: **{balance + value}** coins.",
            color=discord.Color.green(),
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Fishing(bot))
