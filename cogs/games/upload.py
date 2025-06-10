import os
from typing import Optional

import discord
import requests
from bs4 import BeautifulSoup
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class Upload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_owner_check(interaction: discord.Interaction) -> bool:
        return (
            interaction.user.id == interaction.client.owner_id
            or interaction.user.id == 1047615361886982235
        )

    @app_commands.command(name="add_game", description="Add a game to games channel")
    @app_commands.describe(
        add="Adding or Updating a game",
        download_link="The google drive download link",
        steam_link="The steam link to the game",
    )
    @app_commands.choices(
        add=[
            Choice(name="Added", value="Added "),
            Choice(name="Updated", value="Updated"),
        ]
    )
    @app_commands.check(is_owner_check)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def add_game(
        self,
        interaction: discord.Interaction,
        add: str,
        download_link: str,
        steam_link: str,
        build: Optional[str] = None,
        notes: Optional[str] = "No Notes",
    ):
        """Easy embed for games download"""
        try:
            GAMES = os.getenv("GAMES")
            # bs4 to parse through steam link for data
            url = steam_link
            response = requests.get(url, timeout=100)
            soup = BeautifulSoup(response.text, features="html.parser")
            genres = ""
            for index, genre in enumerate(soup.find_all(class_="app_tag")):
                if index >= 5:
                    break
                if genre.contents[0].strip() == "+":
                    continue
                genres += f"`{genre.contents[0].strip()}` "

            title = soup.select_one('div[class="apphub_AppName"]').contents[0]
            description = soup.find("meta", property="og:description")["content"]
            image = soup.find("meta", property="og:image")["content"]
            if soup.select_one('div[class="discount_original_price"]'):
                original_price = soup.select_one(
                    'div[class="discount_original_price"]'
                ).contents[0]
                discounted_price = soup.select_one(
                    'div[class="discount_final_price"]'
                ).contents[0]
                price = f"~~{original_price}~~\n{discounted_price}"
            else:
                if soup.select_one('div[class="game_purchase_price price"]'):
                    price = soup.select_one(
                        'div[class="game_purchase_price price"]'
                    ).contents[0]
                else:
                    price = "N/A"
            reviews = soup.find("meta", itemprop="reviewCount")["content"]
            reviews_description = soup.find("span", itemprop="description").contents[0]
            app_id = soup.find("meta", property="og:url")["content"].split("/")[4]
            build_link = f"https://steamdb.info/app/{app_id}/patchnotes/"
            embed = discord.Embed(
                title=f"{add} - {title}",
                color=0x336EFF,
                url=steam_link,
                description=f"[Build {build}]({build_link})" if build else "",
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
            request_link = "https://forms.gle/d1K2NBLfJBqoSsv59"
            embed.add_field(
                name="Have a request?",
                value=f"[Click Here]({request_link})",
                inline=False,
            )
            embed.add_field(
                name="Description", value=f"```{description}```", inline=False
            )
            embed.add_field(name="Notes", value=f"```{notes}```", inline=False)
            embed.add_field(name="Price", value=f"{price}", inline=True)
            embed.add_field(
                name="Reviews", value=f"{reviews_description} ({reviews})", inline=True
            )
            embed.add_field(name="App Id", value=f"{app_id}", inline=True)
            embed.add_field(name="Genres", value=f"{genres}", inline=False)
            embed.set_image(url=image)
            embed.set_footer(
                text=f"{interaction.user}", icon_url=interaction.user.avatar
            )
        except Exception as e:
            print(e)
            return
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Upload(bot))
