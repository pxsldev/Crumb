import sqlite3
import re

import discord
from discord import app_commands
from discord.ext import commands

class Messages(commands.GroupCog, group_name="messages"):
    def __init__(self, bot):
        self.bot = bot

        self.db = sqlite3.connect("db/messages.db")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                guild_id INTEGER PRIMARY KEY,

                join_message TEXT,
                join_channel_id INTEGER,
                join_embed INTEGER NOT NULL DEFAULT 0,
                join_title TEXT,
                join_color TEXT,
                join_image TEXT,
                join_thumbnail TEXT,
                join_url TEXT,

                leave_message TEXT,
                leave_channel_id INTEGER,
                leave_embed INTEGER NOT NULL DEFAULT 0,
                leave_title TEXT,
                leave_color TEXT,
                leave_image TEXT,
                leave_thumbnail TEXT,
                leave_url TEXT,

                boost_message TEXT,
                boost_channel_id INTEGER,
                boost_embed INTEGER NOT NULL DEFAULT 0,
                boost_title TEXT,
                boost_color TEXT,
                boost_image TEXT,
                boost_thumbnail TEXT,
                boost_url TEXT
            )
        """)

        self.migrate_database()
        self.db.commit()

    def migrate_database(self):
        """
        Adds new columns to existing databases without deleting
        existing message configurations.
        """

        columns = {
            row["name"]
            for row in self.db.execute(
                "PRAGMA table_info(messages)"
            ).fetchall()
        }

        new_columns = {
            "join_embed": "INTEGER NOT NULL DEFAULT 0",
            "join_title": "TEXT",
            "join_color": "TEXT",
            "join_image": "TEXT",
            "join_thumbnail": "TEXT",
            "join_url": "TEXT",

            "leave_embed": "INTEGER NOT NULL DEFAULT 0",
            "leave_title": "TEXT",
            "leave_color": "TEXT",
            "leave_image": "TEXT",
            "leave_thumbnail": "TEXT",
            "leave_url": "TEXT",

            "boost_embed": "INTEGER NOT NULL DEFAULT 0",
            "boost_title": "TEXT",
            "boost_color": "TEXT",
            "boost_image": "TEXT",
            "boost_thumbnail": "TEXT",
            "boost_url": "TEXT",
        }

        for column, definition in new_columns.items():
            if column not in columns:
                self.db.execute(
                    f"ALTER TABLE messages ADD COLUMN {column} {definition}"
                )

    def get_config(self, guild_id: int):
        row = self.db.execute(
            """
            SELECT *
            FROM messages
            WHERE guild_id = ?
            """,
            (guild_id,)
        ).fetchone()

        if row is None:
            self.db.execute(
                """
                INSERT INTO messages (guild_id)
                VALUES (?)
                """,
                (guild_id,)
            )

            self.db.commit()

            row = self.db.execute(
                """
                SELECT *
                FROM messages
                WHERE guild_id = ?
                """,
                (guild_id,)
            ).fetchone()

        return row

    def update_config(self, guild_id: int, column: str, value):
        allowed_columns = {
            "join_message",
            "join_channel_id",
            "join_embed",
            "join_title",
            "join_color",
            "join_image",
            "join_thumbnail",
            "join_url",

            "leave_message",
            "leave_channel_id",
            "leave_embed",
            "leave_title",
            "leave_color",
            "leave_image",
            "leave_thumbnail",
            "leave_url",

            "boost_message",
            "boost_channel_id",
            "boost_embed",
            "boost_title",
            "boost_color",
            "boost_image",
            "boost_thumbnail",
            "boost_url",
        }

        if column not in allowed_columns:
            raise ValueError(f"Invalid database column: {column}")

        self.get_config(guild_id)

        self.db.execute(
            f"""
            UPDATE messages
            SET {column} = ?
            WHERE guild_id = ?
            """,
            (value, guild_id)
        )

        self.db.commit()

    def error_embed(self, text: str):
        return discord.Embed(
            description=f"❌ {text}",
            color=discord.Color.red()
        )

    def success_embed(self, text: str):
        return discord.Embed(
            description=f"🟠 {text}",
            color=discord.Color.orange()
        )

    def parse_color(self, value: str | None):
        if not value:
            return discord.Color.orange()

        value = value.strip().lower()

        if value.startswith("#"):
            value = value[1:]

        if not re.fullmatch(r"[0-9a-f]{6}", value):
            return discord.Color.orange()

        return discord.Color(int(value, 16))

    def format_message(
        self,
        message: str | None,
        member: discord.Member
    ):
        if not message:
            return None

        guild = member.guild

        replacements = {
            "{user}": member.mention,
            "{username}": member.name,
            "{displayname}": member.display_name,
            "{server}": guild.name,
            "{count}": str(guild.member_count or 0),
            "{boosts}": str(
                guild.premium_subscription_count or 0
            ),
            "{boostlevel}": str(
                guild.premium_tier or 0
            ),
            "{id}": str(member.id),
            "{userid}": str(member.id),
            "{serverid}": str(guild.id),
        }

        for placeholder, replacement in replacements.items():
            message = message.replace(
                placeholder,
                replacement
            )

        return message

    def format_text(
        self,
        text: str | None,
        member: discord.Member
    ):
        if not text:
            return None

        return self.format_message(text, member)

    def build_embed(
        self,
        row,
        message_type: str,
        member: discord.Member
    ):
        message = row[f"{message_type}_message"]

        if not message:
            return None

        formatted_message = self.format_message(
            message,
            member
        )

        if not formatted_message:
            return None

        embed_enabled = row[f"{message_type}_embed"]

        if not embed_enabled:
            return None

        title = self.format_text(
            row[f"{message_type}_title"],
            member
        )

        color = self.parse_color(
            row[f"{message_type}_color"]
        )

        embed = discord.Embed(
            description=formatted_message,
            color=color
        )

        if title:
            embed.title = title

        image = row[f"{message_type}_image"]

        if image:
            embed.set_image(url=image)

        thumbnail = row[f"{message_type}_thumbnail"]

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        url = row[f"{message_type}_url"]

        if url:
            embed.url = url

        return embed

    async def send_configured_message(
        self,
        guild: discord.Guild,
        member: discord.Member,
        message_type: str
    ):
        row = self.get_config(guild.id)

        channel_id = row[f"{message_type}_channel_id"]
        message = row[f"{message_type}_message"]

        if not channel_id or not message:
            return

        channel = guild.get_channel(channel_id)

        if channel is None:
            return

        embed_enabled = row[f"{message_type}_embed"]

        try:
            if embed_enabled:
                embed = self.build_embed(
                    row,
                    message_type,
                    member
                )

                if embed:
                    await channel.send(embed=embed)

            else:
                formatted = self.format_message(
                    message,
                    member
                )

                if formatted:
                    await channel.send(formatted)

        except (discord.Forbidden, discord.HTTPException):
            pass

    @app_commands.command(
        name="join",
        description="Configure the server's join message"
    )
    @app_commands.describe(
        channel="The channel to send the message in",
        message="The message to send",
        embed="Send the message as an embed"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def join(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
        embed: bool = False
    ):
        guild = interaction.guild

        if guild is None:
            return

        if len(message) > 4000:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Your message is too long. Keep it under 4000 characters."
                ),
                ephemeral=True
            )
            return

        self.update_config(
            guild.id,
            "join_message",
            message
        )

        self.update_config(
            guild.id,
            "join_channel_id",
            channel.id
        )

        self.update_config(
            guild.id,
            "join_embed",
            int(embed)
        )

        response = self.success_embed(
            f"Join messages are now enabled in {channel.mention}."
        )

        response.add_field(
            name="Mode",
            value="Embed" if embed else "Normal message",
            inline=True
        )

        response.add_field(
            name="Message",
            value=message[:1024],
            inline=False
        )

        await interaction.response.send_message(
            embed=response
        )

    @app_commands.command(
        name="leave",
        description="Configure the server's leave message"
    )
    @app_commands.describe(
        channel="The channel to send the message in",
        message="The message to send",
        embed="Send the message as an embed"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def leave(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
        embed: bool = False
    ):
        guild = interaction.guild

        if guild is None:
            return

        if len(message) > 4000:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Your message is too long. Keep it under 4000 characters."
                ),
                ephemeral=True
            )
            return

        self.update_config(
            guild.id,
            "leave_message",
            message
        )

        self.update_config(
            guild.id,
            "leave_channel_id",
            channel.id
        )

        self.update_config(
            guild.id,
            "leave_embed",
            int(embed)
        )

        response = self.success_embed(
            f"Leave messages are now enabled in {channel.mention}."
        )

        response.add_field(
            name="Mode",
            value="Embed" if embed else "Normal message",
            inline=True
        )

        response.add_field(
            name="Message",
            value=message[:1024],
            inline=False
        )

        await interaction.response.send_message(
            embed=response
        )

    @app_commands.command(
        name="boost",
        description="Configure the server's boost message"
    )
    @app_commands.describe(
        channel="The channel to send the message in",
        message="The message to send",
        embed="Send the message as an embed"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def boost(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
        embed: bool = False
    ):
        guild = interaction.guild

        if guild is None:
            return

        if len(message) > 4000:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Your message is too long. Keep it under 4000 characters."
                ),
                ephemeral=True
            )
            return

        self.update_config(
            guild.id,
            "boost_message",
            message
        )

        self.update_config(
            guild.id,
            "boost_channel_id",
            channel.id
        )

        self.update_config(
            guild.id,
            "boost_embed",
            int(embed)
        )

        response = self.success_embed(
            f"Boost messages are now enabled in {channel.mention}."
        )

        response.add_field(
            name="Mode",
            value="Embed" if embed else "Normal message",
            inline=True
        )

        response.add_field(
            name="Message",
            value=message[:1024],
            inline=False
        )

        await interaction.response.send_message(
            embed=response
        )

    @app_commands.command(
        name="disable",
        description="Disable a server message"
    )
    @app_commands.describe(
        message_type="The message type to disable"
    )
    @app_commands.choices(
        message_type=[
            app_commands.Choice(
                name="Join",
                value="join"
            ),
            app_commands.Choice(
                name="Leave",
                value="leave"
            ),
            app_commands.Choice(
                name="Boost",
                value="boost"
            ),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(
        self,
        interaction: discord.Interaction,
        message_type: app_commands.Choice[str]
    ):
        guild_id = interaction.guild.id

        columns = {
            "join": (
                "join_message",
                "join_channel_id"
            ),
            "leave": (
                "leave_message",
                "leave_channel_id"
            ),
            "boost": (
                "boost_message",
                "boost_channel_id"
            ),
        }

        message_column, channel_column = columns[
            message_type.value
        ]

        self.update_config(
            guild_id,
            message_column,
            None
        )

        self.update_config(
            guild_id,
            channel_column,
            None
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"{message_type.name} messages have been disabled."
            )
        )

    @app_commands.command(
        name="config",
        description="View the server's message configuration"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(
        self,
        interaction: discord.Interaction
    ):
        row = self.get_config(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="📨 Message Configuration",
            color=discord.Color.orange()
        )

        for message_type, emoji, name in (
            ("join", "👋", "Join"),
            ("leave", "👋", "Leave"),
            ("boost", "🚀", "Boost"),
        ):
            channel_id = row[
                f"{message_type}_channel_id"
            ]

            message = row[
                f"{message_type}_message"
            ]

            enabled = bool(channel_id and message)

            if not enabled:
                value = "🔴 Disabled"

            else:
                channel = interaction.guild.get_channel(
                    channel_id
                )

                channel_text = (
                    channel.mention
                    if channel
                    else f"`{channel_id}`"
                )

                mode = (
                    "Embed"
                    if row[f"{message_type}_embed"]
                    else "Normal"
                )

                value = (
                    f"🟢 Enabled\n"
                    f"Channel: {channel_text}\n"
                    f"Mode: `{mode}`\n"
                    f"Message: {message[:500]}"
                )

            embed.add_field(
                name=f"{emoji} {name}",
                value=value[:1024],
                inline=False
            )

        embed.add_field(
            name="🧩 Available Placeholders",
            value=(
                "`{user}` — mention\n"
                "`{username}` — username\n"
                "`{displayname}` — display name\n"
                "`{server}` — server name\n"
                "`{count}` — member count\n"
                "`{boosts}` — boost count\n"
                "`{boostlevel}` — boost level\n"
                "`{id}` — member ID\n"
                "`{userid}` — member ID\n"
                "`{serverid}` — server ID"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="preview",
        description="Preview a configured message"
    )
    @app_commands.describe(
        message_type="The message to preview"
    )
    @app_commands.choices(
        message_type=[
            app_commands.Choice(
                name="Join",
                value="join"
            ),
            app_commands.Choice(
                name="Leave",
                value="leave"
            ),
            app_commands.Choice(
                name="Boost",
                value="boost"
            ),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def preview(
        self,
        interaction: discord.Interaction,
        message_type: app_commands.Choice[str]
    ):
        row = self.get_config(
            interaction.guild.id
        )

        message = row[
            f"{message_type.value}_message"
        ]

        if not message:
            await interaction.response.send_message(
                embed=self.error_embed(
                    f"{message_type.name} messages are not configured."
                ),
                ephemeral=True
            )
            return

        member = interaction.user

        if not isinstance(member, discord.Member):
            return

        if row[f"{message_type.value}_embed"]:
            embed = self.build_embed(
                row,
                message_type.value,
                member
            )

            if embed:
                await interaction.response.send_message(
                    content="👀 **Preview:**",
                    embed=embed,
                    ephemeral=True
                )
                return

        formatted = self.format_message(
            message,
            member
        )

        await interaction.response.send_message(
            content=f"👀 **Preview:**\n\n{formatted}",
            ephemeral=True
        )

    @app_commands.command(
        name="test",
        description="Send a configured message to its channel"
    )
    @app_commands.describe(
        message_type="The message to test"
    )
    @app_commands.choices(
        message_type=[
            app_commands.Choice(
                name="Join",
                value="join"
            ),
            app_commands.Choice(
                name="Leave",
                value="leave"
            ),
            app_commands.Choice(
                name="Boost",
                value="boost"
            ),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test(
        self,
        interaction: discord.Interaction,
        message_type: app_commands.Choice[str]
    ):
        guild = interaction.guild

        if guild is None:
            return

        row = self.get_config(guild.id)

        channel_id = row[
            f"{message_type.value}_channel_id"
        ]

        message = row[
            f"{message_type.value}_message"
        ]

        if not channel_id or not message:
            await interaction.response.send_message(
                embed=self.error_embed(
                    f"{message_type.name} messages are not configured."
                ),
                ephemeral=True
            )
            return

        channel = guild.get_channel(channel_id)

        if channel is None:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "The configured channel no longer exists."
                ),
                ephemeral=True
            )
            return

        member = interaction.user

        if not isinstance(member, discord.Member):
            return

        try:
            if row[f"{message_type.value}_embed"]:
                embed = self.build_embed(
                    row,
                    message_type.value,
                    member
                )

                if embed:
                    await channel.send(
                        embed=embed
                    )

            else:
                formatted = self.format_message(
                    message,
                    member
                )

                await channel.send(
                    formatted
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                embed=self.error_embed(
                    f"I can't send messages in {channel.mention}."
                ),
                ephemeral=True
            )
            return

        except discord.HTTPException:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Discord rejected the test message."
                ),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Test {message_type.name.lower()} message sent to "
                f"{channel.mention}."
            ),
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member
    ):
        await self.send_configured_message(
            member.guild,
            member,
            "join"
        )

    @commands.Cog.listener()
    async def on_member_remove(
        self,
        member: discord.Member
    ):
        await self.send_configured_message(
            member.guild,
            member,
            "leave"
        )

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member
    ):
        if before.premium_since == after.premium_since:
            return

        if after.premium_since is None:
            return

        await self.send_configured_message(
            after.guild,
            after,
            "boost"
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(
            error,
            app_commands.MissingPermissions
        ):
            await interaction.response.send_message(
                embed=self.error_embed(
                    "You need the `Manage Server` permission "
                    "to use this command."
                ),
                ephemeral=True
            )
            return

        if isinstance(
            error,
            app_commands.BotMissingPermissions
        ):
            await interaction.response.send_message(
                embed=self.error_embed(
                    "I don't have the permissions required "
                    "to perform that action."
                ),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=self.error_embed(
                "Something went wrong while running this command."
            ),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Messages(bot))