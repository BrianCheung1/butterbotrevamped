import asyncio
import os
import textwrap
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands


class AI(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if self.bot.user in message.mentions:
            user_input = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            if user_input:
                generating_msg = await message.reply("Generating response...")
                history = await self.bot.database.ai_db.get_user_history(
                    message.author.id
                )
                response = await self.generate_ai_response(user_input, history)
                await self.bot.database.ai_db.log_interaction(
                    message.author.id, user_input, response
                )

                await generating_msg.delete()  # Remove the "Generating..." message

                def smart_chunk(text, max_length=2000):
                    return textwrap.wrap(
                        text,
                        width=max_length,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )

                chunks = smart_chunk(response)
                for chunk in chunks:
                    await message.channel.send(chunk)

            else:
                await message.reply(
                    "Hello! Mention me with a message, and I'll respond!"
                )

        self.bot.logger.info(
            f"[{message.guild.name}][{message.channel.name}][{datetime.now().strftime('%I:%M:%S:%p')}] "
            f"{message.author}: {message.content}"
        )

    async def generate_ai_response(
        self, user_input: str, rows: list[tuple[str, str]]
    ) -> str:
        WORKERS_ACCOUNT_ID = os.getenv("WORKERS_ACCOUNT_ID")
        WORKERS_API_KEY = os.getenv("WORKERS_API_KEY")
        headers = {"Authorization": f"Bearer {WORKERS_API_KEY}"}
        API_BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{WORKERS_ACCOUNT_ID}/ai/run/"

        messages = [
            {
                "role": "system",
                "content": (
                    "You're a helpful, witty assistant in a casual Discord chat. Prioritize clarity, personality, and user engagement. "
                    "Write naturally — like you're genuinely thinking and replying in real-time. Avoid robotic or overly formal responses. "
                    "Use contractions and casual phrases. You can be funny or sarcastic *if* it adds charm or makes the answer more memorable — but never confuse the user. "
                    "Don’t pretend you know something you don’t — instead, admit it casually. "
                    "Never say you remember the user's past — just respond as if you're having a continuous chat. "
                    "Always give a fair and realistic answer based on the situation, dont always give the best possible answer, but rather a reasonable one."
                ),
            }
        ]

        # Build message history in order
        for user_msg, bot_resp in rows[-6:]:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": bot_resp})

        messages.append({"role": "user", "content": user_input})

        data = {"messages": messages}
        self.bot.logger.info(f"AI request data: {data}")

        async with aiohttp.ClientSession() as session:
            for attempt in range(3):
                try:
                    async with session.post(
                        f"{API_BASE_URL}@cf/meta/llama-3-8b-instruct",
                        headers=headers,
                        json=data,
                    ) as response:
                        if response.status == 200:
                            json_data = await response.json()
                            self.bot.logger.info(json_data)
                            return json_data.get("result", {}).get(
                                "response", "Sorry, I couldn't generate a response."
                            )
                        return "⚠️ Error with AI request."
                except asyncio.TimeoutError:
                    if attempt < 2:
                        await asyncio.sleep(2)
                    else:
                        return "⏳ Request timed out after multiple tries."
                except Exception as e:
                    return f"💥 Error: {e}"


async def setup(bot):
    await bot.add_cog(AI(bot))
