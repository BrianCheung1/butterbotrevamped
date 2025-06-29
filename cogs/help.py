from collections import defaultdict
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

MODULES_PER_PAGE = 2  # You can change this to fit your layout better


class HelpView(discord.ui.View):
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.current_page = 0

        self.prev_button.disabled = True
        if len(embeds) == 1:
            self.next_button.disabled = True

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.blurple)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page -= 1
        self.next_button.disabled = False
        self.prev_button.disabled = self.current_page == 0
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page], view=self
        )

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.blurple)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page += 1
        self.prev_button.disabled = False
        self.next_button.disabled = self.current_page == len(self.embeds) - 1
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page], view=self
        )


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="help", description="List all commands grouped by category"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def help_command(self, interaction: discord.Interaction):
        grouped_commands = defaultdict(list)
        for cmd in self.bot.tree.walk_commands():
            cog = cmd.binding
            module = (
                getattr(cog, "__module__", "uncategorized") if cog else "uncategorized"
            )
            module = module.split(".")[1] if module.startswith("cogs.") else module
            grouped_commands[module].append(cmd)

        sorted_modules = sorted(grouped_commands.items())
        pages = []
        for i in range(0, len(sorted_modules), MODULES_PER_PAGE):
            embed = discord.Embed(
                title="📖 Help Menu",
                description="Here's a categorized list of commands:",
                color=discord.Color.green(),
            )
            for module, cmds in sorted_modules[i : i + MODULES_PER_PAGE]:
                command_list = "\n".join(
                    f"• `/{c.name}` — {c.description or 'No description'}" for c in cmds
                )
                embed.add_field(name=f"📁 `{module}`", value=command_list, inline=False)
            embed.set_footer(
                text=f"Page {len(pages)+1}/{(len(sorted_modules)-1)//MODULES_PER_PAGE+1}"
            )
            pages.append(embed)

        await interaction.response.send_message(embed=pages[0], view=HelpView(pages))


async def setup(bot):
    await bot.add_cog(Help(bot))
