from discord.ext import commands
from discord import app_commands
import discord
from datetime import datetime, timezone
from utils.checks import is_owner_check, is_owner_or_mod_check
from typing import Optional
import os

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class PatchNotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="patchnotes", description="Add and display patch notes")
    @app_commands.describe(changes="Separate each change with a ';'")
    @app_commands.check(is_owner_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def patchnotes(self, interaction: discord.Interaction, changes: str):
        items = [
            item.strip().capitalize() for item in changes.split(";") if item.strip()
        ]
        if not items:
            await interaction.response.send_message(
                "No valid changes provided.", ephemeral=True
            )
            return

        formatted = ";".join(items)

        # Add patch note and get its ID
        patch_id = await self.bot.database.patch_notes_db.add_patch_note(
            interaction.user.id, interaction.user.name, formatted
        )

        formatted_notes = "\n".join(f"- {change}" for change in items)
        embed = discord.Embed(
            title=f"🛠️ Patch Notes #{patch_id}",
            description=formatted_notes,
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"By {interaction.user.name}")

        # Send to the invoking user first
        await interaction.response.send_message(embed=embed)

        # Now broadcast to all guilds that have a patch notes channel set
        for guild in self.bot.guilds:
            channel_id = await self.bot.database.guild_db.get_channel(
                guild.id, "patchnotes_channel_id"
            )
            if not channel_id:
                continue

            channel = guild.get_channel(channel_id)
            if channel is None:
                continue

            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                self.bot.logger.warning(
                    f"Missing permission to send messages in {channel.name} ({channel.id})"
                )
            except discord.HTTPException as e:
                self.bot.logger.error(f"Failed to send patch notes message: {e}")

    @app_commands.command(name="patchnotes-view", description="View saved patch notes")
    @app_commands.describe(patch_id="(Optional) Specific patch note ID to view")
    async def patchnotes_view(
        self, interaction: discord.Interaction, patch_id: Optional[int] = None
    ):
        await interaction.response.defer()

        if patch_id is not None:
            # Show a single patch note by ID
            entry = await self.bot.database.patch_notes_db.get_patch_note_by_id(
                patch_id
            )
            if not entry:
                await interaction.followup.send(
                    f"Patch note #{patch_id} not found.", ephemeral=True
                )
                return

            changes = "\n".join(
                f"- {item.strip().capitalize()}"
                for item in entry["changes"].split(";")
                if item.strip()
            )
            timestamp_dt = datetime.fromisoformat(entry["timestamp"]).replace(
                tzinfo=timezone.utc
            )

            embed = discord.Embed(
                title=f"🛠️ Patch Notes #{entry['id']}",
                description=changes,
                color=discord.Color.blue(),
                timestamp=timestamp_dt,
            )
            embed.set_footer(text=f"By {entry['author_name']}")

            await interaction.followup.send(embed=embed)

        else:
            # Show all patch notes with pagination
            entries = await self.bot.database.patch_notes_db.get_all_patch_notes()

            if not entries:
                await interaction.followup.send("No patch notes available yet.")
                return

            view = PatchNotesView(entries, interaction.user)
            embed = view.create_embed()
            await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(
        name="patchnotes-delete", description="Delete a patch note by its ID"
    )
    @app_commands.describe(patch_id="The patch note ID to delete")
    @app_commands.check(is_owner_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def patchnotes_delete(self, interaction: discord.Interaction, patch_id: int):
        # Check if patch note exists
        note = await self.bot.database.patch_notes_db.get_patch_note_by_id(patch_id)
        if not note:
            await interaction.response.send_message(
                f"Patch note #{patch_id} not found.", ephemeral=True
            )
            return

        # Delete patch note
        await self.bot.database.patch_notes_db.delete_patch_note_by_id(patch_id)
        await interaction.response.send_message(
            f"Patch note #{patch_id} deleted successfully."
        )

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
        self, interaction: discord.Interaction, patch_id: int, changes: str
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
        await self.bot.database.patch_notes_db.update_patch_note_changes(
            patch_id, formatted
        )

        # Fetch the updated note again
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

        await interaction.response.send_message(
            f"Patch note #{patch_id} updated successfully.", embed=embed
        )

        # Broadcast the updated patch note to all guilds with patchnotes channel set
        for guild in self.bot.guilds:
            channel_id = await self.bot.database.guild_db.get_channel(
                guild.id, "patchnotes_channel_id"
            )
            if not channel_id:
                continue

            channel = guild.get_channel(channel_id)
            if channel is None:
                continue

            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                self.bot.logger.warning(
                    f"Missing permission to send messages in {channel.name} ({channel.id})"
                )
            except discord.HTTPException as e:
                self.bot.logger.error(f"Failed to send patch notes update message: {e}")

    @app_commands.command(
        name="set-patchnotes-channel",
        description="Set the current channel as the patch notes announcement channel (admin only).",
    )
    @app_commands.check(is_owner_or_mod_check)
    async def set_patchnotes_channel(
        self,
        interaction: discord.Interaction,
    ):
        await self.bot.database.guild_db.set_channel(
            guild_id=interaction.guild.id,
            channel_type="patchnotes_channel_id",
            channel_id=interaction.channel.id,
        )

        await interaction.response.send_message(
            f"✅ Patch Notes announcement channel has been set to {interaction.channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="remove-patchnotes-channel",
        description="Unset the patch notes announcement channel (admin only).",
    )
    @app_commands.check(is_owner_or_mod_check)
    async def remove_patchnotes_channel(
        self,
        interaction: discord.Interaction,
    ):
        removed = await self.bot.database.guild_db.remove_channel(
            guild_id=interaction.guild.id,
            channel_type="patchnotes_channel_id",
        )

        if removed:
            msg = "✅ Patch Notes announcement channel has been unset."
        else:
            msg = "ℹ️ Patch Notes announcement channel was not set."

        await interaction.response.send_message(msg, ephemeral=True)


class PatchNotesView(discord.ui.View):
    def __init__(self, entries: list[dict], user: discord.User):
        super().__init__(timeout=60)
        self.entries = entries
        self.user = user
        self.page = 0
        self.max_page = len(entries) - 1
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page == self.max_page

    def create_embed(self) -> discord.Embed:
        entry = self.entries[self.page]

        changes = "\n".join(
            f"- {item.strip().capitalize()}"
            for item in entry["changes"].split(";")
            if item.strip()
        )
        timestamp_dt = datetime.fromisoformat(entry["timestamp"]).replace(
            tzinfo=timezone.utc
        )

        embed = discord.Embed(
            title=f"🛠️ Patch #{entry['id']} Notes",
            description=changes,
            color=discord.Color.blue(),
            timestamp=timestamp_dt,
        )
        embed.set_footer(
            text=f"By {entry['author_name']} • Page {self.page + 1}/{self.max_page + 1}"
        )
        return embed

    @discord.ui.button(label="⬅ Previous", style=discord.ButtonStyle.gray)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.user:
            await interaction.response.send_message(
                "You're not allowed to use these buttons.", ephemeral=True
            )
            return

        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="➡ Next", style=discord.ButtonStyle.gray)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.user:
            await interaction.response.send_message(
                "You're not allowed to use these buttons.", ephemeral=True
            )
            return

        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


async def setup(bot):
    await bot.add_cog(PatchNotes(bot))
