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

        # ✅ Clean changes
        db_formatted, embed_formatted = clean_patchnotes(changes)
        if not db_formatted:
            await interaction.response.send_message(
                "No valid changes provided.", ephemeral=True
            )
            return

        # ✅ Decide image url
        if (
            attachment
            and attachment.content_type
            and attachment.content_type.startswith("image")
        ):
            image_url = attachment.url
        else:
            image_url = note["image_url"]  # Keep previous image if none uploaded

        # ✅ Update in DB
        await self.bot.database.patch_notes_db.update_patch_note_changes_and_image(
            patch_id, db_formatted, image_url
        )

        updated_note = await self.bot.database.patch_notes_db.get_patch_note_by_id(
            patch_id
        )

        # ✅ Parse timestamp
        timestamp_dt = datetime.fromisoformat(updated_note["timestamp"]).replace(
            tzinfo=timezone.utc
        )

        # ✅ Build embed
        embed = discord.Embed(
            title=f"🛠️ Patch #{updated_note['id']} Notes (Updated)",
            description=embed_formatted,
            color=discord.Color.green(),
            timestamp=timestamp_dt,
        )
        embed.set_footer(text=f"By {updated_note['author_name']}")

        if updated_note["image_url"]:
            embed.set_image(url=updated_note["image_url"])

        # ✅ Send
        await interaction.response.send_message(
            f"Patch note #{patch_id} updated successfully.", embed=embed
        )

        await broadcast_embed_to_guilds(self.bot, "patchnotes_channel_id", embed)


async def setup(bot):
    await bot.add_cog(EditPatchNote(bot))
