import time
from datetime import datetime, timezone
from typing import Dict

import discord
from discord.ext import commands, tasks
from logger import setup_logger
from utils.channels import broadcast_embed_to_guilds

logger = setup_logger("OSRSMargin")

# === FILTERS ===
MIN_VOLUME = 400
MAX_PRICE = 20_000_000
CHECK_INTERVAL = 60
TOP_ITEMS_COUNT = 15

# Margin tiers for ALERTS
ALERT_MARGIN_TIERS = [
    {"price_min": 1_000_000, "price_max": 5_000_000, "min_margin": 200_000},
    {"price_min": 5_000_000, "price_max": 10_000_000, "min_margin": 500_000},
    {"price_min": 10_000_000, "price_max": 15_000_000, "min_margin": 750_000},
    {"price_min": 15_000_000, "price_max": float("inf"), "min_margin": 1_000_000},
]

# Below average tiers for ALERTS
BELOW_AVG_TIERS = [
    {"price_min": 0, "price_max": 1_000_000, "min_margin": 150_000},
    {"price_min": 1_000_000, "price_max": 5_000_000, "min_margin": 250_000},
    {"price_min": 5_000_000, "price_max": 10_000_000, "min_margin": 1_000_000},
    {"price_min": 10_000_000, "price_max": 15_000_000, "min_margin": 2_000_000},
    {"price_min": 15_000_000, "price_max": float("inf"), "min_margin": 5_000_000},
]

# Below average tiers for ALERTS
BELOW_AVG_TIERS_MARGINS = [
    {"price_min": 0, "price_max": 1_000_000, "min_margin": 5_000},
    {"price_min": 1_000_000, "price_max": 5_000_000, "min_margin": 10_000},
    {"price_min": 5_000_000, "price_max": 10_000_000, "min_margin": 50_000},
    {"price_min": 10_000_000, "price_max": 15_000_000, "min_margin": 100_000},
    {"price_min": 15_000_000, "price_max": float("inf"), "min_margin": 150_000},
]


def get_min_margin_for_price(price: int) -> int:
    """Get the minimum margin required for ALERTS based on item price."""
    for tier in ALERT_MARGIN_TIERS:
        if tier["price_min"] <= price < tier["price_max"]:
            return tier["min_margin"]
    return ALERT_MARGIN_TIERS[-1]["min_margin"]


def get_min_below_avg_for_price(price: int) -> int:
    """Get the minimum margin (current buy to avg sell) required for below-avg alerts."""
    for tier in BELOW_AVG_TIERS:
        if tier["price_min"] <= price < tier["price_max"]:
            return tier["min_margin"]
    return BELOW_AVG_TIERS[-1]["min_margin"]


def get_min_below_avg_margin_for_price(price: int) -> int:
    """Get the minimum margin (current buy to avg sell) required for below-avg alerts."""
    for tier in BELOW_AVG_TIERS_MARGINS:
        if tier["price_min"] <= price < tier["price_max"]:
            return tier["min_margin"]
    return BELOW_AVG_TIERS_MARGINS[-1]["min_margin"]


class OSRSMargin(commands.Cog):
    """Cog to monitor OSRS GE margins and send alerts."""

    def __init__(self, bot):
        self.bot = bot
        self.data_manager = bot.osrs_data

        # Separate tracking for each alert type
        self.top_margin_item_ids = set()
        self.below_avg_item_ids = set()

        self._first_run = True
        self.check_new_items.start()

    def cog_unload(self):
        """Stop the background task when cog is unloaded."""
        self.check_new_items.cancel()

    @tasks.loop(seconds=CHECK_INTERVAL)
    async def check_new_items(self):
        """Background task to check for both high margin and below-average items."""
        try:
            if self._first_run:
                logger.info("First run — populating baseline items only")
                self._first_run = False

                # Fetch shared API data ONCE for initialization
                latest_data = await self.data_manager.get_latest_prices(
                    force_refresh=True
                )
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

                # Initialize margin tracking
                margin_result = await self._get_profitable_items(
                    shared_data=shared_data
                )
                if not isinstance(margin_result, str) and margin_result:
                    self.top_margin_item_ids = {
                        item["id"] for item in margin_result[:TOP_ITEMS_COUNT]
                    }
                    logger.info(
                        f"✓ Initialized {len(self.top_margin_item_ids)} high margin items"
                    )

                # Initialize below-average tracking
                below_avg_result = await self._get_below_average_items(
                    shared_data=shared_data
                )
                if not isinstance(below_avg_result, str) and below_avg_result:
                    self.below_avg_item_ids = {
                        item["id"] for item in below_avg_result[:TOP_ITEMS_COUNT]
                    }
                    logger.info(
                        f"✓ Initialized {len(self.below_avg_item_ids)} below-avg items"
                    )

                logger.info(
                    f"First run complete: {len(self.top_margin_item_ids)} margin items, "
                    f"{len(self.below_avg_item_ids)} below-avg items tracked"
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

            # ========== ALERT TYPE 1: High Margin Items ==========
            profitable_items = await self._get_profitable_items(shared_data=shared_data)
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

            # ========== ALERT TYPE 2: Below Average Items ==========
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

            # Update tracking sets
            self.top_margin_item_ids = current_margin_ids
            self.below_avg_item_ids = current_below_avg_ids

        except Exception as e:
            logger.error(f"Error in monitoring task: {e}", exc_info=True)

    def _calculate_stats(self, history: Dict) -> Dict:
        """Calculate 24h and 7d statistics from timeseries data."""
        from statistics import mean

        stats = {}

        timeframes = {
            "24h": ("5m", 288),
            "7d": ("1h", 168),
        }

        for period, (step, count) in timeframes.items():
            data = history.get(step, [])[-count:] if history.get(step) else []

            if not data:
                stats[period] = {}
                continue

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

    @check_new_items.before_loop
    async def before_check_new_items(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    async def _get_below_average_items(self, shared_data=None):
        """Get items that are significantly below their average buy price."""
        try:
            if shared_data:
                price_data = shared_data["price_data"]
                mapping = shared_data["mapping"]
                volume_data = shared_data["volume_data"]
            else:
                logger.info("Fetching OSRS data for below-average check...")
                latest_data = await self.data_manager.get_latest_prices(
                    force_refresh=True
                )
                price_data = latest_data.get("data", {})
                mapping = await self.data_manager.get_mapping(force_refresh=True)
                item_names = [item["name"] for item in mapping]
                volume_data = await self.data_manager.get_weirdgloop_volumes(
                    item_names, force_refresh=True
                )

            if not price_data or not mapping or not volume_data:
                return "❌ Missing OSRS API data"

        except Exception as e:
            logger.error(f"Error fetching OSRS data for below-avg: {e}", exc_info=True)
            return f"❌ Error fetching data from OSRS APIs: {str(e)}"

        below_avg_items = []
        total_items = len(price_data)
        processed = 0

        logger.info(f"Checking {total_items} items for below-average prices...")

        for item_id_str, price_info in price_data.items():
            processed += 1
            if processed % 500 == 0:
                logger.info(
                    f"Progress: {processed}/{total_items} items processed below average"
                )

            try:
                item_id = int(item_id_str)
            except ValueError:
                continue

            low_price = price_info.get("low")
            high_price = price_info.get("high")
            high_time = price_info.get("highTime")
            low_time = price_info.get("lowTime")

            if not high_price or not low_price:
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
            min_margin = get_min_below_avg_margin_for_price(low_price)

            if margin <= min_margin:
                continue

            # Get historical data
            try:
                item_data = await self.data_manager.get_comprehensive_item_data(item_id)
                historical_stats = self._calculate_stats(item_data["history"])
            except Exception as e:
                logger.debug(f"No history for {item_name}: {e}")
                continue

            avg_buy_24h = int(historical_stats.get("24h", {}).get("avg_low", 0))
            avg_buy_7d = int(historical_stats.get("7d", {}).get("avg_low", 0))
            avg_sell_24h = int(historical_stats.get("24h", {}).get("avg_high", 0))
            avg_sell_7d = int(historical_stats.get("7d", {}).get("avg_high", 0))

            avg_buy = avg_buy_24h or avg_buy_7d
            avg_sell = avg_sell_24h or avg_sell_7d

            if not avg_buy or avg_buy <= 0:
                continue

            below_avg = avg_buy - low_price

            if below_avg <= 0:
                continue

            if not avg_sell or avg_sell <= low_price:
                continue

            ge_tax_avg = avg_sell * 0.02
            margin_to_avg_sell = round((avg_sell - ge_tax_avg) - low_price)
            roi_to_avg_sell = (
                round((margin_to_avg_sell / low_price) * 100, 2) if low_price > 0 else 0
            )

            min_required_margin = get_min_below_avg_for_price(low_price)

            if margin_to_avg_sell < min_required_margin:
                continue

            discount_pct = (below_avg / avg_buy) * 100

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

        below_avg_items.sort(key=lambda x: x["margin_to_avg_sell"], reverse=True)
        logger.info(f"Found {len(below_avg_items)} items below average")

        return below_avg_items

    async def _get_profitable_items(self, shared_data=None):
        """Get list of profitable items using tiered margin requirements."""
        try:
            if shared_data:
                price_data = shared_data["price_data"]
                mapping = shared_data["mapping"]
                volume_data = shared_data["volume_data"]
            else:
                logger.info("Fetching OSRS data...")
                latest_data = await self.data_manager.get_latest_prices(
                    force_refresh=True
                )
                price_data = latest_data.get("data", {})
                mapping = await self.data_manager.get_mapping(force_refresh=True)
                item_names = [item["name"] for item in mapping]
                volume_data = await self.data_manager.get_weirdgloop_volumes(
                    item_names, force_refresh=True
                )

            if not price_data or not mapping or not volume_data:
                return "❌ Missing OSRS API data"

        except Exception as e:
            logger.error(f"Error fetching OSRS data: {e}", exc_info=True)
            return f"❌ Error fetching data from OSRS APIs: {str(e)}"

        profitable_items = []
        total_items = len(price_data)
        processed = 0
        logger.info(f"Checking {total_items} items for margin prices...")
        for item_id_str, price_info in price_data.items():
            processed += 1
            if processed % 500 == 0:
                logger.info(
                    f"Progress: {processed}/{total_items} items processed margin"
                )
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
            min_margin = get_min_margin_for_price(low_price)

            if margin <= min_margin:
                continue

            roi = (margin / low_price) * 100 if low_price > 0 else 0

            historical_stats = {}
            try:
                item_data = await self.data_manager.get_comprehensive_item_data(item_id)
                historical_stats = self._calculate_stats(item_data["history"])
            except Exception as e:
                logger.debug(f"No history for {item_name}: {e}")
                continue

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
