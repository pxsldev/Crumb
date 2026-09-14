import asyncio

import sqlite3

from datetime import datetime, timezone

import discord

from discord import app_commands

from discord.ext import commands, tasks


class ServerStats(commands.GroupCog, group_name="serverstats"):

    def __init__(self, bot):

        self.bot = bot

        self.db = sqlite3.connect(
            "db/serverstats.db",
            check_same_thread=False,
        )

        self.db.row_factory = sqlite3.Row

        self.setup_database()

        self.update_stats.start()

    def cog_unload(self):

        self.update_stats.cancel()

        self.db.close()

    def setup_database(self):

        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS serverstats (

                guild_id INTEGER PRIMARY KEY,

                enabled INTEGER NOT NULL DEFAULT 0,

                category_id INTEGER

            )
            """
        )

        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS stat_channels (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,

                channel_id INTEGER NOT NULL UNIQUE,

                stat_type TEXT NOT NULL,

                format TEXT NOT NULL,

                enabled INTEGER NOT NULL DEFAULT 1

            )
            """
        )

        self.db.commit()

    def get_config(self, guild_id):

        return self.db.execute(
            """
            SELECT *
            FROM serverstats
            WHERE guild_id = ?
            """,
            (guild_id,),
        ).fetchone()

    def ensure_config(self, guild_id):

        self.db.execute(
            """
            INSERT OR IGNORE INTO serverstats (
                guild_id
            )
            VALUES (?)
            """,
            (guild_id,),
        )

        self.db.commit()

        return self.get_config(guild_id)

    def get_stat_channels(self, guild_id):

        return self.db.execute(
            """
            SELECT *
            FROM stat_channels
            WHERE guild_id = ?
            ORDER BY id ASC
            """,
            (guild_id,),
        ).fetchall()

    def error_embed(self, message):

        return discord.Embed(
            title="❌ Error",
            description=message,
            color=discord.Color.red(),
        )

    def success_embed(self, message):

        return discord.Embed(
            title="✅ Success",
            description=message,
            color=discord.Color.orange(),
        )

    def get_stat_value(self, guild, stat_type):

        members = guild.members

        values = {
            "members": len(members),

            "humans": sum(
                1
                for member in members
                if not member.bot
            ),

            "bots": sum(
                1
                for member in members
                if member.bot
            ),

            "online": sum(
                1
                for member in members
                if member.status == discord.Status.online
            ),

            "idle": sum(
                1
                for member in members
                if member.status == discord.Status.idle
            ),

            "dnd": sum(
                1
                for member in members
                if member.status == discord.Status.dnd
            ),

            "offline": sum(
                1
                for member in members
                if member.status == discord.Status.offline
            ),

            "text_channels": sum(
                1
                for channel in guild.channels
                if isinstance(channel, discord.TextChannel)
            ),

            "voice_channels": sum(
                1
                for channel in guild.channels
                if isinstance(channel, discord.VoiceChannel)
            ),

            "categories": sum(
                1
                for channel in guild.channels
                if isinstance(channel, discord.CategoryChannel)
            ),

            "channels": sum(
                1
                for channel in guild.channels
                if not isinstance(channel, discord.CategoryChannel)
            ),

            "roles": len(guild.roles),

            "emojis": len(guild.emojis),

            "stickers": len(guild.stickers),

            "boosts": guild.premium_subscription_count or 0,

            "boost_level": guild.premium_tier,

            "voice_users": sum(
                1
                for channel in guild.voice_channels
                for member in channel.members
            ),

            "voice_channels_active": sum(
                1
                for channel in guild.voice_channels
                if len(channel.members) > 0
            ),
        }

        return values.get(
            stat_type,
            0,
        )

    def get_stat_types(self):

        return {
            "members": "Total members",
            "humans": "Human members",
            "bots": "Bots",
            "online": "Online members",
            "idle": "Idle members",
            "dnd": "Do Not Disturb members",
            "offline": "Offline members",
            "text_channels": "Text channels",
            "voice_channels": "Voice channels",
            "categories": "Categories",
            "channels": "All non-category channels",
            "roles": "Roles",
            "emojis": "Emojis",
            "stickers": "Stickers",
            "boosts": "Server boosts",
            "boost_level": "Boost level",
            "voice_users": "Users currently in voice",
            "voice_channels_active": "Voice channels currently in use",
        }

    def format_stat(
        self,
        guild,
        stat_type,
        channel_format,
    ):

        value = self.get_stat_value(
            guild,
            stat_type,
        )

        replacements = {
            "{value}": str(value),

            "{members}": str(
                self.get_stat_value(
                    guild,
                    "members",
                )
            ),

            "{humans}": str(
                self.get_stat_value(
                    guild,
                    "humans",
                )
            ),

            "{bots}": str(
                self.get_stat_value(
                    guild,
                    "bots",
                )
            ),

            "{online}": str(
                self.get_stat_value(
                    guild,
                    "online",
                )
            ),

            "{idle}": str(
                self.get_stat_value(
                    guild,
                    "idle",
                )
            ),

            "{dnd}": str(
                self.get_stat_value(
                    guild,
                    "dnd",
                )
            ),

            "{offline}": str(
                self.get_stat_value(
                    guild,
                    "offline",
                )
            ),

            "{text_channels}": str(
                self.get_stat_value(
                    guild,
                    "text_channels",
                )
            ),

            "{voice_channels}": str(
                self.get_stat_value(
                    guild,
                    "voice_channels",
                )
            ),

            "{categories}": str(
                self.get_stat_value(
                    guild,
                    "categories",
                )
            ),

            "{channels}": str(
                self.get_stat_value(
                    guild,
                    "channels",
                )
            ),

            "{roles}": str(
                self.get_stat_value(
                    guild,
                    "roles",
                )
            ),

            "{emojis}": str(
                self.get_stat_value(
                    guild,
                    "emojis",
                )
            ),

            "{stickers}": str(
                self.get_stat_value(
                    guild,
                    "stickers",
                )
            ),

            "{boosts}": str(
                self.get_stat_value(
                    guild,
                    "boosts",
                )
            ),

            "{boost_level}": str(
                self.get_stat_value(
                    guild,
                    "boost_level",
                )
            ),

            "{voice_users}": str(
                self.get_stat_value(
                    guild,
                    "voice_users",
                )
            ),

            "{voice_active}": str(
                self.get_stat_value(
                    guild,
                    "voice_channels_active",
                )
            ),

            "{server}": guild.name,
        }

        for key, replacement in replacements.items():

            channel_format = channel_format.replace(
                key,
                replacement,
            )

        return channel_format[:100]

    async def get_or_create_category(self, guild):

        config = self.get_config(guild.id)

        if config and config["category_id"]:

            category = guild.get_channel(
                config["category_id"]
            )

            if isinstance(
                category,
                discord.CategoryChannel,
            ):

                return category

        category = await guild.create_category(
            "📊 SERVER STATS",
            reason="Crumb ServerStats setup",
        )

        self.ensure_config(guild.id)

        self.db.execute(
            """
            UPDATE serverstats
            SET category_id = ?
            WHERE guild_id = ?
            """,
            (
                category.id,
                guild.id,
            ),
        )

        self.db.commit()

        return category

    async def create_stat_channel(
        self,
        guild,
        category,
        stat_type,
        channel_format,
    ):

        name = self.format_stat(
            guild,
            stat_type,
            channel_format,
        )

        channel = await guild.create_voice_channel(
            name=name,
            category=category,
            reason="Crumb ServerStats",
        )

        self.db.execute(
            """
            INSERT INTO stat_channels (
                guild_id,
                channel_id,
                stat_type,
                format,
                enabled
            )
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                guild.id,
                channel.id,
                stat_type,
                channel_format,
            ),
        )

        self.db.commit()

        return channel

    @tasks.loop(seconds=60)
    async def update_stats(self):

        await self.bot.wait_until_ready()

        configs = self.db.execute(
            """
            SELECT *
            FROM serverstats
            WHERE enabled = 1
            """
        ).fetchall()

        for config in configs:

            guild = self.bot.get_guild(
                config["guild_id"]
            )

            if not guild:
                continue

            stat_channels = self.get_stat_channels(
                guild.id
            )

            for stat in stat_channels:

                if not stat["enabled"]:
                    continue

                channel = guild.get_channel(
                    stat["channel_id"]
                )

                if not channel:

                    self.db.execute(
                        """
                        DELETE FROM stat_channels
                        WHERE channel_id = ?
                        """,
                        (stat["channel_id"],),
                    )

                    self.db.commit()

                    continue

                new_name = self.format_stat(
                    guild,
                    stat["stat_type"],
                    stat["format"],
                )

                if channel.name == new_name:
                    continue

                try:

                    await channel.edit(
                        name=new_name,
                        reason="Crumb ServerStats update",
                    )

                except (
                    discord.Forbidden,
                    discord.HTTPException,
                ):

                    pass

    @update_stats.before_loop
    async def before_update_stats(self):

        await self.bot.wait_until_ready()

    @app_commands.command(
        name="setup",
        description="Set up server statistics",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def setup(
        self,
        interaction: discord.Interaction,
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        self.ensure_config(guild.id)

        category = await self.get_or_create_category(
            guild
        )

        existing = self.get_stat_channels(
            guild.id
        )

        if existing:

            self.db.execute(
                """
                UPDATE serverstats
                SET enabled = 1
                WHERE guild_id = ?
                """,
                (guild.id,),
            )

            self.db.commit()

            await interaction.followup.send(
                embed=self.success_embed(
                    "ServerStats is already configured.\n\n"
                    f"**Category:** {category.name}\n"
                    f"**Stat channels:** {len(existing)}\n\n"
                    "Use `/serverstats add` to add more "
                    "statistics."
                ),
                ephemeral=True,
            )

            return

        default_stats = [
            (
                "members",
                "👥 Members: {value}",
            ),
            (
                "online",
                "🟢 Online: {value}",
            ),
            (
                "bots",
                "🤖 Bots: {value}",
            ),
            (
                "text_channels",
                "💬 Text Channels: {value}",
            ),
            (
                "voice_channels",
                "🔊 Voice Channels: {value}",
            ),
            (
                "roles",
                "🎭 Roles: {value}",
            ),
            (
                "boosts",
                "🚀 Boosts: {value}",
            ),
        ]

        created = 0

        for stat_type, channel_format in default_stats:

            try:

                await self.create_stat_channel(
                    guild,
                    category,
                    stat_type,
                    channel_format,
                )

                created += 1

            except (
                discord.Forbidden,
                discord.HTTPException,
            ):

                break

        self.db.execute(
            """
            UPDATE serverstats
            SET enabled = 1
            WHERE guild_id = ?
            """,
            (guild.id,),
        )

        self.db.commit()

        await interaction.followup.send(
            embed=self.success_embed(
                "ServerStats has been set up successfully!\n\n"
                f"**Category:** {category.name}\n"
                f"**Statistics created:** {created}\n\n"
                "Use `/serverstats add` to add more "
                "statistics or `/serverstats config` "
                "to view the current configuration."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="add",
        description="Add a custom server statistic",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.describe(
        stat_type="The statistic to display",
        channel_format=(
            "The channel name. Use {value} for the statistic."
        ),
    )
    @app_commands.choices(
        stat_type=[
            app_commands.Choice(
                name="Members",
                value="members",
            ),
            app_commands.Choice(
                name="Humans",
                value="humans",
            ),
            app_commands.Choice(
                name="Bots",
                value="bots",
            ),
            app_commands.Choice(
                name="Online",
                value="online",
            ),
            app_commands.Choice(
                name="Idle",
                value="idle",
            ),
            app_commands.Choice(
                name="Do Not Disturb",
                value="dnd",
            ),
            app_commands.Choice(
                name="Offline",
                value="offline",
            ),
            app_commands.Choice(
                name="Text Channels",
                value="text_channels",
            ),
            app_commands.Choice(
                name="Voice Channels",
                value="voice_channels",
            ),
            app_commands.Choice(
                name="Categories",
                value="categories",
            ),
            app_commands.Choice(
                name="All Channels",
                value="channels",
            ),
            app_commands.Choice(
                name="Roles",
                value="roles",
            ),
            app_commands.Choice(
                name="Emojis",
                value="emojis",
            ),
            app_commands.Choice(
                name="Stickers",
                value="stickers",
            ),
            app_commands.Choice(
                name="Boosts",
                value="boosts",
            ),
            app_commands.Choice(
                name="Boost Level",
                value="boost_level",
            ),
            app_commands.Choice(
                name="Users in Voice",
                value="voice_users",
            ),
            app_commands.Choice(
                name="Active Voice Channels",
                value="voice_channels_active",
            ),
        ],
    )
    async def add(
        self,
        interaction: discord.Interaction,
        stat_type: app_commands.Choice[str],
        channel_format: str,
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        self.ensure_config(guild.id)

        category = await self.get_or_create_category(
            guild
        )

        try:

            channel = await self.create_stat_channel(
                guild,
                category,
                stat_type.value,
                channel_format,
            )

        except discord.Forbidden:

            await interaction.followup.send(
                embed=self.error_embed(
                    "I don't have permission to create "
                    "voice channels."
                ),
                ephemeral=True,
            )

            return

        except discord.HTTPException:

            await interaction.followup.send(
                embed=self.error_embed(
                    "Discord rejected the channel creation."
                ),
                ephemeral=True,
            )

            return

        self.db.execute(
            """
            UPDATE serverstats
            SET enabled = 1
            WHERE guild_id = ?
            """,
            (guild.id,),
        )

        self.db.commit()

        await interaction.followup.send(
            embed=self.success_embed(
                "Statistic added successfully!\n\n"
                f"**Statistic:** `{stat_type.name}`\n"
                f"**Channel:** {channel.mention}\n"
                f"**Format:** `{channel_format}`"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="remove",
        description="Remove a server statistic",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.describe(
        channel="The statistics channel to remove",
    )
    async def remove(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        row = self.db.execute(
            """
            SELECT *
            FROM stat_channels
            WHERE guild_id = ?
              AND channel_id = ?
            """,
            (
                guild.id,
                channel.id,
            ),
        ).fetchone()

        if not row:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "That channel isn't managed by "
                    "Crumb ServerStats."
                ),
                ephemeral=True,
            )

            return

        try:

            await channel.delete(
                reason="Crumb ServerStats removal"
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "I don't have permission to delete "
                    "that channel."
                ),
                ephemeral=True,
            )

            return

        except discord.HTTPException:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "Discord rejected the channel deletion."
                ),
                ephemeral=True,
            )

            return

        self.db.execute(
            """
            DELETE FROM stat_channels
            WHERE channel_id = ?
            """,
            (channel.id,),
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "The statistic has been removed."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="edit",
        description="Edit a server statistic",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.describe(
        channel="The statistics channel to edit",
        stat_type="The new statistic",
        channel_format="The new channel name format",
    )
    @app_commands.choices(
        stat_type=[
            app_commands.Choice(
                name="Members",
                value="members",
            ),
            app_commands.Choice(
                name="Humans",
                value="humans",
            ),
            app_commands.Choice(
                name="Bots",
                value="bots",
            ),
            app_commands.Choice(
                name="Online",
                value="online",
            ),
            app_commands.Choice(
                name="Idle",
                value="idle",
            ),
            app_commands.Choice(
                name="Do Not Disturb",
                value="dnd",
            ),
            app_commands.Choice(
                name="Offline",
                value="offline",
            ),
            app_commands.Choice(
                name="Text Channels",
                value="text_channels",
            ),
            app_commands.Choice(
                name="Voice Channels",
                value="voice_channels",
            ),
            app_commands.Choice(
                name="Categories",
                value="categories",
            ),
            app_commands.Choice(
                name="All Channels",
                value="channels",
            ),
            app_commands.Choice(
                name="Roles",
                value="roles",
            ),
            app_commands.Choice(
                name="Emojis",
                value="emojis",
            ),
            app_commands.Choice(
                name="Stickers",
                value="stickers",
            ),
            app_commands.Choice(
                name="Boosts",
                value="boosts",
            ),
            app_commands.Choice(
                name="Boost Level",
                value="boost_level",
            ),
            app_commands.Choice(
                name="Users in Voice",
                value="voice_users",
            ),
            app_commands.Choice(
                name="Active Voice Channels",
                value="voice_channels_active",
            ),
        ],
    )
    async def edit(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        stat_type: app_commands.Choice[str],
        channel_format: str,
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        row = self.db.execute(
            """
            SELECT *
            FROM stat_channels
            WHERE guild_id = ?
              AND channel_id = ?
            """,
            (
                guild.id,
                channel.id,
            ),
        ).fetchone()

        if not row:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "That channel isn't managed by "
                    "Crumb ServerStats."
                ),
                ephemeral=True,
            )

            return

        new_name = self.format_stat(
            guild,
            stat_type.value,
            channel_format,
        )

        try:

            await channel.edit(
                name=new_name,
                reason="Crumb ServerStats edit",
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "I don't have permission to edit "
                    "that channel."
                ),
                ephemeral=True,
            )

            return

        except discord.HTTPException:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "Discord rejected the channel update."
                ),
                ephemeral=True,
            )

            return

        self.db.execute(
            """
            UPDATE stat_channels
            SET stat_type = ?,
                format = ?
            WHERE channel_id = ?
            """,
            (
                stat_type.value,
                channel_format,
                channel.id,
            ),
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "The statistic has been updated.\n\n"
                f"**Statistic:** `{stat_type.name}`\n"
                f"**Format:** `{channel_format}`"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="enable",
        description="Enable automatic server statistic updates",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def enable(
        self,
        interaction: discord.Interaction,
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        config = self.get_config(guild.id)

        if not config:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "ServerStats hasn't been set up yet.\n\n"
                    "Run `/serverstats setup` first."
                ),
                ephemeral=True,
            )

            return

        self.db.execute(
            """
            UPDATE serverstats
            SET enabled = 1
            WHERE guild_id = ?
            """,
            (guild.id,),
        )

        self.db.execute(
            """
            UPDATE stat_channels
            SET enabled = 1
            WHERE guild_id = ?
            """,
            (guild.id,),
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "ServerStats automatic updates have been enabled."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="disable",
        description="Disable automatic server statistic updates",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def disable(
        self,
        interaction: discord.Interaction,
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        self.db.execute(
            """
            UPDATE serverstats
            SET enabled = 0
            WHERE guild_id = ?
            """,
            (guild.id,),
        )

        self.db.execute(
            """
            UPDATE stat_channels
            SET enabled = 0
            WHERE guild_id = ?
            """,
            (guild.id,),
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "ServerStats automatic updates have been disabled."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="refresh",
        description="Immediately refresh all server statistics",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def refresh(
        self,
        interaction: discord.Interaction,
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        stats = self.get_stat_channels(
            guild.id
        )

        updated = 0

        for stat in stats:

            channel = guild.get_channel(
                stat["channel_id"]
            )

            if not channel:
                continue

            new_name = self.format_stat(
                guild,
                stat["stat_type"],
                stat["format"],
            )

            if channel.name == new_name:
                continue

            try:

                await channel.edit(
                    name=new_name,
                    reason="Manual Crumb ServerStats refresh",
                )

                updated += 1

            except (
                discord.Forbidden,
                discord.HTTPException,
            ):

                pass

        await interaction.followup.send(
            embed=self.success_embed(
                f"Server statistics refreshed.\n\n"
                f"**Channels updated:** {updated}\n"
                f"**Statistics configured:** {len(stats)}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="config",
        description="View ServerStats configuration",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def config(
        self,
        interaction: discord.Interaction,
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        config = self.get_config(
            guild.id
        )

        if not config:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "ServerStats hasn't been configured."
                ),
                ephemeral=True,
            )

            return

        category = guild.get_channel(
            config["category_id"]
        )

        stats = self.get_stat_channels(
            guild.id
        )

        embed = discord.Embed(
            title="📊 ServerStats Configuration",
            color=discord.Color.orange(),
        )

        embed.add_field(
            name="Status",
            value=(
                "🟢 Enabled"
                if config["enabled"]
                else "🔴 Disabled"
            ),
            inline=True,
        )

        embed.add_field(
            name="Category",
            value=(
                category.mention
                if category
                else "`Missing`"
            ),
            inline=True,
        )

        embed.add_field(
            name="Update Interval",
            value="60 seconds",
            inline=True,
        )

        if stats:

            lines = []

            for stat in stats:

                channel = guild.get_channel(
                    stat["channel_id"]
                )

                if channel:

                    lines.append(
                        f"• {channel.mention} — "
                        f"`{stat['stat_type']}`"
                    )

                else:

                    lines.append(
                        f"• `Missing channel` — "
                        f"`{stat['stat_type']}`"
                    )

            embed.add_field(
                name=f"Statistics ({len(stats)})",
                value="\n".join(lines),
                inline=False,
            )

        else:

            embed.add_field(
                name="Statistics",
                value="No statistics configured.",
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="list",
        description="List all configured server statistics",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def list(
        self,
        interaction: discord.Interaction,
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        stats = self.get_stat_channels(
            guild.id
        )

        if not stats:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "No ServerStats are configured.\n\n"
                    "Run `/serverstats setup` to get started."
                ),
                ephemeral=True,
            )

            return

        embed = discord.Embed(
            title="📊 Server Statistics",
            description=(
                "All statistics currently managed by Crumb."
            ),
            color=discord.Color.orange(),
        )

        for index, stat in enumerate(
            stats,
            start=1,
        ):

            channel = guild.get_channel(
                stat["channel_id"]
            )

            channel_name = (
                channel.mention
                if channel
                else "`Missing channel`"
            )

            status = (
                "🟢"
                if stat["enabled"]
                else "🔴"
            )

            embed.add_field(
                name=f"{status} {index}. {stat['stat_type']}",
                value=(
                    f"Channel: {channel_name}\n"
                    f"Format: `{stat['format']}`"
                ),
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="template",
        description="Create a ServerStats template",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.describe(
        template="The template to create",
    )
    @app_commands.choices(
        template=[
            app_commands.Choice(
                name="Minimal",
                value="minimal",
            ),
            app_commands.Choice(
                name="Classic",
                value="classic",
            ),
            app_commands.Choice(
                name="Community",
                value="community",
            ),
            app_commands.Choice(
                name="Activity",
                value="activity",
            ),
            app_commands.Choice(
                name="Everything",
                value="everything",
            ),
        ],
    )
    async def template(
        self,
        interaction: discord.Interaction,
        template: app_commands.Choice[str],
    ):

        guild = interaction.guild

        if not guild:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True,
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        self.ensure_config(guild.id)

        category = await self.get_or_create_category(
            guild
        )

        templates = {
            "minimal": [
                (
                    "members",
                    "👥 Members: {value}",
                ),
                (
                    "online",
                    "🟢 Online: {value}",
                ),
            ],

            "classic": [
                (
                    "members",
                    "👥 Members: {value}",
                ),
                (
                    "online",
                    "🟢 Online: {value}",
                ),
                (
                    "bots",
                    "🤖 Bots: {value}",
                ),
                (
                    "text_channels",
                    "💬 Channels: {value}",
                ),
                (
                    "boosts",
                    "🚀 Boosts: {value}",
                ),
            ],

            "community": [
                (
                    "members",
                    "👥 Members: {value}",
                ),
                (
                    "humans",
                    "👤 Humans: {value}",
                ),
                (
                    "bots",
                    "🤖 Bots: {value}",
                ),
                (
                    "online",
                    "🟢 Online: {value}",
                ),
                (
                    "voice_users",
                    "🔊 In Voice: {value}",
                ),
                (
                    "boosts",
                    "🚀 Boosts: {value}",
                ),
            ],

            "activity": [
                (
                    "online",
                    "🟢 Online: {value}",
                ),
                (
                    "idle",
                    "🌙 Idle: {value}",
                ),
                (
                    "dnd",
                    "⛔ DND: {value}",
                ),
                (
                    "voice_users",
                    "🔊 In Voice: {value}",
                ),
                (
                    "voice_channels_active",
                    "🎙️ Active Voice: {value}",
                ),
            ],

            "everything": [
                (
                    "members",
                    "👥 Members: {value}",
                ),
                (
                    "humans",
                    "👤 Humans: {value}",
                ),
                (
                    "bots",
                    "🤖 Bots: {value}",
                ),
                (
                    "online",
                    "🟢 Online: {value}",
                ),
                (
                    "idle",
                    "🌙 Idle: {value}",
                ),
                (
                    "dnd",
                    "⛔ DND: {value}",
                ),
                (
                    "offline",
                    "⚫ Offline: {value}",
                ),
                (
                    "text_channels",
                    "💬 Text: {value}",
                ),
                (
                    "voice_channels",
                    "🔊 Voice: {value}",
                ),
                (
                    "categories",
                    "📁 Categories: {value}",
                ),
                (
                    "roles",
                    "🎭 Roles: {value}",
                ),
                (
                    "emojis",
                    "😀 Emojis: {value}",
                ),
                (
                    "stickers",
                    "🏷️ Stickers: {value}",
                ),
                (
                    "boosts",
                    "🚀 Boosts: {value}",
                ),
                (
                    "boost_level",
                    "✨ Boost Level: {value}",
                ),
                (
                    "voice_users",
                    "🎤 In Voice: {value}",
                ),
            ],
        }

        selected = templates[
            template.value
        ]

        created = 0

        for stat_type, channel_format in selected:

            try:

                await self.create_stat_channel(
                    guild,
                    category,
                    stat_type,
                    channel_format,
                )

                created += 1

            except (
                discord.Forbidden,
                discord.HTTPException,
            ):

                break

        self.db.execute(
            """
            UPDATE serverstats
            SET enabled = 1
            WHERE guild_id = ?
            """,
            (guild.id,),
        )

        self.db.commit()

        await interaction.followup.send(
            embed=self.success_embed(
                f"**{template.name}** ServerStats template "
                "created successfully!\n\n"
                f"**Statistics created:** {created}\n"
                f"**Category:** {category.name}"
            ),
            ephemeral=True,
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):

        if isinstance(
            error,
            app_commands.MissingPermissions,
        ):

            message = (
                "You don't have permission to use this command."
            )

        elif isinstance(
            error,
            app_commands.BotMissingPermissions,
        ):

            message = (
                "I don't have the permissions required "
                "to do that."
            )

        elif isinstance(
            error,
            app_commands.CommandOnCooldown,
        ):

            message = (
                "This command is currently on cooldown."
            )

        else:

            message = (
                "Something went wrong while running "
                "that command."
            )

        embed = self.error_embed(
            message
        )

        if interaction.response.is_done():

            await interaction.followup.send(
                embed=embed,
                ephemeral=True,
            )

        else:

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )


async def setup(bot):

    await bot.add_cog(
        ServerStats(bot)
    )