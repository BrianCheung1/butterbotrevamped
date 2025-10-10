import os

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_or_mod_check
from utils.valorant_helpers import name_autocomplete, tag_autocomplete

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class ValorantModeration(commands.Cog):
    """Valorant Moderation with essential management features."""

    def __init__(self, bot):
        self.bot = bot
        # Use centralized data manager
        self.data_manager = bot.valorant_data

    @app_commands.command(
        name="valorant-remove", description="Remove a Valorant player from the database"
    )
    @app_commands.describe(name="Player's username", tag="Player's tag")
    @app_commands.autocomplete(name=name_autocomplete, tag=tag_autocomplete)
    @app_commands.guilds(DEV_GUILD_ID)
    @app_commands.check(is_owner_or_mod_check)
    async def valorant_remove(
        self,
        interaction: discord.Interaction,
        name: str,
        tag: str,
    ):
        await interaction.response.defer(thinking=True)

        name = name.strip().lower()
        tag = tag.strip().lower()

        # Delete from database
        deleted = await self.bot.database.players_db.delete_player(name, tag)

        # Remove from in-memory cache
        self.bot.valorant_players.pop((name, tag), None)

        # Invalidate data manager cache
        self.data_manager.invalidate_player_cache(name, tag)

        if deleted:
            await interaction.followup.send(
                f"✅ Removed `{name}#{tag}` from the leaderboard and cleared all cached data."
            )
        else:
            await interaction.followup.send(
                f"⚠️ `{name}#{tag}` was not found in the database."
            )

    @app_commands.command(
        name="valorant-bulk-remove",
        description="Remove multiple players from the leaderboard",
    )
    @app_commands.describe(
        players="Comma-separated list of players (format: name#tag,name#tag)"
    )
    @app_commands.guilds(DEV_GUILD_ID)
    @app_commands.check(is_owner_or_mod_check)
    async def valorant_bulk_remove(
        self,
        interaction: discord.Interaction,
        players: str,
    ):
        """Remove multiple players at once."""
        await interaction.response.defer(thinking=True)

        # Parse player list
        player_list = []
        for player_str in players.split(","):
            player_str = player_str.strip()
            if "#" in player_str:
                parts = player_str.split("#")
                if len(parts) == 2:
                    player_list.append((parts[0].lower(), parts[1].lower()))

        if not player_list:
            return await interaction.followup.send(
                "❌ Invalid format. Use: name#tag,name#tag,...", ephemeral=True
            )

        # Remove each player
        removed = []
        not_found = []

        for name, tag in player_list:
            deleted = await self.bot.database.players_db.delete_player(name, tag)

            if deleted:
                # Remove from cache
                self.bot.valorant_players.pop((name, tag), None)
                self.data_manager.invalidate_player_cache(name, tag)
                removed.append(f"{name}#{tag}")
            else:
                not_found.append(f"{name}#{tag}")

        # Build response
        embed = discord.Embed(
            title="🗑️ Bulk Remove Results", color=discord.Color.orange()
        )

        if removed:
            embed.add_field(
                name=f"✅ Removed ({len(removed)})",
                value="\n".join(removed[:10])
                + (f"\n... and {len(removed) - 10} more" if len(removed) > 10 else ""),
                inline=False,
            )

        if not_found:
            embed.add_field(
                name=f"⚠️ Not Found ({len(not_found)})",
                value="\n".join(not_found[:10])
                + (
                    f"\n... and {len(not_found) - 10} more"
                    if len(not_found) > 10
                    else ""
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantModeration(bot))
