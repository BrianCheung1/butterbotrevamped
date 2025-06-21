import os
from typing import Optional

import discord
import requests
from bs4 import BeautifulSoup
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from utils.checks import is_owner_or_mod_check

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))
GAMES = os.getenv("GAMES")
REQUEST_FORM_LINK = "https://forms.gle/d1K2NBLfJBqoSsv59"


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
    @app_commands.checks.has_permissions(moderate_members=True)
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

            response = requests.get(steam_link, timeout=15)
            soup = BeautifulSoup(response.text, features="html.parser")

            genres = " ".join(
                f"`{g.contents[0].strip()}`"
                for i, g in enumerate(soup.find_all(class_="app_tag"))
                if i < 5 and g.contents[0].strip() != "+"
            )

            title = soup.select_one('div[class="apphub_AppName"]').text.strip()
            description = soup.find("meta", property="og:description")["content"]
            image = soup.find("meta", property="og:image")["content"]

            if soup.select_one('div[class="discount_original_price"]'):
                original_price = soup.select_one(
                    'div[class="discount_original_price"]'
                ).text
                discounted_price = soup.select_one(
                    'div[class="discount_final_price"]'
                ).text
                price = f"~~{original_price}~~\n{discounted_price}"
            elif soup.select_one('div[class="game_purchase_price price"]'):
                price = soup.select_one(
                    'div[class="game_purchase_price price"]'
                ).text.strip()
            else:
                price = "N/A"

            reviews = soup.find("meta", itemprop="reviewCount")["content"]
            reviews_description = soup.find("span", itemprop="description").text.strip()
            app_id = soup.find("meta", property="og:url")["content"].split("/")[4]

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
                reviews=f"{reviews_description} ({reviews})",
                app_id=app_id,
                genres=genres,
                added_by_id=str(interaction.user.id),
                added_by_name=str(interaction.user),
            )

            # Send embed
            embed = discord.Embed(
                title=f"{add.value} - {title}",
                color=0x336EFF,
                url=steam_link,
                description=(
                    f"[Build {build}](https://steamdb.info/app/{app_id}/patchnotes/)"
                    if build
                    else ""
                ),
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
            embed.add_field(
                name="Reviews", value=f"{reviews_description} ({reviews})", inline=True
            )
            embed.add_field(name="App Id", value=app_id, inline=True)
            embed.add_field(name="Genres", value=genres, inline=False)
            embed.set_image(url=image)
            embed.set_footer(
                text=str(interaction.user), icon_url=interaction.user.display_avatar
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                "❌ Failed to add game. Please check your links and try again."
            )
            print(f"Add Game Error: {e}")


async def setup(bot):
    await bot.add_cog(Upload(bot))
