import asyncio
import os
import re
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
from logger import setup_logger

logger = setup_logger("AIResponse")


class AIResponse(commands.Cog):
    """AI chatbot that responds to direct mentions in Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("WORKERS_API_KEY")
        self.account_id = os.getenv("WORKERS_ACCOUNT_ID")
        self.model = "@cf/meta/llama-3-8b-instruct"
        self.api_base = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/"
        )

        # Typing timeout to show bot is thinking
        self.typing_timeout = 15

        if not self.api_key or not self.account_id:
            logger.error("Missing WORKERS_API_KEY or WORKERS_ACCOUNT_ID in environment")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages and respond if bot is mentioned."""
        # Ignore bot messages
        if message.author.bot:
            return

        # Ignore if no mentions at all
        if not message.mentions:
            return

        # Check if THIS BOT was mentioned
        if self.bot.user not in message.mentions:
            return

        # Extract the message content, removing the bot mention
        user_input = self._clean_mention(message.content, self.bot.user.id)

        if not user_input:
            await message.reply(
                "Hey! Mention me with a message and I'll respond. What's on your mind?"
            )
            return

        # Show typing indicator while generating response
        async with message.channel.typing():
            try:
                # Get conversation history
                history = await self.bot.database.ai_db.get_user_history(
                    message.author.id
                )

                # Generate AI response
                response = await self.generate_ai_response(user_input, history)

                if not response:
                    await message.reply(
                        "⚠️ Hmm, I couldn't generate a response. Try again?"
                    )
                    return

                # Log the interaction
                await self.bot.database.ai_db.log_interaction(
                    message.author.id, user_input, response
                )

                # Send response in chunks if needed
                for chunk in self.smart_chunk(response):
                    await message.reply(chunk, mention_author=False)

            except Exception as e:
                logger.error(f"Error generating AI response: {e}", exc_info=True)
                await message.reply(
                    "💥 Oops, something went wrong. Try again in a moment?"
                )

    def _clean_mention(self, content: str, bot_id: int) -> str:
        """
        Remove bot mention from message content.
        Handles both <@bot_id> and <@!bot_id> formats.
        """
        # Remove mention patterns
        content = re.sub(rf"<@!?{bot_id}>", "", content)
        return content.strip()

    def smart_chunk(self, text: str, max_length: int = 2000) -> list[str]:
        """
        Split text into chunks for Discord (2000 char limit).
        Tries to break on logical boundaries (sentences, paragraphs).
        """
        if len(text) <= max_length:
            return [text]

        chunks = []
        current_chunk = ""

        # Split by paragraphs first
        paragraphs = text.split("\n\n")

        for paragraph in paragraphs:
            # If a single paragraph is too long, split by sentences
            if len(paragraph) > max_length:
                sentences = re.split(r"(?<=[.!?])\s+", paragraph)
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 2 <= max_length:
                        current_chunk += sentence + " "
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "
            else:
                if len(current_chunk) + len(paragraph) + 2 <= max_length:
                    current_chunk += paragraph + "\n\n"
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = paragraph + "\n\n"

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    async def generate_ai_response(
        self, user_input: str, history: list[tuple[str, str]]
    ) -> Optional[str]:
        """
        Generate AI response using Cloudflare Workers AI.

        Args:
            user_input: User's message
            history: List of (user_message, bot_response) tuples

        Returns:
            AI-generated response or None if error
        """
        try:
            # Build conversation messages
            messages = self._build_messages(user_input, history)

            # Make API request
            response = await self._call_api(messages)

            if response:
                logger.info(f"✅ AI Response generated: {len(response)} chars")

            return response

        except Exception as e:
            logger.error(f"Error generating AI response: {e}", exc_info=True)
            return None

    def _build_messages(
        self, user_input: str, history: list[tuple[str, str]]
    ) -> list[dict]:
        """
        Build the message list for the API, including conversation history.

        Args:
            user_input: Current user message
            history: Previous conversation turns

        Returns:
            List of message dicts with role and content
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You're a helpful, witty, and engaging assistant in a casual Discord chat. "
                    "Your personality traits:\n"
                    "- Genuine and thoughtful in your responses\n"
                    "- Use natural conversational language and contractions\n"
                    "- Be funny, sarcastic, or charming when it fits naturally\n"
                    "- Ask follow-up questions to keep conversations interesting\n"
                    "- Admit when you don't know something instead of guessing\n"
                    "- Give realistic, balanced answers—not always the 'perfect' response\n"
                    "- Be concise but not robotic; write like a real person\n"
                    "- Match the user's tone and energy when appropriate\n"
                    "- Use context from the conversation to give better replies\n\n"
                    "Keep responses focused and under 400 words when possible. "
                    "If responding to questions, be thorough but readable."
                ),
            }
        ]

        # Add relevant history (last 6 exchanges = 12 messages)
        # This gives context without overwhelming the model
        for user_msg, bot_resp in history[-6:]:
            if user_msg and bot_resp:
                messages.append({"role": "user", "content": user_msg})
                messages.append({"role": "assistant", "content": bot_resp})

        # Add current user message
        messages.append({"role": "user", "content": user_input})

        return messages

    async def _call_api(self, messages: list[dict]) -> Optional[str]:
        """
        Make the API call to Cloudflare Workers AI.

        Args:
            messages: Message list for the API

        Returns:
            Generated response text or None if error
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"messages": messages}

        logger.debug(f"Sending API request with {len(messages)} messages")

        async with aiohttp.ClientSession() as session:
            for attempt in range(3):
                try:
                    async with session.post(
                        f"{self.api_base}{self.model}",
                        headers=headers,
                        json=data,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status == 200:
                            json_data = await response.json()

                            if not json_data.get("success"):
                                error_msg = json_data.get("errors", [{}])[0].get(
                                    "message", "Unknown error"
                                )
                                logger.warning(f"⚠️ API returned error: {error_msg}")
                                return None

                            response_text = (
                                json_data.get("result", {}).get("response", "").strip()
                            )

                            if not response_text:
                                logger.warning("⚠️ Empty response from API")
                                return None

                            return response_text

                        elif response.status == 429:
                            logger.warning(f"Rate limited (attempt {attempt + 1}/3)")
                            if attempt < 2:
                                await asyncio.sleep(2**attempt)  # Exponential backoff
                            continue

                        else:
                            error_text = await response.text()
                            logger.error(
                                f"API error {response.status}: {error_text[:200]}"
                            )
                            return None

                except asyncio.TimeoutError:
                    logger.warning(f"Request timeout (attempt {attempt + 1}/3)")
                    if attempt < 2:
                        await asyncio.sleep(1)
                    continue

                except aiohttp.ClientError as e:
                    logger.error(f"Network error: {e}")
                    return None

        logger.error("Failed to get API response after 3 attempts")
        return None


async def setup(bot: commands.Bot):
    """Load the AI Response cog."""
    if os.getenv("WORKERS_API_KEY") and os.getenv("WORKERS_ACCOUNT_ID"):
        await bot.add_cog(AIResponse(bot))
        logger.info("✅ AIResponse cog loaded")
    else:
        logger.warning("⚠️ Skipping AIResponse cog - missing API credentials")
