import os

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_or_mod_check


class GameInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def game_title_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete matching game titles."""
        games = await self.bot.database.steam_games_db.get_all_games()
        return [
            app_commands.Choice(name=game["title"], value=game["title"])
            for game in games
            if current.lower() in game["title"].lower()
        ][
            :25
        ]  # Discord's max autocomplete limit

    @app_commands.command(name="game-info", description="Get details about a game")
    @app_commands.describe(title="The title of the game")
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.autocomplete(title=game_title_autocomplete)
    async def game_info(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer(thinking=True)

        game = await self.bot.database.steam_games_db.get_game_by_title(title)
        if not game:
            await interaction.followup.send(
                f"❌ No game found with the title: `{title}`"
            )
            return

        GAMES = os.getenv("GAMES")

        embed = discord.Embed(
            title=f"{game['title']}",
            color=0x00AEFF,
            url=game["steam_link"],
            description=(
                f"[Build {game['build']}](https://steamdb.info/app/{game['app_id']}/patchnotes/)"
                if game.get("build")
                else ""
            ),
        )
        embed.add_field(
            name="Direct Download Link",
            value=f"[Click Here]({game['download_link']})",
            inline=False,
        )
        embed.add_field(
            name="Steam Link", value=f"[Click Here]({game['steam_link']})", inline=False
        )

        if GAMES:
            embed.add_field(
                name="Full Games List", value=f"[Click Here]({GAMES})", inline=False
            )

        embed.add_field(
            name="Description", value=f"```{game['description']}```", inline=False
        )
        embed.add_field(name="Notes", value=f"```{game['notes']}```", inline=False)
        embed.add_field(name="Price", value=game["price"], inline=True)
        embed.add_field(name="Reviews", value=game["reviews"], inline=True)
        embed.add_field(name="App Id", value=game["app_id"], inline=True)
        embed.add_field(name="Genres", value=game["genres"], inline=False)
        embed.set_image(url=game["image"])
        embed.set_footer(text=f"{game['added_by_name']} • Added", icon_url=None)

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(GameInfo(bot))
