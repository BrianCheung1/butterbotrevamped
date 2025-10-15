import time
from datetime import datetime, timezone
from typing import Dict

import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.channels import broadcast_embed_to_guilds
from logger import setup_logger

logger = setup_logger("OSRSMargin")

# === FILTERS ===
MIN_VOLUME = 400
MAX_PRICE = 20_000_000
ITEMS_PER_PAGE = 5
CACHE_DURATION = 60
CHECK_INTERVAL = 60
TOP_ITEMS_COUNT = 15
# Margin tiers for ALERTS (stricter)
ALERT_MARGIN_TIERS = [
    {"price_min": 1_000_000, "price_max": 5_000_000, "min_margin": 200_000},
    {"price_min": 5_000_000, "price_max": 10_000_000, "min_margin": 500_000},
    {"price_min": 10_000_000, "price_max": 15_000_000, "min_margin": 750_000},
    {"price_min": 15_000_000, "price_max": float("inf"), "min_margin": 1_000_000},
]

# Below average tiers for ALERTS (margin from current buy to avg sell must meet these thresholds)
BELOW_AVG_TIERS = [
    {"price_min": 0, "price_max": 1_000_000, "min_margin": 150_000},
    {"price_min": 1_000_000, "price_max": 5_000_000, "min_margin": 250_000},
    {"price_min": 5_000_000, "price_max": 10_000_000, "min_margin": 1_000_000},
    {"price_min": 10_000_000, "price_max": 15_000_000, "min_margin": 2_000_000},
    {"price_min": 15_000_000, "price_max": float("inf"), "min_margin": 5_000_000},
]

# Margin threshold for COMMAND (more lenient)
COMMAND_MIN_MARGIN = 100_000
# =================================


def get_min_margin_for_price(price: int) -> int:
    """
    Get the minimum margin required for ALERTS based on item price (stricter tiers).

    :param price: The buy price of the item
    :return: Minimum margin required in gp
    """
    for tier in ALERT_MARGIN_TIERS:
        if tier["price_min"] <= price < tier["price_max"]:
            return tier["min_margin"]
    return ALERT_MARGIN_TIERS[-1]["min_margin"]


def get_min_below_avg_for_price(price: int) -> int:
    """
    Get the minimum margin (current buy to avg sell) required for below-avg alerts based on item price.

    :param price: The current buy price of the item
    :return: Minimum margin required in gp
    """
    for tier in BELOW_AVG_TIERS:
        if tier["price_min"] <= price < tier["price_max"]:
            return tier["min_margin"]
    return BELOW_AVG_TIERS[-1]["min_margin"]


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

        # Separate tracking for each alert type
        self.top_margin_item_ids = set()  # Original high margin alerts
        self.below_avg_item_ids = set()  # New below average alerts

        self._first_run = True
        self._first_fetch = True

        # Use centralized data manager
        self.data_manager = bot.osrs_data

        self.check_new_items.start()

    def cog_unload(self):
        """Stop the background task when cog is unloaded."""
        self.check_new_items.cancel()

    async def fetch_margin_data(
        self, force_refresh=False, use_alert_filters=False, shared_data=None
    ):
        """
        Fetch and process margin data, return embeds or error message.

        :param force_refresh: Force bypass cache
        :param use_alert_filters: If True, use stricter alert margin tiers. If False, use command margin threshold.
        :param shared_data: Optional pre-fetched API data to reuse (dict)
        """
        if self._first_fetch and not force_refresh:
            self._first_fetch = False
            return "⏳ Bot just started/reloaded. Please run the command again in a moment."

        # Use cache if available and no force refresh
        if not force_refresh and not use_alert_filters:
            time_since_cache = time.time() - self.last_fetch_time
            if time_since_cache < CACHE_DURATION and self.cached_embeds:
                return self.cached_embeds

        # Get profitable items (with shared data reuse)
        result = await self._get_profitable_items(
            use_alert_filters=use_alert_filters,
            force_refresh=force_refresh,
            shared_data=shared_data,
        )

        if isinstance(result, str):
            return result

        profitable_items = result

        if not profitable_items:
            if use_alert_filters:
                return (
                    "❌ No items found matching alert criteria (strict tiered margins)"
                )
            return f"❌ No items found matching criteria (Vol ≥ {MIN_VOLUME:,}, Margin ≥ {COMMAND_MIN_MARGIN:,} gp)"

        # Build paginated embeds
        embeds = []
        total_pages = (len(profitable_items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        for page in range(total_pages):
            start_idx = page * ITEMS_PER_PAGE
            end_idx = min(start_idx + ITEMS_PER_PAGE, len(profitable_items))
            page_items = profitable_items[start_idx:end_idx]

            desc = (
                f"Found {len(profitable_items)} items • Volume ≥ {MIN_VOLUME:,} • "
                + (
                    "Tiered margins (alerts)"
                    if use_alert_filters
                    else f"Margin ≥ {COMMAND_MIN_MARGIN:,} gp"
                )
            )

            embed = discord.Embed(
                title="📊 OSRS Top Margins",
                description=desc,
                color=discord.Color.gold(),
            )

            for i, item in enumerate(page_items, start=start_idx + 1):
                buy_time = f"<t:{item['low_time']}:R>" if item["low_time"] else "N/A"
                sell_time = f"<t:{item['high_time']}:R>" if item["high_time"] else "N/A"

                embed.add_field(
                    name=f"#{i} - {item['name']}",
                    value=(
                        f"[📈 View Graph](https://prices.osrs.cloud/item/{item['id']})\n"
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

        # Cache results (for command only)
        if not use_alert_filters:
            self.cached_embeds = embeds
            self.last_fetch_time = time.time()

        return embeds

    @app_commands.command(
        name="osrs-margin",
        description="Show top OSRS items by margin (high - low - 2% tax), filtered by daily volume",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
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
            logger.error(f"Error in command: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An unexpected error occurred: {str(e)}"
            )

    @tasks.loop(seconds=CHECK_INTERVAL)
    async def check_new_items(self):
        """Background task to check for both high margin and below-average items."""
        try:
            if self._first_run:
                logger.info("First run — populating baseline items only")
                self._first_run = False
                result = await self._get_profitable_items(use_alert_filters=True)
                if isinstance(result, str) or not result:
                    return

                # Initialize both tracking sets
                margin_result = await self._get_profitable_items(use_alert_filters=True)
                if not isinstance(margin_result, str) and margin_result:
                    self.top_margin_item_ids = {
                        item["id"] for item in margin_result[:TOP_ITEMS_COUNT]
                    }

                # Initialize below-average tracking
                below_avg_result = await self._get_below_average_items()
                if not isinstance(below_avg_result, str) and below_avg_result:
                    self.below_avg_item_ids = {
                        item["id"] for item in below_avg_result[:TOP_ITEMS_COUNT]
                    }

                logger.info(
                    f"Initialized with {len(self.top_margin_item_ids)} margin items and {len(self.below_avg_item_ids)} below-avg items"
                )
                return

            # Fetch shared API data ONCE
            latest_data = await self.data_manager.get_latest_prices(force_refresh=True)
            mapping = await self.data_manager.get_mapping(force_refresh=True)
            item_names = [item["name"] for item in mapping]
            volume_data = await self.data_manager.get_weirdgloop_volumes(
                item_names, force_refresh=True
            )

            shared_data = {
                "price_data": latest_data.get("data", {}),
                "mapping": mapping,
                "volume_data": volume_data,
            }

            # ========== ALERT TYPE 1: High Margin Items (Original) ==========
            # Get profitable items with strict margin filters
            profitable_items = await self._get_profitable_items(
                use_alert_filters=True, shared_data=shared_data
            )
            if isinstance(profitable_items, str) or not profitable_items:
                logger.warning("No profitable items found for margin alerts")
                profitable_items = []

            top_margin_items = (
                profitable_items[:TOP_ITEMS_COUNT] if profitable_items else []
            )
            current_margin_ids = {item["id"] for item in top_margin_items}

            new_margin_items = [
                item
                for item in top_margin_items
                if item["id"] not in self.top_margin_item_ids
            ]

            for item in new_margin_items:
                embed = discord.Embed(
                    title="🚨 New High Margin Item Alert!",
                    description=f"**{item['name']}** entered the top {TOP_ITEMS_COUNT} margins!",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc),
                )

                buy_time = f"<t:{item['low_time']}:R>" if item["low_time"] else "N/A"
                sell_time = f"<t:{item['high_time']}:R>" if item["high_time"] else "N/A"

                embed.add_field(
                    name="📊 Margin Details",
                    value=(
                        f"**Buy:** {item['low']:,} gp ({buy_time})\n"
                        f"**Sell:** {item['high']:,} gp ({sell_time})\n"
                        f"**Margin:** {item['margin']:,} gp | ROI: {item['roi']}%\n"
                        f"**Volume:** {item['volume']:,}"
                    ),
                    inline=False,
                )

                if item.get("avg_buy_24h") or item.get("avg_buy_7d"):
                    avg_text = ""
                    if item.get("avg_buy_24h"):
                        avg_text += f"**24H Avg Buy:** {item['avg_buy_24h']:,} gp\n"
                        avg_text += f"**24H Avg Sell:** {item['avg_sell_24h']:,} gp\n"
                    if item.get("avg_buy_7d"):
                        avg_text += f"**7D Avg Buy:** {item['avg_buy_7d']:,} gp\n"
                        avg_text += f"**7D Avg Sell:** {item['avg_sell_7d']:,} gp"
                    embed.add_field(
                        name="📈 Historical Averages", value=avg_text, inline=False
                    )

                embed.set_footer(text="OSRS Wiki API • Weirdgloop API")

                await broadcast_embed_to_guilds(self.bot, "osrs_channel_id", embed)
                logger.info(
                    f"🚨 High Margin Alert: {item['name']} entered top {TOP_ITEMS_COUNT}"
                )

            # ========== ALERT TYPE 2: Below Average Items (New) ==========
            # Get items below average - uses different filtering (no strict margins required)
            below_avg_items = await self._get_below_average_items(
                shared_data=shared_data
            )
            if isinstance(below_avg_items, str) or not below_avg_items:
                logger.warning("No below-average items found")
                below_avg_items = []

            top_below_avg_items = (
                below_avg_items[:TOP_ITEMS_COUNT] if below_avg_items else []
            )
            current_below_avg_ids = {item["id"] for item in top_below_avg_items}

            new_below_avg_items = [
                item
                for item in top_below_avg_items
                if item["id"] not in self.below_avg_item_ids
            ]

            for item in new_below_avg_items:
                embed = discord.Embed(
                    title="💰 Below Average Item Alert!",
                    description=f"**{item['name']}** is **{item['below_avg']:,} gp** below average!",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc),
                )

                buy_time = f"<t:{item['low_time']}:R>" if item["low_time"] else "N/A"
                sell_time = f"<t:{item['high_time']}:R>" if item["high_time"] else "N/A"

                # Determine which average was used
                avg_source = "24H" if item.get("avg_buy_24h") else "7D"
                avg_buy_used = item.get("avg_buy_24h") or item.get("avg_buy_7d")

                embed.add_field(
                    name="💸 Price Comparison",
                    value=(
                        f"**Current Buy:** {item['low']:,} gp ({buy_time})\n"
                        f"**{avg_source} Avg Buy:** {avg_buy_used:,} gp\n"
                        f"**Discount:** {item['below_avg']:,} gp ({item['discount_pct']:.1f}%) ✅"
                    ),
                    inline=False,
                )

                embed.add_field(
                    name="📊 Profit Potential",
                    value=(
                        f"**Sell:** {item['high']:,} gp ({sell_time})\n"
                        f"**Margin:** {item['margin']:,} gp | ROI: {item['roi']}%\n"
                        f"**Avg Sell**: {avg_buy_used:,} gp\n"
                        f"**Sell to Avg Sell Margin:** {item['margin_to_avg_sell']:,} gp | ROI: {item['roi_to_avg_sell']}%\n"
                        f"**Volume:** {item['volume']:,}"
                    ),
                    inline=False,
                )

                if item.get("avg_buy_24h") or item.get("avg_buy_7d"):
                    avg_text = ""
                    if item.get("avg_buy_24h"):
                        avg_text += f"**24H Avg Buy:** {item['avg_buy_24h']:,} gp\n"
                        avg_text += f"**24H Avg Sell:** {item['avg_sell_24h']:,} gp\n"
                    if item.get("avg_buy_7d"):
                        avg_text += f"**7D Avg Buy:** {item['avg_buy_7d']:,} gp\n"
                        avg_text += f"**7D Avg Sell:** {item['avg_sell_7d']:,} gp"
                    embed.add_field(
                        name="📈 Historical Averages", value=avg_text, inline=False
                    )

                embed.set_footer(text="OSRS Wiki API • Weirdgloop API")

                await broadcast_embed_to_guilds(self.bot, "osrs_channel_id", embed)
                logger.info(
                    f"💰 Below Avg Alert: {item['name']} is {item['below_avg']:,} gp below avg ({item['discount_pct']:.1f}%)"
                )

            # Update cached embeds
            embeds = await self.fetch_margin_data(shared_data=shared_data)
            if not isinstance(embeds, str):
                self.cached_embeds = embeds
                self.last_fetch_time = time.time()

            # Update tracking sets
            self.top_margin_item_ids = current_margin_ids
            self.below_avg_item_ids = current_below_avg_ids

        except Exception as e:
            logger.error(f"Error in monitoring task: {e}", exc_info=True)

    @check_new_items.before_loop
    async def before_check_new_items(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    async def _get_below_average_items(self, shared_data=None, force_refresh=False):
        """
        Get items that are significantly below their average buy price AND have good margin to avg sell.
        Uses tiered margin requirements based on item price.

        :param shared_data: Optional dict with pre-fetched data
        :param force_refresh: Force refresh from API
        :return: List of items below average, sorted by margin to avg sell
        """
        try:
            if shared_data:
                price_data = shared_data["price_data"]
                mapping = shared_data["mapping"]
                volume_data = shared_data["volume_data"]
            else:
                logger.info("Fetching OSRS data for below-average check...")
                latest_data = await self.data_manager.get_latest_prices(
                    force_refresh=force_refresh
                )
                price_data = latest_data.get("data", {})
                mapping = await self.data_manager.get_mapping(
                    force_refresh=force_refresh
                )
                item_names = [item["name"] for item in mapping]
                volume_data = await self.data_manager.get_weirdgloop_volumes(
                    item_names, force_refresh=force_refresh
                )

            if not price_data or not mapping or not volume_data:
                return "❌ Missing OSRS API data"

        except Exception as e:
            logger.error(f"Error fetching OSRS data for below-avg: {e}", exc_info=True)
            return f"❌ Error fetching data from OSRS APIs: {str(e)}"

        below_avg_items = []

        for item_id_str, price_info in price_data.items():
            try:
                item_id = int(item_id_str)
            except ValueError:
                continue

            low_price = price_info.get("low")
            high_price = price_info.get("high")
            high_time = price_info.get("highTime")
            low_time = price_info.get("lowTime")

            if not low_price:
                continue

            item_info = self.data_manager.get_item_info(item_id)
            if not item_info:
                continue

            item_name = item_info["name"]
            if item_name not in volume_data:
                continue

            daily_volume = volume_data[item_name].get("volume")
            if not daily_volume or daily_volume < MIN_VOLUME:
                continue

            # Optional: filter by max price
            if MAX_PRICE is not None and low_price > MAX_PRICE:
                continue

            # Get historical data to compare with current price
            try:
                item_data = await self.data_manager.get_comprehensive_item_data(item_id)
                historical_stats = self._calculate_stats(item_data["history"])
            except Exception as e:
                logger.debug(f"No history for {item_name}: {e}")
                continue

            # Check 24h average first, fallback to 7d
            avg_buy_24h = int(historical_stats.get("24h", {}).get("avg_low", 0))
            avg_buy_7d = int(historical_stats.get("7d", {}).get("avg_low", 0))
            avg_sell_24h = int(historical_stats.get("24h", {}).get("avg_high", 0))
            avg_sell_7d = int(historical_stats.get("7d", {}).get("avg_high", 0))

            avg_buy = avg_buy_24h or avg_buy_7d
            avg_sell = avg_sell_24h or avg_sell_7d

            if not avg_buy or avg_buy <= 0:
                continue

            # Calculate how much below average buy price
            below_avg = avg_buy - low_price

            # Must be below average to qualify
            if below_avg <= 0:
                continue

            # Calculate margin from current buy to average sell (this is what gets tiered)
            if not avg_sell or avg_sell <= low_price:
                continue

            ge_tax_avg = avg_sell * 0.02
            margin_to_avg_sell = round((avg_sell - ge_tax_avg) - low_price)

            roi_to_avg_sell = (
                round((margin_to_avg_sell / low_price) * 100, 2) if low_price > 0 else 0
            )

            # Use tiered threshold based on current buy price
            min_required_margin = get_min_below_avg_for_price(low_price)

            if margin_to_avg_sell < min_required_margin:
                continue

            # Calculate discount percentage
            discount_pct = (below_avg / avg_buy) * 100

            # Calculate margin if high price exists
            margin = 0
            roi = 0
            if high_price and high_price > low_price:
                ge_tax = high_price * 0.02
                margin = round((high_price - ge_tax) - low_price)
                roi = round((margin / low_price) * 100, 2) if low_price > 0 else 0

            below_avg_items.append(
                {
                    "id": item_id,
                    "name": item_name,
                    "low": low_price,
                    "high": high_price or 0,
                    "high_time": high_time,
                    "low_time": low_time,
                    "volume": daily_volume,
                    "below_avg": below_avg,
                    "discount_pct": discount_pct,
                    "margin_to_avg_sell": margin_to_avg_sell,
                    "roi_to_avg_sell": roi_to_avg_sell,
                    "avg_buy_24h": avg_buy_24h,
                    "avg_sell_24h": avg_sell_24h,
                    "avg_buy_7d": avg_buy_7d,
                    "avg_sell_7d": avg_sell_7d,
                    "margin": margin,
                    "roi": roi,
                }
            )

        # Sort by margin to average sell (biggest profit potential first)
        below_avg_items.sort(key=lambda x: x["margin_to_avg_sell"], reverse=True)
        logger.info(
            f"Found {len(below_avg_items)} items below average (tiered margin requirements)"
        )

        return below_avg_items

    def _calculate_stats(self, history: Dict) -> Dict:
        """Calculate 24h and 7d statistics from timeseries data."""
        from statistics import mean

        stats = {}

        # Timeframe configurations: (step, lookback_count)
        timeframes = {
            "24h": ("5m", 288),  # 24h * 12 (5min intervals)
            "7d": ("1h", 168),  # 7d * 24 hours
        }

        for period, (step, count) in timeframes.items():
            data = history.get(step, [])[-count:] if history.get(step) else []

            if not data:
                stats[period] = {}
                continue

            # Extract prices and volumes
            high_prices = [d["avgHighPrice"] for d in data if d.get("avgHighPrice")]
            low_prices = [d["avgLowPrice"] for d in data if d.get("avgLowPrice")]
            volumes = [
                (d.get("highPriceVolume", 0) + d.get("lowPriceVolume", 0)) for d in data
            ]

            stats[period] = {
                "high": max(high_prices) if high_prices else 0,
                "low": min([p for p in low_prices if p > 0], default=0),
                "avg_high": mean(high_prices) if high_prices else 0,
                "avg_low": mean(low_prices) if low_prices else 0,
                "volume": sum(volumes),
                "avg_vol": mean(volumes) if volumes else 0,
            }

        return stats

    async def _get_profitable_items(
        self, use_alert_filters=False, force_refresh=False, shared_data=None
    ):
        """
        Get list of profitable items using shared or fetched API data.

        :param use_alert_filters: Use tiered margins (for alerts)
        :param force_refresh: Force refresh from API
        :param shared_data: Optional dict with pre-fetched data
        """
        try:
            if shared_data:
                price_data = shared_data["price_data"]
                mapping = shared_data["mapping"]
                volume_data = shared_data["volume_data"]
            else:
                logger.info("Fetching OSRS data (no shared data provided)...")
                latest_data = await self.data_manager.get_latest_prices(
                    force_refresh=force_refresh
                )
                price_data = latest_data.get("data", {})
                mapping = await self.data_manager.get_mapping(
                    force_refresh=force_refresh
                )
                item_names = [item["name"] for item in mapping]
                volume_data = await self.data_manager.get_weirdgloop_volumes(
                    item_names, force_refresh=force_refresh
                )

            if not price_data or not mapping or not volume_data:
                return "❌ Missing OSRS API data"

        except Exception as e:
            logger.error(f"Error fetching OSRS data: {e}", exc_info=True)
            return f"❌ Error fetching data from OSRS APIs: {str(e)}"

        profitable_items = []

        for item_id_str, price_info in price_data.items():
            try:
                item_id = int(item_id_str)
            except ValueError:
                continue

            high_price = price_info.get("high")
            low_price = price_info.get("low")
            high_time = price_info.get("highTime")
            low_time = price_info.get("lowTime")

            if not high_price or not low_price or high_price <= low_price:
                continue

            item_info = self.data_manager.get_item_info(item_id)
            if not item_info:
                continue

            item_name = item_info["name"]
            if item_name not in volume_data:
                continue

            daily_volume = volume_data[item_name].get("volume")
            if not daily_volume or daily_volume < MIN_VOLUME:
                continue

            if MAX_PRICE is not None and low_price > MAX_PRICE:
                continue

            ge_tax = high_price * 0.02
            margin = (high_price - ge_tax) - low_price
            if use_alert_filters:
                min_margin = get_min_margin_for_price(low_price)
            else:
                min_margin = COMMAND_MIN_MARGIN

            if margin <= min_margin:
                continue

            roi = (margin / low_price) * 100 if low_price > 0 else 0

            historical_stats = {}
            if use_alert_filters:
                try:
                    item_data = await self.data_manager.get_comprehensive_item_data(
                        item_id
                    )
                    historical_stats = self._calculate_stats(item_data["history"])
                except Exception as e:
                    logger.warning(f"Failed to get history for {item_name}: {e}")

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
                    "avg_buy_24h": int(
                        historical_stats.get("24h", {}).get("avg_low", 0)
                    ),
                    "avg_sell_24h": int(
                        historical_stats.get("24h", {}).get("avg_high", 0)
                    ),
                    "avg_buy_7d": int(historical_stats.get("7d", {}).get("avg_low", 0)),
                    "avg_sell_7d": int(
                        historical_stats.get("7d", {}).get("avg_high", 0)
                    ),
                }
            )

        profitable_items.sort(key=lambda x: x["margin"], reverse=True)
        logger.info(f"Found {len(profitable_items)} profitable items after filtering")

        return profitable_items


async def setup(bot):
    await bot.add_cog(OSRSMargin(bot))
