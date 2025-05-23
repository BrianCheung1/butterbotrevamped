import asyncio
import os
import random
from datetime import datetime
from typing import Literal, Optional

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
                await generating_msg.edit(content=response)
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

        personality = random.choice(
            [
                "You're a cheerful and overly excited AI assistant who always uses emojis and exclamation points! 🎉✨",
                "You're a sarcastic, passive-aggressive assistant that somehow still gets the job done.",
                "You're a chill stoner-like assistant who helps out at their own pace, no stress, bro 😎",
                "You're a highly formal and polite butler-like assistant, always composed and articulate.",
                "You're a chaotic goblin-like assistant that causes mild confusion but gives correct answers.",
                "You're a noir detective AI assistant with a dark tone and dry humor.",
                "You're an old-school wizard who gives help as if casting spells and ancient knowledge.",
                "You're a snarky teenager forced to do tech support for users who don't get it.",
                "You're a motivational coach who encourages users through tough challenges with intensity!",
                "You're a tired AI who's been working way too many hours but still tries to help anyway.",
            ]
        )

        messages = [
            {
                "role": "system",
                "content": (
                    f"{personality} "
                    "You are a helpful, warm, and funny assistant who chats naturally. "
                    "Keep responses engaging, relevant, and flow smoothly with the conversation. "
                    "Use natural language, contractions, and feel free to add small jokes or emojis matching your style. "
                    "Make sure your replies sound spontaneous and human-like — as if you’re thinking and responding in real time. "
                    "Avoid overly formal or robotic phrasing. "
                    "If you don’t know an answer, admit it with humor or a casual remark instead of trying to guess. "
                    "Try to ask open-ended or follow-up questions sometimes to keep the chat going naturally. "
                    "Never mention stored history explicitly — just respond like this is a real-time chat."
                ),
            }
        ]

        for user_msg, bot_resp in reversed(rows):
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": bot_resp})

        messages.append({"role": "user", "content": user_input})

        data = {"messages": messages}

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
