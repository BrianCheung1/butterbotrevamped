import time

import discord
from discord import app_commands
from discord.ext import commands

# Configuration
MIN_VOLUME_1H = 50_000
MIN_VOLUME_5M = 5_000
MIN_VOLUME_24H = 50_000
TAX_RATE = 0.02
TOP_N = 10
MAX_ITEMS_FEASIBLE = 20_000
MIN_PROFIT_MARGIN = 1
MIN_ROI = 0.5
MAX_ITEM_PRICE = 50_000_000
MIN_RECENT_TRADES = 2

MIN_LIQUIDITY_SCORE = 0.3
MAX_PRICE_VOLATILITY = 0.25
RECENCY_WEIGHT = 0.3
MAX_TRADE_AGE_MINUTES = 60


class OSRSFlips(commands.Cog):
    """OSRS flipping cog using centralized data manager."""

    def __init__(self, bot):
        self.bot = bot
        self.data_manager = bot.osrs_data
        self.debug_stats = {
            "total_items": 0,
            "members_only": 0,
            "has_name": 0,
            "volume_1h_pass": 0,
            "volume_5m_pass": 0,
            "has_prices": 0,
            "price_valid": 0,
            "not_too_expensive": 0,
            "recent_trades": 0,
            "profit_positive": 0,
            "roi_pass": 0,
            "liquidity_pass": 0,
            "final_candidates": 0,
        }

    def calculate_liquidity_score(
        self,
        vol_buy_1h,
        vol_sell_1h,
        vol_buy_5m,
        vol_sell_5m,
        vol_buy_24h,
        vol_sell_24h,
    ):
        """Calculate a liquidity score based on volume consistency and balance."""
        # Volume balance (closer to 1.0 is better)
        buy_sell_balance_1h = min(vol_buy_1h, vol_sell_1h) / max(
            vol_buy_1h, vol_sell_1h, 1
        )
        buy_sell_balance_5m = min(vol_buy_5m, vol_sell_5m) / max(
            vol_buy_5m, vol_sell_5m, 1
        )

        # Recent activity ratio (5m vs 1h)
        recent_activity = min(vol_buy_5m + vol_sell_5m, vol_buy_1h + vol_sell_1h) / max(
            vol_buy_1h + vol_sell_1h, 1
        )

        # 24h consistency (if available)
        consistency_24h = 1.0
        if vol_buy_24h and vol_sell_24h:
            total_24h = vol_buy_24h + vol_sell_24h
            total_1h = vol_buy_1h + vol_sell_1h
            expected_1h = total_24h / 24
            if expected_1h > 0:
                consistency_24h = min(total_1h, expected_1h) / max(
                    total_1h, expected_1h, 1
                )

        # Combined score
        liquidity_score = (
            buy_sell_balance_1h
            + buy_sell_balance_5m
            + recent_activity
            + consistency_24h
        ) / 4
        return liquidity_score

    def calculate_price_stability(self, price_1h, price_5m, price_24h, current_price):
        """Calculate price stability to avoid volatile items."""
        prices = [
            p for p in [price_1h, price_5m, price_24h, current_price] if p and p > 0
        ]
        if len(prices) < 2:
            return 0.8  # More generous default for unknown stability

        avg_price = sum(prices) / len(prices)
        max_deviation = max(abs(p - avg_price) / avg_price for p in prices)

        stability_score = max(0, 1 - (max_deviation / MAX_PRICE_VOLATILITY))
        return stability_score

    def calculate_trade_recency_score(self, low_time, high_time):
        """Score based on how recent the trades are."""
        current_time = int(time.time())
        max_age_seconds = MAX_TRADE_AGE_MINUTES * 60

        recency_scores = []
        for trade_time in [low_time, high_time]:
            if trade_time and trade_time > 0:
                age = current_time - trade_time
                if age <= max_age_seconds:
                    score = max(0, 1 - (age / max_age_seconds))
                    recency_scores.append(score)
                else:
                    recency_scores.append(0)  # Too old
            else:
                recency_scores.append(0)  # No timestamp

        return sum(recency_scores) / len(recency_scores) if recency_scores else 0

    def check_trade_recency(self, low_time, high_time):
        """Check if both buy and sell trades are recent enough for quick flipping."""
        current_time = int(time.time())
        max_age_seconds = MAX_TRADE_AGE_MINUTES * 60

        # Both trades must exist and be recent
        if not low_time or not high_time:
            return False, "Missing trade timestamps"

        if low_time <= 0 or high_time <= 0:
            return False, "Invalid trade timestamps"

        buy_age = current_time - low_time
        sell_age = current_time - high_time

        if buy_age > max_age_seconds:
            return False, f"Buy trade too old ({buy_age // 60} minutes)"

        if sell_age > max_age_seconds:
            return False, f"Sell trade too old ({sell_age // 60} minutes)"

        return (
            True,
            f"Recent trades (Buy: {buy_age // 60}m, Sell: {sell_age // 60}m ago)",
        )

    async def analyze_flips(self, force_refresh: bool = False):
        """
        Analyze all items for flipping opportunities using data manager.

        Args:
            force_refresh: Force bypass cache

        Returns:
            List of flip opportunities
        """
        # Reset debug stats
        self.debug_stats = {key: 0 for key in self.debug_stats.keys()}

        # Fetch all required data using data manager (all cached!)
        try:
            data_1h = await self.data_manager.get_period_data("1h", force_refresh)
            data_5m = await self.data_manager.get_period_data("5m", force_refresh)
            data_24h = await self.data_manager.get_period_data("24h", force_refresh)
            latest_data = await self.data_manager.get_latest_prices(
                force_refresh=force_refresh
            )
            mapping = await self.data_manager.get_mapping(force_refresh)

            data = {
                "1h": data_1h,
                "5m": data_5m,
                "24h": data_24h,
                "latest": latest_data.get("data", {}),
                "mapping": {item["id"]: item for item in mapping},
            }

        except Exception as e:
            self.bot.logger.error(
                f"[OSRSFlips] Error fetching data: {e}", exc_info=True
            )
            raise

        # Analyze flips with debug tracking
        flips = []

        for item_id_str, price_1h in data["1h"].items():
            self.debug_stats["total_items"] += 1

            try:
                item_id = int(item_id_str)
            except ValueError:
                continue

            meta = data["mapping"].get(item_id)
            if not meta:
                continue

            # Members only filter
            if not meta.get("members", False):
                continue
            self.debug_stats["members_only"] += 1

            # Name filter
            name = meta.get("name", "")
            if not name or any(
                skip in name.lower() for skip in ["noted", "damaged", "broken"]
            ):
                continue
            self.debug_stats["has_name"] += 1

            # Get all volume data
            price_5m = data["5m"].get(item_id_str, {})
            price_24h = data["24h"].get(item_id_str, {})
            latest = data["latest"].get(item_id_str, {})

            # Volume analysis
            vol_buy_1h = price_1h.get("lowPriceVolume", 0)
            vol_sell_1h = price_1h.get("highPriceVolume", 0)
            vol_buy_5m = price_5m.get("lowPriceVolume", 0)
            vol_sell_5m = price_5m.get("highPriceVolume", 0)
            vol_buy_24h = price_24h.get("lowPriceVolume", 0)
            vol_sell_24h = price_24h.get("highPriceVolume", 0)

            # Volume filters with tracking
            if vol_buy_1h >= MIN_VOLUME_1H and vol_sell_1h >= MIN_VOLUME_1H:
                self.debug_stats["volume_1h_pass"] += 1
            else:
                continue

            if vol_buy_5m >= MIN_VOLUME_5M and vol_sell_5m >= MIN_VOLUME_5M:
                self.debug_stats["volume_5m_pass"] += 1
            else:
                continue

            # Price analysis
            buy_price = latest.get("low")
            sell_price = latest.get("high")
            low_time = latest.get("lowTime")
            high_time = latest.get("highTime")

            if buy_price and sell_price:
                self.debug_stats["has_prices"] += 1
            else:
                continue

            if buy_price < sell_price:
                self.debug_stats["price_valid"] += 1
            else:
                continue

            # Price limit filter
            if buy_price <= MAX_ITEM_PRICE:
                self.debug_stats["not_too_expensive"] += 1
            else:
                continue

            # Recency filter - check if trades are recent enough for quick flipping
            recent_check, recency_msg = self.check_trade_recency(low_time, high_time)
            if recent_check:
                self.debug_stats["recent_trades"] += 1
            else:
                continue

            # Profit calculations
            ge_limit = meta.get("limit", 1)
            raw_margin = sell_price - buy_price
            tax = int(sell_price * TAX_RATE)
            profit_per_item = raw_margin - tax
            roi = (profit_per_item / buy_price * 100) if buy_price > 0 else 0

            # Profit filters
            if profit_per_item >= MIN_PROFIT_MARGIN:
                self.debug_stats["profit_positive"] += 1
            else:
                continue

            if roi >= MIN_ROI:
                self.debug_stats["roi_pass"] += 1
            else:
                continue

            # Liquidity analysis
            liquidity_score = self.calculate_liquidity_score(
                vol_buy_1h,
                vol_sell_1h,
                vol_buy_5m,
                vol_sell_5m,
                vol_buy_24h,
                vol_sell_24h,
            )

            if liquidity_score >= MIN_LIQUIDITY_SCORE:
                self.debug_stats["liquidity_pass"] += 1
            else:
                continue

            # If we get here, it's a valid flip
            self.debug_stats["final_candidates"] += 1

            # Price stability and recency scores
            avg_low_1h = price_1h.get("avgLowPrice")
            avg_low_5m = price_5m.get("avgLowPrice")
            stability_score = self.calculate_price_stability(
                avg_low_1h, avg_low_5m, price_24h.get("avgLowPrice"), buy_price
            )
            recency_score = self.calculate_trade_recency_score(low_time, high_time)

            # Conservative volume estimation
            conservative_volume = min(
                int(vol_buy_1h * 0.1),
                int(vol_sell_1h * 0.1),
                ge_limit,
                MAX_ITEMS_FEASIBLE,
            )

            if vol_buy_5m > vol_buy_1h * 0.1 and vol_sell_5m > vol_sell_1h * 0.1:
                conservative_volume = int(conservative_volume * 1.2)

            expected_profit = profit_per_item * conservative_volume
            quality_score = (liquidity_score + stability_score + recency_score) / 3
            weighted_profit = int(expected_profit * quality_score)

            # Format timestamps
            last_buy = f"<t:{low_time}:R>" if low_time else "N/A"
            last_sell = f"<t:{high_time}:R>" if high_time else "N/A"

            flips.append(
                {
                    "name": name,
                    "item_id": item_id,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "profit_per_item": profit_per_item,
                    "roi": round(roi, 2),
                    "ge_limit": ge_limit,
                    "conservative_volume": conservative_volume,
                    "expected_profit": expected_profit,
                    "weighted_profit": weighted_profit,
                    "liquidity_score": round(liquidity_score, 2),
                    "stability_score": round(stability_score, 2),
                    "recency_score": round(recency_score, 2),
                    "quality_score": round(quality_score, 2),
                    "vol_buy_1h": vol_buy_1h,
                    "vol_sell_1h": vol_sell_1h,
                    "vol_buy_5m": vol_buy_5m,
                    "vol_sell_5m": vol_sell_5m,
                    "last_buy": last_buy,
                    "last_sell": last_sell,
                    "tax": tax,
                }
            )

        # Sort by weighted profit (highest to lowest)
        flips.sort(key=lambda x: x["weighted_profit"], reverse=True)

        return flips

    @app_commands.command(
        name="osrs-flips",
        description="Find profitable OSRS flipping opportunities with live market data",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def osrs_flip(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            flips = await self.analyze_flips()
        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching data: {e}")
            return

        # Create report embed
        embed = discord.Embed(
            title="🔍 OSRS Flips Analysis",
            description="Top flipping opportunities based on live market data",
            color=discord.Color.gold() if flips else discord.Color.orange(),
        )

        # Add current filter settings
        filter_text = "\n".join(
            [
                f"Min 1H Volume: {MIN_VOLUME_1H:,}",
                f"Min 5M Volume: {MIN_VOLUME_5M:,}",
                f"Min Liquidity Score: {MIN_LIQUIDITY_SCORE}",
                f"Min ROI: {MIN_ROI}%",
                f"Max Trade Age: {MAX_TRADE_AGE_MINUTES} minutes",
            ]
        )
        embed.add_field(name="⚙️ Current Filters", value=filter_text, inline=False)

        if flips:
            embed.add_field(
                name="✅ Found Flips",
                value=f"Found {len(flips)} viable flips! Showing top {min(len(flips), 10)}:",
                inline=False,
            )

            # Show up to 10 items
            items_to_show = min(len(flips), 10)
            for i, flip in enumerate(flips[:items_to_show], 1):
                flip_text = (
                    f"**[{flip['name']}](https://prices.osrs.cloud/item/{flip['item_id']})**\n"
                    f"Buy: {flip['buy_price']:,} → Sell: {flip['sell_price']:,}\n"
                    f"Profit: {flip['profit_per_item']:,} gp ({flip['roi']}% ROI)\n"
                    f"Expected: {flip['expected_profit']:,} gp\n"
                    f"Quality: {flip['quality_score']} | Tax: {flip['tax']:,} gp\n"
                    f"Last Buy: {flip['last_buy']}\n"
                    f"Last Sell: {flip['last_sell']}\n"
                    f"5M Volume - Buy: {flip['vol_buy_5m']:,}, Sell: {flip['vol_sell_5m']:,}"
                )

                embed.add_field(name=f"#{i}", value=flip_text, inline=True)

                if i % 3 == 0 and i < items_to_show:
                    embed.add_field(name="\u200b", value="\u200b", inline=False)
        else:
            embed.add_field(
                name="❌ No Results",
                value="No items passed all filters. Consider relaxing criteria or trying again later.",
                inline=False,
            )

        embed.set_footer(text="Data from OSRS Wiki • Refreshed live")
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(OSRSFlips(bot))
