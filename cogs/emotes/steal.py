import io
import re
import urllib.parse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image

CUSTOM_EMOJI_REGEX = r"<(a?):(\w+):(\d+)>"


class StealApprovalView(discord.ui.View):
    def __init__(self, bot, emoji_data, final_name, requester):
        super().__init__(timeout=600)
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
            await interaction.response.edit_message(
                content=f"✅ Emoji `{self.final_name}` added {new_emoji}", view=None
            )
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

        await interaction.response.edit_message(
            content="❌ Emoji steal request was denied.", view=None
        )
        await self.requester.send("❌ Your emoji steal request was denied.")
        self.handled = True
        self.stop()


class StealEmote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="stealemote",
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
                animated, original_name, emoji_id = match.groups()
                file_ext = "gif" if animated == "a" else "png"
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{file_ext}"
                path = url  # required for .endswith() later
                final_name = name or original_name
            else:
                parsed = urllib.parse.urlparse(emote_or_url)
                path = parsed.path.lower()
                if not path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    return await interaction.followup.send(
                        "❌ URL must end in .png, .jpg, .jpeg, .gif, or .webp"
                    )
                if not name:
                    return await interaction.followup.send(
                        "❌ You must provide a name when using a URL."
                    )
                url = emote_or_url
                final_name = name
        elif attachment:
            if not attachment.filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            ):
                return await interaction.followup.send(
                    "❌ Attachment must be a .png, .jpg, .jpeg, .gif, or .webp image."
                )
            if not name:
                return await interaction.followup.send(
                    "❌ You must provide a name when uploading an image."
                )
            url = attachment.url
            path = urllib.parse.urlparse(url).path.lower()
            final_name = name

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
                    im = im.convert("RGBA")
                    buf = io.BytesIO()
                    im.save(buf, format="PNG")
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

        # Create and send embed with preview
        embed = discord.Embed(
            title="Emoji Steal Request",
            description=f"{interaction.user.mention} requested to add an emoji.\n"
            f"**Name:** `{final_name}`\n"
            f"**Source:** {url}",
            color=discord.Color.orange(),
        )
        embed.set_image(url=url)

        view = StealApprovalView(self.bot, emoji_data, final_name, interaction.user)
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message


async def setup(bot):
    await bot.add_cog(StealEmote(bot))
