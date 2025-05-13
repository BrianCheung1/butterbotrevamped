import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from imdb import Cinemagoer

ia = Cinemagoer()

OMDB_API_KEY = os.getenv("OMDBAPI_KEY")
OMDB_URL = "http://www.omdbapi.com/"


class Movies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = {}

    @app_commands.command(name="addmovie", description="Search for a movie by title.")
    async def add_movie(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer(thinking=True)

        movies = ia.search_movie(title)
        if not movies:
            await interaction.followup.send("❌ No results found.")
            return

        view = MovieDropdownView(
            movies, self.get_movie_details, self.bot.database.movies_db
        )
        await interaction.followup.send(
            "🎬 Select a movie from the list below:", view=view
        )

    @app_commands.command(
        name="listmovies", description="List all movies added to the guild."
    )
    async def list_movies(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        # Fetch all movies from the database for the guild
        movies = await self.bot.database.movies_db.get_movies(
            guild_id=str(interaction.guild_id)
        )

        if not movies:
            await interaction.followup.send("❌ No movies found.")
            return

        # Define the page size (how many movies per page)
        PAGE_SIZE = 5
        total_pages = (
            len(movies) + PAGE_SIZE - 1
        ) // PAGE_SIZE  # Calculate number of pages
        current_page = 0

        # Function to create the embed for the given page
        def create_embed(page):
            start = page * PAGE_SIZE
            end = min(start + PAGE_SIZE, len(movies))
            embed = discord.Embed(title="Movies Added to Guild")

            for i in range(start, end):
                movie = movies[i]
                embed.add_field(
                    name=movie["title"],
                    value=f"IMDB Link: {movie['imdb_link']}",
                    inline=False,
                )

            embed.set_footer(text=f"Page {page + 1}/{total_pages}")
            return embed

        # Create the initial embed
        embed = create_embed(current_page)

        # Create the pagination buttons
        view = MoviePaginationView(
            current_page, total_pages, movies, self.bot.database, create_embed
        )
        await interaction.followup.send(embed=embed, view=view)

    async def get_movie_details(self, imdb_id: str):
        # Check if the movie is already cached
        if imdb_id in self.cache:
            return self.cache[imdb_id]

        # If not cached, fetch from OMDb
        async with aiohttp.ClientSession() as session:
            params = {"i": f"tt{imdb_id}", "apikey": OMDB_API_KEY}
            async with session.get(OMDB_URL, params=params) as resp:
                data = await resp.json()
                self.cache[imdb_id] = data
                return data


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
            await interaction.response.edit_message(embed=embed)
            self.update_buttons()

    @discord.ui.button(
        label="➡️ Next", style=discord.ButtonStyle.primary, disabled=False
    )
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            embed = self.create_embed(self.current_page)
            await interaction.response.edit_message(embed=embed)
            self.update_buttons()

    def update_buttons(self):
        self.children[0].disabled = (
            self.current_page == 0
        )  # Disable previous button if on first page
        self.children[1].disabled = (
            self.current_page == self.total_pages - 1
        )  # Disable next button if on last page


class MovieDropdownView(discord.ui.View):
    def __init__(self, movies, fetch_details_func, db):
        super().__init__(timeout=60)
        self.add_item(MovieSelect(movies, fetch_details_func, db))


class MovieSelect(discord.ui.Select):
    def __init__(self, movies, fetch_details_func, db):
        self.movies = movies
        self.fetch_details = fetch_details_func
        self.db = db

        options = [
            discord.SelectOption(
                label=f"{m['title']} ({m.get('year', '?')})", value=m.movieID
            )
            for m in movies[:5]
        ]
        super().__init__(placeholder="Choose a movie", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        movie_id = self.values[0]
        movie = await self.fetch_details(movie_id)  # Call fetch_details correctly
        if not movie:
            await interaction.followup.send("❌ Failed to fetch movie details.")
            return

        embed = discord.Embed(
            title=movie.get("Title", "Unknown Title"),
            description=movie.get("Plot", "No plot available."),
            url=f"https://www.imdb.com/title/{movie_id}/",
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
        )

        await interaction.followup.send(embed=embed, view=view)


class MovieActionView(discord.ui.View):
    def __init__(self, imdb_id, title, db, original_interaction, movies, fetch_details):
        super().__init__(timeout=60)
        self.imdb_id = imdb_id
        self.title = title
        self.db = db
        self.original_interaction = original_interaction
        self.movies = movies
        self.fetch_details = fetch_details

    @discord.ui.button(label="🎬 Save Movie", style=discord.ButtonStyle.success)
    async def save_movie(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(thinking=True)

        imdb_link = f"https://www.imdb.com/title/{self.imdb_id}/"

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
        else:
            await interaction.followup.send(
                f"⚠️ Could not save **{self.title}**. Maybe it's already in the list?",
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
