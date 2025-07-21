import os
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.autcomplete import patch_number_autocomplete
from utils.channels import broadcast_embed_to_guilds
from utils.checks import is_owner_check
from utils.formatting import clean_patchnotes

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class EditPatchNote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="patchnotes-edit",
        description="Edit a patch note by its visible number",
    )
    @app_commands.describe(
        patch_number="The visible patch note number to edit (autocomplete enabled)",
        changes="New patch note changes separated by ';'",
        attachment="Optional new image attachment",
    )
    @app_commands.check(is_owner_check)
    @app_commands.guilds(DEV_GUILD_ID)
    @app_commands.autocomplete(patch_number=patch_number_autocomplete)
    async def patchnotes_edit(
        self,
        interaction: discord.Interaction,
        patch_number: int,
        changes: str,
        attachment: Optional[discord.Attachment] = None,
    ):
        entries = await self.bot.database.patch_notes_db.get_all_patch_notes()
        entries.sort(key=lambda e: e["timestamp"], reverse=True)

        index = len(entries) - patch_number
        if index < 0 or index >= len(entries):
            await interaction.response.send_message(
                f"Patch note #{patch_number} not found.", ephemeral=True
            )
            return

        note = entries[index]
        patch_db_id = note["id"]

        db_formatted, embed_formatted = clean_patchnotes(changes)
        if not db_formatted:
            await interaction.response.send_message(
                "No valid changes provided.", ephemeral=True
            )
            return

        if (
            attachment
            and attachment.content_type
            and attachment.content_type.startswith("image")
        ):
            image_url = attachment.url
        else:
            image_url = note["image_url"]

        await self.bot.database.patch_notes_db.update_patch_note_changes_and_image(
            patch_db_id, db_formatted, image_url
        )

        updated_note = await self.bot.database.patch_notes_db.get_patch_note_by_id(
            patch_db_id
        )
        timestamp_dt = datetime.fromisoformat(updated_note["timestamp"]).replace(
            tzinfo=timezone.utc
        )

        embed = discord.Embed(
            title=f"🛠️ Patch #{patch_number} Notes (Updated)",
            description=embed_formatted,
            color=discord.Color.green(),
            timestamp=timestamp_dt,
        )
        embed.set_footer(text=f"By {updated_note['author_name']}")

        if updated_note["image_url"]:
            embed.set_image(url=updated_note["image_url"])

        await interaction.response.send_message(
            f"Patch note #{patch_number} updated successfully.", embed=embed
        )

        await broadcast_embed_to_guilds(self.bot, "patchnotes_channel_id", embed)


async def setup(bot):
    await bot.add_cog(EditPatchNote(bot))
