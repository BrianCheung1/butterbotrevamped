import asyncio
import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from imdb import Cinemagoer
from logger import setup_logger

logger = setup_logger("Movies")

ia = Cinemagoer()

OMDB_API_KEY = os.getenv("OMDBAPI_KEY")
OMDB_URL = "http://www.omdbapi.com/"


class Movies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = {}
        self.guilds = {}

    async def cog_load(self):
        await self.load_cached_movies()

    async def load_cached_movies(self):
        """Load movies when cog is loaded"""
        movies = await self.bot.database.movies_db.get_all_movies()
        for movie in movies:
            guild_id = movie["guild_id"]
            if guild_id not in self.guilds:
                self.guilds[guild_id] = {}
        self.guilds[guild_id][movie["title"]] = movie
        logger.info(f"Cached {len(movies)} movies across {len(self.guilds)} guilds")

    @app_commands.command(name="movie-add", description="Search for a movie by title.")
    async def add_movie(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer(thinking=True)

        search_results = ia.search_movie(title)
        if not search_results:
            await interaction.followup.send("❌ No results found.")
            return

        # Fetch full movie details asynchronously for top 5 results
        async def fetch_movie(movie_id):
            return await asyncio.to_thread(ia.get_movie, movie_id)

        movies = await asyncio.gather(
            *(fetch_movie(m.movieID) for m in search_results[:5]),
            return_exceptions=True,
        )
        movies = [m for m in movies if not isinstance(m, Exception)]

        if not movies:
            await interaction.followup.send("❌ Failed to fetch full movie details.")
            return

        view = MovieDropdownView(
            movies,
            self.get_movie_details,
            self.bot.database.movies_db,
            self.guilds,
        )
        message = await interaction.followup.send(
            "🎬 Select a movie from the list below:", view=view
        )
        view.message = message  # Store the message so `on_timeout` can edit it

    @app_commands.command(
        name="movie-list", description="List all movies added to the guild."
    )
    async def list_movies(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        movies = await self.bot.database.movies_db.get_movies(
            guild_id=str(interaction.guild_id)
        )
        if not movies:
            await interaction.followup.send("❌ No movies found.")
            return

        PAGE_SIZE = 5
        total_pages = (len(movies) + PAGE_SIZE - 1) // PAGE_SIZE
        current_page = 0

        def create_embed(page):
            start = page * PAGE_SIZE
            end = min(start + PAGE_SIZE, len(movies))
            embed = discord.Embed(title="Movies Added to Guild")

            for i in range(start, end):
                movie = movies[i]
                embed.add_field(
                    name=movie["title"],
                    value=f"IMDB Link: {movie['imdb_link']}\nAdded by: {movie['added_by_name']}",
                    inline=False,
                )

            embed.set_footer(text=f"Page {page + 1}/{total_pages}")
            return embed

        embed = create_embed(current_page)
        view = MoviePaginationView(
            current_page, total_pages, movies, self.bot.database, create_embed
        )
        await interaction.followup.send(embed=embed, view=view)

    async def get_movie_details(self, imdb_id: str):
        if imdb_id in self.cache:
            return self.cache[imdb_id]

        async with aiohttp.ClientSession() as session:
            params = {"i": f"tt{imdb_id}", "apikey": OMDB_API_KEY}
            async with session.get(OMDB_URL, params=params) as resp:
                data = await resp.json()
                self.cache[imdb_id] = data
                return data

    async def movie_title_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        movies = await self.bot.database.movies_db.get_movies(
            guild_id=str(interaction.guild_id)
        )

        # Filter and return matching titles
        return [
            app_commands.Choice(name=m["title"], value=m["title"])
            for m in movies
            if current.lower() in m["title"].lower()
        ][:25]

    @app_commands.command(name="movie-remove", description="Remove a movie by title.")
    @app_commands.describe(title="The title of the movie to remove.")
    @app_commands.autocomplete(title=movie_title_autocomplete)
    async def remove_movie(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer(thinking=True)

        movies = await self.bot.database.movies_db.get_movies(
            guild_id=str(interaction.guild_id)
        )
        movie = next((m for m in movies if m["title"] == title), None)

        if not movie:
            await interaction.followup.send("❌ Movie not found.")
            return

        success = await self.bot.database.movies_db.remove_movie(
            guild_id=str(interaction.guild_id),
            imdb_id=movie["imdb_id"],
        )

        if success:
            await interaction.followup.send(f"✅ Removed {title} from the list.")
        else:
            await interaction.followup.send(f"❌ Could not remove {title}.")


class MoviePaginationView(discord.ui.View):
    def __init__(self, current_page, total_pages, movies, db, create_embed):
        super().__init__(timeout=60)
        self.current_page = current_page
        self.total_pages = total_pages
        self.movies = movies
        self.db = db
        self.create_embed = create_embed

    @discord.ui.button(
        label="⬅️ Previous", style=discord.ButtonStyle.primary, disabled=True
    )
    async def prev_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.current_page > 0:
            self.current_page -= 1
            embed = self.create_embed(self.current_page)
            self.update_buttons()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="➡️ Next", style=discord.ButtonStyle.primary, disabled=False
    )
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            embed = self.create_embed(self.current_page)
            self.update_buttons()
            await interaction.response.edit_message(embed=embed, view=self)

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == self.total_pages - 1


class MovieDropdownView(discord.ui.View):
    def __init__(self, movies, fetch_details_func, db, guilds):
        super().__init__(timeout=10)
        self.select = MovieSelect(movies, fetch_details_func, db, guilds)
        self.add_item(self.select)
        self.message = None  # This will be set after sending the message

    async def on_timeout(self):
        self.select.disabled = True  # Disable the dropdown

        if self.message:  # Only attempt to edit if message is stored
            try:
                await self.message.edit(
                    content="⚠️ Timed out. Please run the command again.", view=self
                )
            except discord.NotFound:
                pass  # Message deleted
            except discord.HTTPException:
                pass  # Failed to edit for some reason


class MovieSelect(discord.ui.Select):
    def __init__(self, movies, fetch_details_func, db, guilds):
        self.movies = movies
        self.fetch_details = fetch_details_func
        self.db = db
        self.guilds = guilds

        options = [
            discord.SelectOption(
                label=f"{m.get('title', 'Unknown')} ({m.get('year', '?')})",
                value=m.movieID,
            )
            for m in movies
        ]
        super().__init__(placeholder="Choose a movie", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        movie_id = self.values[0]
        movie = await self.fetch_details(movie_id)
        if not movie:
            await interaction.followup.send("❌ Failed to fetch movie details.")
            return

        embed = discord.Embed(
            title=movie.get("Title", "Unknown Title"),
            description=movie.get("Plot", "No plot available."),
            url=f"https://www.imdb.com/title/tt{movie_id}/",
        )
        embed.add_field(name="Year", value=movie.get("Year", "Unknown"))
        embed.add_field(name="Genre", value=movie.get("Genre", "Unknown"))
        if poster := movie.get("Poster"):
            embed.set_thumbnail(url=poster)

        view = MovieActionView(
            imdb_id=movie_id,
            title=movie.get("Title", "Unknown Title"),
            db=self.db,
            original_interaction=interaction,
            movies=self.movies,
            fetch_details=self.fetch_details,
            guilds=self.guilds,
        )
        await interaction.followup.send(embed=embed, view=view)


class MovieActionView(discord.ui.View):
    def __init__(
        self, imdb_id, title, db, original_interaction, movies, fetch_details, guilds
    ):
        super().__init__(timeout=60)
        self.imdb_id = imdb_id
        self.title = title
        self.db = db
        self.original_interaction = original_interaction
        self.movies = movies
        self.fetch_details = fetch_details
        self.guilds = guilds

    @discord.ui.button(label="🎬 Save Movie", style=discord.ButtonStyle.success)
    async def save_movie(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(thinking=True)

        imdb_link = f"https://www.imdb.com/title/tt{self.imdb_id}/"
        success = await self.db.save_movie(
            guild_id=str(self.original_interaction.guild_id),
            title=self.title,
            imdb_id=self.imdb_id,
            imdb_link=imdb_link,
            added_by_id=str(self.original_interaction.user.id),
            added_by_name=self.original_interaction.user.name,
            notes=None,
        )

        if success:
            await interaction.followup.send(
                f"✅ Saved **{self.title}**!\n🔗 {imdb_link}"
            )
            self.guilds[str(self.original_interaction.guild_id)][self.title] = {
                "guild_id": self.original_interaction.guild_id,
                "title": self.title,
                "imdb_id": self.imdb_id,
                "imdb_link": imdb_link,
                "added_by_id": str(self.original_interaction.user.id),
                "added_by_name": self.original_interaction.user.name,
                "notes": None,
            }

        else:
            await interaction.followup.send(
                f"⚠️ Could not save **{self.title}**. Maybe it's already in the list?"
            )

    @discord.ui.button(label="🔙 Back to Menu", style=discord.ButtonStyle.secondary)
    async def back_to_menu(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(thinking=True)

        view = MovieDropdownView(self.movies, self.fetch_details, self.db)
        await interaction.followup.send(
            "🎬 Select a movie from the list below:", view=view
        )


async def setup(bot):

    await bot.add_cog(Movies(bot))
