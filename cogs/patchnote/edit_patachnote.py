import os
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.channels import broadcast_embed_to_guilds
from utils.checks import is_owner_check

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class EditPatchNote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="patchnotes-edit", description="Edit a patch note by its ID"
    )
    @app_commands.describe(
        patch_id="The patch note ID to edit",
        changes="New patch note changes separated by ';'",
    )
    @app_commands.check(is_owner_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def patchnotes_edit(
        self,
        interaction: discord.Interaction,
        patch_id: int,
        changes: str,
        attachment: Optional[discord.Attachment] = None,
    ):
        note = await self.bot.database.patch_notes_db.get_patch_note_by_id(patch_id)
        if not note:
            await interaction.response.send_message(
                f"Patch note #{patch_id} not found.", ephemeral=True
            )
            return

        items = [
            item.strip().capitalize() for item in changes.split(";") if item.strip()
        ]
        if not items:
            await interaction.response.send_message(
                "No valid changes provided.", ephemeral=True
            )
            return

        formatted = ";".join(items)

        # Decide which image_url to save
        if (
            attachment
            and attachment.content_type
            and attachment.content_type.startswith("image")
        ):
            image_url = attachment.url
        else:
            # Use previous image_url from DB if no new attachment
            image_url = note["image_url"]

        # Update patch note with both changes and image_url
        await self.bot.database.patch_notes_db.update_patch_note_changes_and_image(
            patch_id, formatted, image_url
        )

        updated_note = await self.bot.database.patch_notes_db.get_patch_note_by_id(
            patch_id
        )

        changes_display = "\n".join(
            f"- {item.strip().capitalize()}"
            for item in updated_note["changes"].split(";")
            if item.strip()
        )
        timestamp_dt = datetime.fromisoformat(updated_note["timestamp"]).replace(
            tzinfo=timezone.utc
        )

        embed = discord.Embed(
            title=f"🛠️ Patch #{updated_note['id']} Notes (Updated)",
            description=changes_display,
            color=discord.Color.green(),
            timestamp=timestamp_dt,
        )
        embed.set_footer(text=f"By {updated_note['author_name']}")

        if updated_note["image_url"]:
            embed.set_image(url=updated_note["image_url"])

        await interaction.response.send_message(
            f"Patch note #{patch_id} updated successfully.", embed=embed
        )

        await broadcast_embed_to_guilds(self.bot, "patchnotes_channel_id", embed)


async def setup(bot):
    await bot.add_cog(EditPatchNote(bot))
