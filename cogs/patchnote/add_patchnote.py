import os
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.channels import broadcast_embed_to_guilds
from utils.checks import is_owner_check
from utils.formatting import clean_patchnotes

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class AddPatchNote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="patchnote-add", description="Add and display patch notes"
    )
    @app_commands.describe(changes="Separate each change with a ';'")
    @app_commands.check(is_owner_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def patchnotes(
        self,
        interaction: discord.Interaction,
        changes: str,
        attachment: Optional[discord.Attachment] = None,
    ):
        # ✅ Clean and format changes
        db_formatted, embed_formatted = clean_patchnotes(changes)
        if not db_formatted:
            await interaction.response.send_message(
                "No valid changes provided.", ephemeral=True
            )
            return

        # ✅ Handle image
        image_url = (
            attachment.url
            if attachment
            and attachment.content_type
            and attachment.content_type.startswith("image")
            else None
        )

        # ✅ Save to DB
        patch_id = await self.bot.database.patch_notes_db.add_patch_note(
            interaction.user.id, interaction.user.name, db_formatted, image_url
        )

        # ✅ Fetch all patch notes and sort descending by timestamp (latest first)
        entries = await self.bot.database.patch_notes_db.get_all_patch_notes()
        entries.sort(key=lambda e: e["timestamp"], reverse=True)

        # ✅ Find display number of the newly added patch note
        display_number = None
        for i, entry in enumerate(entries):
            if entry["id"] == patch_id:
                display_number = len(entries) - i
                break
        if display_number is None:
            display_number = 1  # fallback if not found

        # ✅ Build embed with display_number instead of patch_id
        embed = discord.Embed(
            title=f"🛠️ Patch Notes #{display_number}",
            description=embed_formatted,
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"By {interaction.user.name}")

        if image_url:
            embed.set_image(url=image_url)

        # ✅ Send
        await interaction.response.send_message(embed=embed)
        await broadcast_embed_to_guilds(self.bot, "patchnotes_channel_id", embed)


async def setup(bot):
    await bot.add_cog(AddPatchNote(bot))
