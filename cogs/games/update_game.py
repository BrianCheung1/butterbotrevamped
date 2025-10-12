import os
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.channels import broadcast_embed_to_guilds
from utils.checks import is_owner_or_mod_check
from utils.steam_helpers import (
    clean_notes,
    extract_app_id,
    fetch_steam_app_details,
    fetch_steam_review_summary,
    game_title_autocomplete,
)

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))
from logger import setup_logger

logger = setup_logger("UpdateGame")


class UpdateGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="steam-update-game", description="Update an existing Steam game"
    )
    @app_commands.describe(
        title="Title of the game to update (exact match)",
        download_link="New or existing download link",
        steam_link="Steam link (optional if unchanged)",
        build="New build version (optional)",
        notes="Updated notes (optional)",
    )
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
    @app_commands.autocomplete(title=game_title_autocomplete)
    async def update_game(
        self,
        interaction: discord.Interaction,
        title: str,
        download_link: str,
        steam_link: Optional[str] = None,
        build: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        try:
            await interaction.response.defer(thinking=True)

            game = await self.bot.database.steam_games_db.get_game_by_title(title)
            if not game:
                await interaction.followup.send(
                    "❌ Game not found in database.", ephemeral=True
                )
                return

            if not steam_link:
                steam_link = game.get("steam_link")
                if not steam_link:
                    await interaction.followup.send(
                        "❌ Existing game has no Steam link stored.", ephemeral=True
                    )
                    return

            app_id = extract_app_id(steam_link)
            steam_data = fetch_steam_app_details(app_id)

            description = steam_data.get(
                "short_description", "No description available."
            )
            image = steam_data.get("header_image", "")

            price_overview = steam_data.get("price_overview")
            if price_overview:
                initial = price_overview["initial"] / 100
                final = price_overview["final"] / 100
                price = (
                    f"~~${initial:.2f}~~\n${final:.2f}"
                    if price_overview["discount_percent"]
                    else f"${final:.2f}"
                )
            else:
                price = "Free" if steam_data.get("is_free") else "N/A"

            reviews = fetch_steam_review_summary(app_id)
            genres = " ".join(
                f"`{g['description']}`" for g in steam_data.get("genres", [])[:5]
            )
            categories = " ".join(
                f"`{c['description']}`" for c in steam_data.get("categories", [])[:5]
            )

            notes = clean_notes(notes) if notes else game.get("notes", "No Notes")

            await self.bot.database.steam_games_db.upsert_game(
                title=title,
                add_type="Updated",
                download_link=download_link,
                steam_link=steam_link,
                description=description,
                image=image,
                build=build,
                notes=notes,
                price=price,
                reviews=reviews,
                app_id=app_id,
                genres=genres,
                categories=categories,
                added_by_id=str(interaction.user.id),
                added_by_name=str(interaction.user),
            )

            embed = discord.Embed(
                title=f"Updated - {title}",
                color=0x336EFF,
                url=steam_link,
                description=(
                    f"[Build {build}](https://steamdb.info/app/{app_id}/patchnotes/)"
                    if build
                    else ""
                ),
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(
                name="Direct Download Link",
                value=f"[Click Here]({download_link})",
                inline=False,
            )
            embed.add_field(
                name="Description", value=f"```{description}```", inline=False
            )
            embed.add_field(name="Notes", value=f"```{notes}```", inline=False)
            embed.add_field(name="Price", value=price, inline=True)
            embed.add_field(name="Reviews", value=reviews, inline=True)
            embed.add_field(name="App Id", value=app_id, inline=True)
            embed.add_field(name="Genres", value=genres, inline=False)
            embed.add_field(name="Categories", value=categories, inline=False)
            embed.set_image(url=image)
            embed.set_footer(
                text=str(interaction.user), icon_url=interaction.user.display_avatar.url
            )

            await interaction.followup.send(embed=embed)
            await broadcast_embed_to_guilds(self.bot, "steam_games_channel_id", embed)

        except Exception as e:
            await interaction.followup.send("❌ Failed to update game.", ephemeral=True)
            logger.error(f"Update Game Error: {e}", exc_info=True)


async def setup(bot):
    await bot.add_cog(UpdateGame(bot))
