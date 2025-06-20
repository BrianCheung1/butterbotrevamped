import io
import os
import re
import time
import urllib.parse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image

CUSTOM_EMOJI_REGEX = r"<(a?):(\w+):(\d+)>"


class StealApprovalView(discord.ui.View):
    def __init__(self, bot, emoji_data, final_name, requester):
        super().__init__(timeout=86400)
        self.bot = bot
        self.emoji_data = emoji_data
        self.final_name = final_name
        self.requester = requester
        self.handled = False
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_emojis_and_stickers:
            await interaction.response.send_message(
                "❌ You must be a moderator to approve or deny this.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        if not self.handled and self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(
                    content="⏳ This emoji steal request has expired due to no response.",
                    view=self,
                )
                await self.requester.send(
                    "⚠️ Your emoji steal request expired without a moderator response."
                )
            except Exception:
                pass

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.success)
    async def approve(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.handled:
            return await interaction.response.send_message(
                "This request has already been handled.", ephemeral=True
            )

        try:
            new_emoji = await interaction.guild.create_custom_emoji(
                name=self.final_name,
                image=self.emoji_data,
                reason=f"Approved by {interaction.user} for {self.requester}",
            )

            # Emoji slot info
            emoji_limit = interaction.guild.emoji_limit
            static = [e for e in interaction.guild.emojis if not e.animated]
            animated = [e for e in interaction.guild.emojis if e.animated]

            static_remaining = emoji_limit - len(static)
            animated_remaining = emoji_limit - len(animated)

            # Modify the original embed
            embed = self.message.embeds[0]
            embed.title = "✅ Emoji Approved"
            embed.color = discord.Color.green()
            embed.description = (
                f"{self.requester.mention}'s emoji request was approved by {interaction.user.mention}.\n"
                f"**Name:** `{self.final_name}`\n"
                f"{new_emoji} **has been added.**\n\n"
                f"📊 **Emoji slots remaining:**\n"
                f"- Static: `{static_remaining}/{emoji_limit}`\n"
                f"- Animated: `{animated_remaining}/{emoji_limit}`"
            )

            for child in self.children:
                child.disabled = True

            await interaction.response.edit_message(embed=embed, view=self)
            await self.requester.send(
                f"✅ Your emoji `{self.final_name}` was approved and added to the server: {new_emoji}"
            )
        except Exception as e:
            await interaction.response.edit_message(
                content=f"❌ Failed to add emoji: {e}", view=None
            )
            await self.requester.send(
                "❌ Your emoji request was approved, but the upload failed."
            )

        self.handled = True
        self.stop()

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.handled:
            return await interaction.response.send_message(
                "This request has already been handled.", ephemeral=True
            )

        embed = self.message.embeds[0]
        embed.title = "❌ Emoji Denied"
        embed.color = discord.Color.red()
        embed.description = (
            f"{self.requester.mention}'s emoji request was denied by {interaction.user.mention}.\n"
            f"**Name:** `{self.final_name}`"
        )

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        await self.requester.send("❌ Your emoji steal request was denied.")

        self.handled = True
        self.stop()


class StealEmote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="steal-emote",
        description="Request to upload an emoji from an emoji, image URL, or uploaded image.",
    )
    @app_commands.describe(
        emote_or_url="Custom emoji or image URL (.png, .jpg, .gif, .webp)",
        name="Name for the emoji (required for URLs/attachments)",
        attachment="Optional image upload (.png/.jpg/.gif/.webp)",
    )
    async def steal_emote(
        self,
        interaction: discord.Interaction,
        emote_or_url: str = None,
        name: str = None,
        attachment: discord.Attachment = None,
    ):
        await interaction.response.defer()

        if not emote_or_url and not attachment:
            return await interaction.followup.send(
                "❌ You must provide either a custom emoji, image URL, or upload an image."
            )

        # Parse emoji
        if emote_or_url:
            match = re.match(CUSTOM_EMOJI_REGEX, emote_or_url)
            if match:
                # It's a custom Discord emoji
                animated, original_name, emoji_id = match.groups()
                file_ext = "gif" if animated == "a" else "png"
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{file_ext}"
                path = url  # Needed for .endswith check later
                final_name = name or original_name
            else:
                # It's a direct image URL
                parsed = urllib.parse.urlparse(emote_or_url)
                path = parsed.path.lower()

                if not path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    return await interaction.followup.send(
                        "❌ URL must end in .png, .jpg, .jpeg, .gif, or .webp"
                    )

                url = emote_or_url

                if not name:
                    base = os.path.basename(path)
                    final_name = (
                        os.path.splitext(base)[0].lower().replace(" ", "_")[:32]
                    )
                else:
                    final_name = name
        elif attachment:
            # Handle uploaded file
            path = attachment.filename.lower()

            if not path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                return await interaction.followup.send(
                    "❌ Attachment must be a .png, .jpg, .jpeg, .gif, or .webp image."
                )

            url = attachment.url

            if not name:
                base = os.path.basename(path)
                final_name = os.path.splitext(base)[0].lower().replace(" ", "_")[:32]
            else:
                final_name = name
        else:
            return await interaction.followup.send(
                "❌ You must provide an emoji, image URL, or upload a file."
            )

        # Download and convert if needed
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await interaction.followup.send(
                            "❌ Failed to fetch the image."
                        )
                    image_data = await resp.read()

            if path.endswith(".webp"):
                with Image.open(io.BytesIO(image_data)) as im:
                    if im.mode != "RGBA":
                        im = im.convert("RGBA")  # Preserve transparency
                    buf = io.BytesIO()
                    im.save(buf, format="PNG")  # Always save as PNG for alpha support
                    buf.seek(0)
                    emoji_data = buf.read()
            else:
                emoji_data = image_data

            if len(emoji_data) > 256 * 1024:
                return await interaction.followup.send(
                    "❌ Image too large. Must be under 256KB for Discord emojis."
                )
        except Exception as e:
            return await interaction.followup.send(f"❌ Failed to process image: {e}")

        expires_at = int(time.time()) + 86400

        embed = discord.Embed(
            title="Emoji Steal Request",
            description=(
                f"{interaction.user.mention} requested to add an emoji.\n"
                f"**Name:** `{final_name}`\n"
                f"**Source:** {url}\n"
                f"⏳ **Expires:** <t:{expires_at}:R>"
            ),
            color=discord.Color.orange(),
        )
        embed.set_image(url=url)

        view = StealApprovalView(self.bot, emoji_data, final_name, interaction.user)
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message


async def setup(bot):
    await bot.add_cog(StealEmote(bot))
