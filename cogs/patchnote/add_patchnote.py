import os
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.channels import broadcast_embed_to_guilds
from utils.checks import is_owner_check

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class AddPatchNote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="patchnotes", description="Add and display patch notes")
    @app_commands.describe(changes="Separate each change with a ';'")
    @app_commands.check(is_owner_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def patchnotes(
        self,
        interaction: discord.Interaction,
        changes: str,
        attachment: Optional[discord.Attachment] = None,
    ):
        items = [
            item.strip().capitalize() for item in changes.split(";") if item.strip()
        ]
        if not items:
            await interaction.response.send_message(
                "No valid changes provided.", ephemeral=True
            )
            return

        formatted = ";".join(items)
        image_url = (
            attachment.url
            if attachment
            and attachment.content_type
            and attachment.content_type.startswith("image")
            else None
        )
        # Add patch note and get its ID
        patch_id = await self.bot.database.patch_notes_db.add_patch_note(
            interaction.user.id, interaction.user.name, formatted, image_url
        )

        formatted_notes = "\n".join(f"- {change}" for change in items)
        embed = discord.Embed(
            title=f"🛠️ Patch Notes #{patch_id}",
            description=formatted_notes,
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"By {interaction.user.name}")

        if image_url:
            embed.set_image(url=image_url)

        # Send to the invoking user first
        await interaction.response.send_message(embed=embed)

        await broadcast_embed_to_guilds(self.bot, "patchnotes_channel_id", embed)


async def setup(bot):
    await bot.add_cog(AddPatchNote(bot))
