import asyncio

import os

import sqlite3

import discord

from discord import app_commands
from discord.ext import commands


DB_PATH = "db/sticky.db"

EMBED_COLOR = discord.Color.orange()
ERROR_COLOR = discord.Color.red()


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sticky_messages (
            channel_id INTEGER PRIMARY KEY,
            message TEXT NOT NULL,
            message_id INTEGER
        )
    """)

    conn.commit()

    return conn


class Sticky(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.locks = {}

        conn = get_connection()
        conn.close()

    def get_lock(self, channel_id):
        if channel_id not in self.locks:
            self.locks[channel_id] = asyncio.Lock()

        return self.locks[channel_id]

    def get_sticky(self, channel_id):
        conn = get_connection()

        row = conn.execute(
            """
            SELECT message, message_id
            FROM sticky_messages
            WHERE channel_id = ?
            """,
            (channel_id,)
        ).fetchone()

        conn.close()

        if not row:
            return None

        return {
            "message": row[0],
            "message_id": row[1]
        }

    def set_sticky(self, channel_id, message, message_id=None):
        conn = get_connection()

        conn.execute(
            """
            INSERT INTO sticky_messages
                (channel_id, message, message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(channel_id)
            DO UPDATE SET
                message = excluded.message,
                message_id = excluded.message_id
            """,
            (channel_id, message, message_id)
        )

        conn.commit()
        conn.close()

    def delete_sticky(self, channel_id):
        conn = get_connection()

        conn.execute(
            """
            DELETE FROM sticky_messages
            WHERE channel_id = ?
            """,
            (channel_id,)
        )

        conn.commit()
        conn.close()

    def update_message_id(self, channel_id, message_id):
        conn = get_connection()

        conn.execute(
            """
            UPDATE sticky_messages
            SET message_id = ?
            WHERE channel_id = ?
            """,
            (message_id, channel_id)
        )

        conn.commit()
        conn.close()

    def error_embed(self, message):
        return discord.Embed(
            description=f"❌ {message}",
            color=ERROR_COLOR
        )

    def success_embed(self, message):
        return discord.Embed(
            description=f"✅ {message}",
            color=EMBED_COLOR
        )

    def sticky_embed(self, message):
        return discord.Embed(
            title="📌 Sticky Message",
            description=message,
            color=EMBED_COLOR
        )

    async def delete_old_sticky(self, channel, sticky):
        message_id = sticky.get("message_id")

        if not message_id:
            return

        try:
            message = await channel.fetch_message(message_id)
            await message.delete()
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            pass

    async def send_sticky(self, channel, sticky):
        await self.delete_old_sticky(channel, sticky)

        try:
            message = await channel.send(
                embed=self.sticky_embed(sticky["message"]),
                allowed_mentions=discord.AllowedMentions.none()
            )
        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            return None

        self.update_message_id(
            channel.id,
            message.id
        )

        return message

    sticky_group = app_commands.Group(
        name="sticky",
        description="Manage sticky messages."
    )

    @sticky_group.command(
        name="set",
        description="Set a sticky message in this channel."
    )
    @app_commands.describe(
        message="The message to keep at the bottom of the channel."
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def sticky_set(
        self,
        interaction: discord.Interaction,
        message: str
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )
            return

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Sticky messages can only be used in text channels."
                ),
                ephemeral=True
            )
            return

        if len(message) > 4000:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Sticky messages cannot exceed 4000 characters."
                ),
                ephemeral=True
            )
            return

        async with self.get_lock(channel.id):
            old_sticky = self.get_sticky(channel.id)

            if old_sticky:
                await self.delete_old_sticky(
                    channel,
                    old_sticky
                )

            self.set_sticky(
                channel.id,
                message,
                None
            )

            try:
                sticky_message = await channel.send(
                    embed=self.sticky_embed(message),
                    allowed_mentions=discord.AllowedMentions.none()
                )
            except discord.Forbidden:
                self.delete_sticky(channel.id)

                await interaction.response.send_message(
                    embed=self.error_embed(
                        "I don't have permission to send messages in this channel."
                    ),
                    ephemeral=True
                )
                return

            except discord.HTTPException:
                self.delete_sticky(channel.id)

                await interaction.response.send_message(
                    embed=self.error_embed(
                        "I couldn't send the sticky message."
                    ),
                    ephemeral=True
                )
                return

            self.update_message_id(
                channel.id,
                sticky_message.id
            )

        await interaction.response.send_message(
            embed=self.success_embed(
                "Sticky message set."
            ),
            ephemeral=True
        )

    @sticky_group.command(
        name="remove",
        description="Remove the sticky message from this channel."
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def sticky_remove(
        self,
        interaction: discord.Interaction
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )
            return

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Sticky messages can only be used in text channels."
                ),
                ephemeral=True
            )
            return

        async with self.get_lock(channel.id):
            sticky = self.get_sticky(channel.id)

            if not sticky:
                await interaction.response.send_message(
                    embed=self.error_embed(
                        "There isn't a sticky message in this channel."
                    ),
                    ephemeral=True
                )
                return

            await self.delete_old_sticky(
                channel,
                sticky
            )

            self.delete_sticky(channel.id)

        await interaction.response.send_message(
            embed=self.success_embed(
                "Sticky message removed."
            ),
            ephemeral=True
        )

    @sticky_group.command(
        name="view",
        description="View the sticky message in this channel."
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def sticky_view(
        self,
        interaction: discord.Interaction
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )
            return

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Sticky messages can only be used in text channels."
                ),
                ephemeral=True
            )
            return

        sticky = self.get_sticky(channel.id)

        if not sticky:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "There isn't a sticky message in this channel."
                ),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=self.sticky_embed(
                sticky["message"]
            ),
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        if message.author.bot:
            return

        if not isinstance(message.channel, discord.TextChannel):
            return

        sticky = self.get_sticky(message.channel.id)

        if not sticky:
            return

        async with self.get_lock(message.channel.id):
            sticky = self.get_sticky(message.channel.id)

            if not sticky:
                return

            await self.send_sticky(
                message.channel,
                sticky
            )

    @sticky_set.error
    @sticky_remove.error
    @sticky_view.error
    async def sticky_error(
        self,
        interaction: discord.Interaction,
        error
    ):
        if isinstance(
            error,
            app_commands.MissingPermissions
        ):
            embed = self.error_embed(
                "You need the **Manage Messages** permission to use this command."
            )

            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=embed,
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True
                )

            return

        raise error


async def setup(bot):
    await bot.add_cog(Sticky(bot))