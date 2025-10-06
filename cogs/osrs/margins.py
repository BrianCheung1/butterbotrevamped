import asyncio
import time
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.channels import broadcast_embed_to_guilds

WIKI_LATEST_URL = "https://prices.runescape.wiki/api/v1/osrs/latest"
WIKI_MAPPING_URL = "https://prices.runescape.wiki/api/v1/osrs/mapping"
WEIRDGLOOP_URL = "https://api.weirdgloop.org/exchange/history/osrs/latest"

# === FILTERS ===
MIN_VOLUME = 400
MIN_PRICE = 250_000
MAX_PRICE = 20_000_000
ITEMS_PER_PAGE = 5
CACHE_DURATION = 60
CHECK_INTERVAL = 60
TOP_ITEMS_COUNT = 15
# =================================


class PaginationView(discord.ui.View):
    """Pagination view for flipping through pages."""

    def __init__(self, embeds, cog):
        super().__init__(timeout=3600)
        self.embeds = embeds
        self.cog = cog
        self.current_page = 0
        self.max_pages = len(embeds)

    def update_buttons(self):
        """Enable/disable buttons based on current page."""
        self.first_page.disabled = self.current_page == 0
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= self.max_pages - 1
        self.last_page.disabled = self.current_page >= self.max_pages - 1

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.gray)
    async def first_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page], view=self
        )

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.blurple)
    async def prev_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page], view=self
        )

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.blurple)
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page], view=self
        )

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.gray)
    async def last_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page = self.max_pages - 1
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page], view=self
        )

    @discord.ui.button(label="🔄 Run Again", style=discord.ButtonStyle.green, row=1)
    async def run_again(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        time_since_cache = time.time() - self.cog.last_fetch_time

        if time_since_cache < CACHE_DURATION:
            remaining = int(CACHE_DURATION - time_since_cache)
            current_embed = self.embeds[self.current_page].copy()

            original_footer = f"Page {self.current_page + 1}/{self.max_pages} • Prices: OSRS Wiki API • Volume: Weirdgloop API"
            current_embed.set_footer(
                text=f"{original_footer}\n⏳ Using cached data. Fresh data available in {remaining}s."
            )

            await interaction.response.edit_message(embed=current_embed, view=self)
            return

        await interaction.response.defer()

        embeds = await self.cog.fetch_margin_data(force_refresh=True)

        if isinstance(embeds, str):
            current_embed = self.embeds[self.current_page].copy()
            original_footer = f"Page {self.current_page + 1}/{self.max_pages} • Prices: OSRS Wiki API • Volume: Weirdgloop API"
            current_embed.set_footer(text=f"{original_footer}\n❌ {embeds}")
            await interaction.edit_original_response(embed=current_embed, view=self)
            return

        new_view = PaginationView(embeds, self.cog)
        new_view.update_buttons()

        fresh_embed = embeds[0].copy()
        original_footer = (
            f"Page 1/{len(embeds)} • Prices: OSRS Wiki API • Volume: Weirdgloop API"
        )
        fresh_embed.set_footer(text=f"{original_footer}\n✅ Data refreshed!")

        await interaction.edit_original_response(embed=fresh_embed, view=new_view)


class OSRSMargin(commands.Cog):
    """Cog to analyze OSRS GE margins with accurate daily volume filtering."""

    def __init__(self, bot):
        self.bot = bot
        self.cached_embeds = None
        self.last_fetch_time = 0
        self.top_item_ids = set()
        self._first_run = True  # Flag for first background task run
        self.check_new_items.start()

    def cog_unload(self):
        """Stop the background task when cog is unloaded."""
        self.check_new_items.cancel()

    async def fetch_margin_data(self, force_refresh=False):
        """Fetch and process margin data, return embeds or error message."""
        # Check cache if not forcing refresh
        if not force_refresh:
            time_since_cache = time.time() - self.last_fetch_time
            if time_since_cache < CACHE_DURATION and self.cached_embeds:
                return self.cached_embeds

        # Get profitable items
        result = await self._get_profitable_items()

        # Check if error message was returned
        if isinstance(result, str):
            return result

        profitable_items = result

        if not profitable_items:
            return f"❌ No items found matching criteria (Vol ≥ {MIN_VOLUME:,}, Margin ≥ {MIN_PRICE:,} gp, Price ≤ {MAX_PRICE:,} gp)"

        # Create paginated embeds
        embeds = []
        total_pages = (len(profitable_items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

        for page in range(total_pages):
            start_idx = page * ITEMS_PER_PAGE
            end_idx = min(start_idx + ITEMS_PER_PAGE, len(profitable_items))
            page_items = profitable_items[start_idx:end_idx]

            embed = discord.Embed(
                title="📊 OSRS Top Margins",
                description=f"Found {len(profitable_items)} items (Vol ≥ {MIN_VOLUME:,}, Margin ≥ {MIN_PRICE:,} gp, Price ≤ {MAX_PRICE:,} gp)",
                color=discord.Color.gold(),
            )

            for i, item in enumerate(page_items, start=start_idx + 1):
                buy_time = f"<t:{item['low_time']}:R>" if item["low_time"] else "N/A"
                sell_time = f"<t:{item['high_time']}:R>" if item["high_time"] else "N/A"

                embed.add_field(
                    name=f"#{i} - {item['name']}",
                    value=(
                        f"Buy: **{item['low']:,}** gp ({buy_time})\n"
                        f"Sell: **{item['high']:,}** gp ({sell_time})\n"
                        f"Margin: **{item['margin']:,}** gp | ROI: **{item['roi']}%**\n"
                        f"Volume: {item['volume']:,}"
                    ),
                    inline=False,
                )

            embed.set_footer(
                text=f"Page {page + 1}/{total_pages} • Prices: OSRS Wiki API • Volume: Weirdgloop API"
            )
            embeds.append(embed)

        # Cache the results
        self.cached_embeds = embeds
        self.last_fetch_time = time.time()

        return embeds

    @app_commands.command(
        name="osrs-margin",
        description="Show top OSRS items by margin (high - low - 2% tax), filtered by daily volume",
    )
    async def osrs_margin(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            embeds = await self.fetch_margin_data()

            # Check if error message was returned
            if isinstance(embeds, str):
                await interaction.followup.send(embeds)
                return

            # Send with pagination
            view = PaginationView(embeds, self)
            view.update_buttons()
            await interaction.followup.send(embed=embeds[0], view=view)

        except Exception as e:
            self.bot.logger.error(f"Error in osrs_margin command: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An unexpected error occurred: {str(e)}"
            )

    @tasks.loop(seconds=CHECK_INTERVAL)
    async def check_new_items(self):
        """Background task to check for new items in top 15 and broadcast alerts."""
        try:
            # Skip data fetching on first run to speed up cog loading
            if self._first_run:
                self.bot.logger.info(
                    "OSRS Margin Monitor: First run, populating initial data without alerts"
                )
                self._first_run = False

                # Just populate the top_item_ids set without fetching or alerting
                result = await self._get_profitable_items()
                if isinstance(result, str) or not result:
                    return

                top_items = result[:TOP_ITEMS_COUNT]
                self.top_item_ids = {item["id"] for item in top_items}
                self.bot.logger.info(
                    f"OSRS Margin Monitor: Initialized with {len(self.top_item_ids)} top items"
                )
                return

            embeds = await self.fetch_margin_data(force_refresh=True)

            if isinstance(embeds, str):
                self.bot.logger.error(
                    f"Failed to fetch OSRS data for monitoring: {embeds}"
                )
                return

            if not embeds or len(embeds) == 0:
                return

            # Get profitable items
            result = await self._get_profitable_items()
            if isinstance(result, str) or not result:
                return

            profitable_items = result

            # Get top N items
            top_items = profitable_items[:TOP_ITEMS_COUNT]
            current_top_ids = {item["id"] for item in top_items}

            # Find new items that weren't in the previous top list
            if self.top_item_ids:
                new_items = [
                    item for item in top_items if item["id"] not in self.top_item_ids
                ]

                for item in new_items:
                    embed = discord.Embed(
                        title="🚨 New High Margin Item Alert!",
                        description=f"**{item['name']}** has entered the top {TOP_ITEMS_COUNT} margins!",
                        color=discord.Color.gold(),
                        timestamp=datetime.now(timezone.utc),
                    )

                    buy_time = (
                        f"<t:{item['low_time']}:R>" if item["low_time"] else "N/A"
                    )
                    sell_time = (
                        f"<t:{item['high_time']}:R>" if item["high_time"] else "N/A"
                    )

                    embed.add_field(
                        name="📊 Margin Details",
                        value=(
                            f"**Buy Price:** {item['low']:,} gp ({buy_time})\n"
                            f"**Sell Price:** {item['high']:,} gp ({sell_time})\n"
                            f"**Margin:** {item['margin']:,} gp\n"
                            f"**ROI:** {item['roi']}%\n"
                            f"**Daily Volume:** {item['volume']:,}"
                        ),
                        inline=False,
                    )

                    embed.set_footer(text="OSRS Wiki API • Weirdgloop API")

                    await broadcast_embed_to_guilds(self.bot, "osrs_channel_id", embed)

                    self.bot.logger.info(
                        f"🚨 Alert sent: {item['name']} entered top {TOP_ITEMS_COUNT} margins"
                    )

            self.top_item_ids = current_top_ids

        except Exception as e:
            self.bot.logger.error(
                f"Error in OSRS margin monitoring task: {e}", exc_info=True
            )

    @check_new_items.before_loop
    async def before_check_new_items(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    async def _get_profitable_items(self):
        """Helper method to get the list of profitable items.

        Returns:
            List of profitable items or error message string
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch latest prices from Wiki
                self.bot.logger.info("Fetching latest prices from OSRS Wiki API...")
                async with session.get(
                    WIKI_LATEST_URL, timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    latest_data = data.get("data", {})

                if not latest_data:
                    self.bot.logger.error("No data returned from Wiki latest API")
                    return "❌ No price data available from OSRS Wiki API"

                self.bot.logger.info(f"Received {len(latest_data)} items from Wiki API")

                # Fetch item mapping for names
                self.bot.logger.info("Fetching item mappings...")
                async with session.get(
                    WIKI_MAPPING_URL, timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    response.raise_for_status()
                    mapping = await response.json()

                if not mapping:
                    self.bot.logger.error("No mapping data returned from Wiki API")
                    return "❌ No item mapping data available from OSRS Wiki API"

                self.bot.logger.info(f"Received {len(mapping)} items in mapping")

                # Create ID to name lookup
                id_to_item = {item["id"]: item for item in mapping}

                # Build item name list for Weirdgloop API
                item_names = [item["name"] for item in mapping]

                # Split into chunks of 100 items
                chunk_size = 100
                name_chunks = [
                    item_names[i : i + chunk_size]
                    for i in range(0, len(item_names), chunk_size)
                ]

                # Fetch volume data from Weirdgloop using concurrent requests
                self.bot.logger.info(
                    f"Fetching volume data in {len(name_chunks)} chunks concurrently..."
                )

                async def fetch_chunk(chunk, idx):
                    """Fetch a single chunk of volume data."""
                    params = {"name": "|".join(chunk)}
                    async with session.get(
                        WEIRDGLOOP_URL,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        response.raise_for_status()
                        chunk_data = await response.json()
                        if idx % 10 == 0:
                            self.bot.logger.info(
                                f"Processed chunk {idx + 1}/{len(name_chunks)}"
                            )
                        return chunk_data

                # Fetch all chunks concurrently (with a limit to avoid overwhelming the API)
                volume_data = {}

                # Process in batches of 5 concurrent requests to be respectful to the API
                batch_size = 5
                for i in range(0, len(name_chunks), batch_size):
                    batch = name_chunks[i : i + batch_size]
                    tasks = [
                        fetch_chunk(chunk, i + idx) for idx, chunk in enumerate(batch)
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in results:
                        if isinstance(result, Exception):
                            self.bot.logger.error(
                                f"Error fetching volume chunk: {result}"
                            )
                            continue
                        volume_data.update(result)

                self.bot.logger.info(
                    f"Received volume data for {len(volume_data)} items"
                )

        except aiohttp.ClientError as e:
            self.bot.logger.error(f"HTTP error fetching OSRS data: {e}")
            return f"❌ Error fetching data from OSRS APIs: {str(e)}"
        except asyncio.TimeoutError:
            self.bot.logger.error("Timeout fetching OSRS data")
            return "❌ Request timed out while fetching data from OSRS APIs"
        except Exception as e:
            self.bot.logger.error(
                f"Unexpected error fetching OSRS data: {e}", exc_info=True
            )
            return f"❌ Unexpected error: {str(e)}"

        profitable_items = []

        for item_id_str, price_data in latest_data.items():
            try:
                item_id = int(item_id_str)
            except ValueError:
                continue

            # Get high and low prices
            high_price = price_data.get("high")
            low_price = price_data.get("low")
            high_time = price_data.get("highTime")
            low_time = price_data.get("lowTime")

            # Skip if missing price data
            if high_price is None or low_price is None:
                continue

            if high_price <= 0 or low_price <= 0:
                continue

            # Skip if no margin potential
            if high_price <= low_price:
                continue

            # Get item info
            item_info = id_to_item.get(item_id)
            if not item_info:
                continue

            item_name = item_info["name"]

            # Get volume from Weirdgloop data
            if item_name not in volume_data:
                continue

            daily_volume = volume_data[item_name].get("volume")

            # Skip if volume is None or missing
            if daily_volume is None:
                continue

            # Filter by volume
            if daily_volume < MIN_VOLUME:
                continue

            # Filter by max price (if set)
            if MAX_PRICE is not None and low_price > MAX_PRICE:
                continue

            # Calculate margin after 2% GE tax
            ge_tax = high_price * 0.02
            effective_sell = high_price - ge_tax
            margin = effective_sell - low_price

            # Skip if not profitable after tax (using MIN_PRICE threshold)
            if margin <= MIN_PRICE:
                continue

            # Calculate ROI
            roi = (margin / low_price) * 100 if low_price > 0 else 0

            profitable_items.append(
                {
                    "id": item_id,
                    "name": item_name,
                    "high": high_price,
                    "low": low_price,
                    "high_time": high_time,
                    "low_time": low_time,
                    "margin": round(margin),
                    "roi": round(roi, 2),
                    "volume": daily_volume,
                }
            )

        # Sort by margin (highest to lowest)
        profitable_items.sort(key=lambda x: x["margin"], reverse=True)

        self.bot.logger.info(
            f"Found {len(profitable_items)} profitable items after filtering"
        )

        return profitable_items


async def setup(bot):
    await bot.add_cog(OSRSMargin(bot))
