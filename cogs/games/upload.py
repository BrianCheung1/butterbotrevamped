import os
import re
from datetime import datetime, timezone
from typing import Optional

import discord
import requests
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from utils.channels import broadcast_embed_to_guilds
from utils.checks import is_owner_or_mod_check

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))
GAMES = os.getenv("GAMES")
REQUEST_FORM_LINK = "https://forms.gle/d1K2NBLfJBqoSsv59"


def extract_app_id(steam_link: str) -> str:
    match = re.search(r"store\.steampowered\.com/app/(\d+)", steam_link)
    if match:
        return match.group(1)
    raise ValueError("Invalid Steam link: Could not extract AppID")


def fetch_steam_app_details(app_id: str) -> dict:
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get(app_id, {}).get("success"):
        return data[app_id]["data"]
    else:
        raise ValueError(f"Steam API: No data for AppID {app_id}")


def fetch_steam_review_summary(app_id: str) -> str:
    url = f"https://store.steampowered.com/appreviews/{app_id}?json=1"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    if data.get("success") == 1:
        desc = data.get("query_summary", {}).get("review_score_desc")
        total = data.get("query_summary", {}).get("total_reviews")
        if desc and total:
            return f"{desc} ({total:,})"
    return "N/A"


class Upload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add-game", description="Add a game to games channel")
    @app_commands.describe(
        add="Adding or Updating a game",
        download_link="The google drive download link",
        steam_link="The steam link to the game",
        build="Build version (optional)",
        notes="Extra notes (optional)",
    )
    @app_commands.choices(
        add=[
            Choice(name="Added", value="Added"),
            Choice(name="Updated", value="Updated"),
        ]
    )
    @app_commands.check(is_owner_or_mod_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def add_game(
        self,
        interaction: discord.Interaction,
        add: Choice[str],
        download_link: str,
        steam_link: str,
        build: Optional[str] = None,
        notes: Optional[str] = "No Notes",
    ):
        try:
            await interaction.response.defer(thinking=True)

            # Extract AppID and fetch Steam data
            app_id = extract_app_id(steam_link)
            steam_data = fetch_steam_app_details(app_id)

            # Extract details
            title = steam_data.get("name", "Unknown Title")
            description = steam_data.get(
                "short_description", "No description available."
            )
            image = steam_data.get("header_image", "")

            # Price info
            price_overview = steam_data.get("price_overview")
            if price_overview:
                initial = price_overview["initial"] / 100  # Prices are in cents
                final = price_overview["final"] / 100

                if price_overview["discount_percent"] > 0:
                    price = f"~~${initial:.2f}~~\n${final:.2f}"
                else:
                    price = f"${final:.2f}"
            else:
                price = "Free" if steam_data.get("is_free") else "N/A"

            # Reviews (JSON API only gives total number)
            reviews = fetch_steam_review_summary(app_id)

            # Genres
            genres = " ".join(
                f"`{g['description']}`" for g in steam_data.get("genres", [])[:5]
            )

            categories = " ".join(
                f"`{c['description']}`" for c in steam_data.get("categories", [])[:5]
            )
            notes = notes.replace(";", "\n") if notes else "No Notes"

            # Save or update in DB
            await self.bot.database.steam_games_db.upsert_game(
                title=title,
                add_type=add.value,
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

            # Build embed
            embed = discord.Embed(
                title=f"{add.value} - {title}",
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
                name="Full Games List", value=f"[Click Here]({GAMES})", inline=False
            )
            embed.add_field(
                name="Steam Link", value=f"[Click Here]({steam_link})", inline=False
            )
            embed.add_field(
                name="Have a request?",
                value=f"[Click Here]({REQUEST_FORM_LINK})",
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
            await interaction.followup.send(
                "❌ Failed to add game. Please check your links and try again.",
                ephemeral=True,
            )
            self.bot.logger.error(f"Add Game Error: {e}", exc_info=True)


async def setup(bot):
    await bot.add_cog(Upload(bot))
