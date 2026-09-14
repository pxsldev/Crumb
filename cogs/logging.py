import sqlite3
import discord

from discord import app_commands
from discord.ext import commands

class Logging(commands.GroupCog, group_name="logging"):

    def __init__(self, bot):
        self.bot = bot

        self.db = sqlite3.connect("db/logging.db")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS logging (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                enabled INTEGER NOT NULL DEFAULT 0,
                events TEXT NOT NULL DEFAULT ''
            )
        """)

        self.db.commit()

    EVENT_NAMES = {
        "members": "Member events",
        "messages": "Message events",
        "channels": "Channel events",
        "roles": "Role events",
        "voice": "Voice events",
        "moderation": "Moderation events",
        "server": "Server events",
    }

    DEFAULT_EVENTS = set(EVENT_NAMES.keys())

    def get_config(self, guild_id):

        row = self.db.execute(
            """
            SELECT *
            FROM logging
            WHERE guild_id = ?
            """,
            (guild_id,)
        ).fetchone()

        if row is None:

            self.db.execute(
                """
                INSERT INTO logging (
                    guild_id,
                    channel_id,
                    enabled,
                    events
                )
                VALUES (?, NULL, 0, '')
                """,
                (guild_id,)
            )

            self.db.commit()

            row = self.db.execute(
                """
                SELECT *
                FROM logging
                WHERE guild_id = ?
                """,
                (guild_id,)
            ).fetchone()

        return row

    def get_events(self, guild_id):

        row = self.get_config(guild_id)

        if not row["events"]:
            return set()

        return set(
            event.strip()
            for event in row["events"].split(",")
            if event.strip()
        )

    def set_events(self, guild_id, events):

        events_string = ",".join(sorted(events))

        self.db.execute(
            """
            UPDATE logging
            SET events = ?
            WHERE guild_id = ?
            """,
            (events_string, guild_id)
        )

        self.db.commit()

    def update_config(self, guild_id, column, value):

        self.get_config(guild_id)

        allowed_columns = {
            "channel_id",
            "enabled",
            "events"
        }

        if column not in allowed_columns:
            return

        self.db.execute(
            f"""
            UPDATE logging
            SET {column} = ?
            WHERE guild_id = ?
            """,
            (value, guild_id)
        )

        self.db.commit()

    def error_embed(self, text):

        return discord.Embed(
            description=f"❌ {text}",
            color=discord.Color.red()
        )

    def log_embed(
        self,
        title,
        description=None
    ):

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.orange()
        )

        return embed

    async def send_log(
        self,
        guild,
        event_type,
        embed
    ):

        if guild is None:
            return

        row = self.get_config(guild.id)

        if not row["enabled"]:
            return

        if event_type not in self.get_events(guild.id):
            return

        channel_id = row["channel_id"]

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)

        if channel is None:
            return

        try:
            await channel.send(embed=embed)

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            pass

    async def get_audit_actor(
        self,
        guild,
        action,
        target_id=None
    ):

        try:
            async for entry in guild.audit_logs(
                limit=5,
                action=action
            ):

                if target_id is not None:

                    if entry.target is None:
                        continue

                    if getattr(
                        entry.target,
                        "id",
                        None
                    ) != target_id:
                        continue

                return entry.user

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            pass

        return None

    @app_commands.command(
        name="setup",
        description="Set up server logging"
    )
    @app_commands.describe(
        channel="The channel to send logs to"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        guild_id = interaction.guild.id

        self.update_config(
            guild_id,
            "channel_id",
            channel.id
        )

        self.update_config(
            guild_id,
            "enabled",
            1
        )

        self.set_events(
            guild_id,
            self.DEFAULT_EVENTS
        )

        embed = self.log_embed(
            "Logging enabled",
            f"Logs will now be sent to {channel.mention}."
        )

        embed.add_field(
            name="Events",
            value="\n".join(
                f"• {name}"
                for name in self.EVENT_NAMES.values()
            ),
            inline=False
        )

        embed.set_footer(
            text="Use /logging 1 toggle to change which events are logged."
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="toggle",
        description="Enable or disable a logging event"
    )
    @app_commands.describe(
        event="The logging event",
        enabled="Whether this event should be logged"
    )
    @app_commands.choices(
        event=[
            app_commands.Choice(
                name="Member events",
                value="members"
            ),
            app_commands.Choice(
                name="Message events",
                value="messages"
            ),
            app_commands.Choice(
                name="Channel events",
                value="channels"
            ),
            app_commands.Choice(
                name="Role events",
                value="roles"
            ),
            app_commands.Choice(
                name="Voice events",
                value="voice"
            ),
            app_commands.Choice(
                name="Moderation events",
                value="moderation"
            ),
            app_commands.Choice(
                name="Server events",
                value="server"
            ),
        ]
    )
    @app_commands.choices(
        enabled=[
            app_commands.Choice(
                name="Enabled",
                value="true"
            ),
            app_commands.Choice(
                name="Disabled",
                value="false"
            ),
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def toggle(
        self,
        interaction: discord.Interaction,
        event: app_commands.Choice[str],
        enabled: app_commands.Choice[str]
    ):

        guild_id = interaction.guild.id
        events = self.get_events(guild_id)

        if enabled.value == "true":
            events.add(event.value)
            status = "enabled"
        else:
            events.discard(event.value)
            status = "disabled"

        self.set_events(
            guild_id,
            events
        )

        await interaction.response.send_message(
            embed=self.log_embed(
                "Logging updated",
                f"**{self.EVENT_NAMES[event.value]}** has been {status}."
            )
        )

    @app_commands.command(
        name="config",
        description="View the server's logging configuration"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def config(
        self,
        interaction: discord.Interaction
    ):

        row = self.get_config(
            interaction.guild.id
        )

        if row["channel_id"]:
            channel = interaction.guild.get_channel(
                row["channel_id"]
            )

            channel_text = (
                channel.mention
                if channel
                else f"<#{row['channel_id']}>"
            )

        else:
            channel_text = "Not configured"

        enabled_events = self.get_events(
            interaction.guild.id
        )

        event_lines = []

        for key, name in self.EVENT_NAMES.items():

            if key in enabled_events:
                status = "Enabled"
            else:
                status = "Disabled"

            event_lines.append(
                f"**{name}** — {status}"
            )

        embed = discord.Embed(
            title="Logging Configuration",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="Status",
            value=(
                "Enabled"
                if row["enabled"]
                else "Disabled"
            ),
            inline=True
        )

        embed.add_field(
            name="Channel",
            value=channel_text,
            inline=True
        )

        embed.add_field(
            name="Events",
            value="\n".join(event_lines),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="disable",
        description="Disable server logging"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def disable(
        self,
        interaction: discord.Interaction
    ):

        self.update_config(
            interaction.guild.id,
            "enabled",
            0
        )

        await interaction.response.send_message(
            embed=self.log_embed(
                "Logging disabled",
                "Server logging has been disabled."
            )
        )

    @app_commands.command(
        name="help",
        description="View logging commands"
    )
    async def help(
        self,
        interaction: discord.Interaction
    ):

        embed = discord.Embed(
            title="Logging",
            description="Configure automatic server event logging.",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="⚙️ Configuration",
            value=(
                "`/logging 1 setup` — configure logging\n"
                "`/logging 1 config` — view the current configuration\n"
                "`/logging 1 toggle` — enable or disable an event\n"
                "`/logging 1 disable` — disable logging"
            ),
            inline=False
        )

        embed.add_field(
            name="📋 Events",
            value=(
                "• Member events\n"
                "• Message events\n"
                "• Channel events\n"
                "• Role events\n"
                "• Voice events\n"
                "• Moderation events\n"
                "• Server events"
            ),
            inline=False
        )

        embed.set_footer(
            text="You need the Manage Server permission to configure logging."
        )

        await interaction.response.send_message(
            embed=embed
        )

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member
    ):

        embed = self.log_embed(
            "Member joined",
            f"{member.mention} joined the server."
        )

        embed.add_field(
            name="Username",
            value=f"{member} (`{member.id}`)",
            inline=False
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        await self.send_log(
            member.guild,
            "members",
            embed
        )

    @commands.Cog.listener()
    async def on_member_remove(
        self,
        member: discord.Member
    ):

        embed = self.log_embed(
            "Member left",
            f"**{member}** left the server."
        )

        embed.add_field(
            name="User ID",
            value=f"`{member.id}`",
            inline=True
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        await self.send_log(
            member.guild,
            "members",
            embed
        )

    @commands.Cog.listener()
    async def on_raw_message_delete(
        self,
        payload: discord.RawMessageDeleteEvent
    ):

        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(
            payload.guild_id
        )

        if guild is None:
            return

        message = payload.cached_message

        if message:

            content = message.content or "*No message content*"

            if len(content) > 1000:
                content = content[:1000] + "..."

            description = (
                f"Message deleted in <#{payload.channel_id}>."
            )

            embed = self.log_embed(
                "Message deleted",
                description
            )

            embed.add_field(
                name="Author",
                value=f"{message.author.mention} (`{message.author.id}`)",
                inline=False
            )

            embed.add_field(
                name="Content",
                value=content,
                inline=False
            )

        else:

            embed = self.log_embed(
                "Message deleted",
                f"Message `{payload.message_id}` was deleted in "
                f"<#{payload.channel_id}>."
            )

        embed.set_footer(
            text=f"Message ID: {payload.message_id}"
        )

        await self.send_log(
            guild,
            "messages",
            embed
        )

    @commands.Cog.listener()
    async def on_raw_message_edit(
        self,
        payload: discord.RawMessageUpdateEvent
    ):

        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(
            payload.guild_id
        )

        if guild is None:
            return

        message = payload.cached_message

        if message is None:
            return

        if message.author.bot:
            return

        before = message.content or "*No content*"
        after = payload.data.get("content")

        if after is None:
            return

        if before == after:
            return

        if len(before) > 900:
            before = before[:900] + "..."

        if len(after) > 900:
            after = after[:900] + "..."

        embed = self.log_embed(
            "Message edited",
            f"Message edited in <#{payload.channel_id}>."
        )

        embed.add_field(
            name="Author",
            value=f"{message.author.mention} (`{message.author.id}`)",
            inline=False
        )

        embed.add_field(
            name="Before",
            value=before,
            inline=False
        )

        embed.add_field(
            name="After",
            value=after,
            inline=False
        )

        embed.set_footer(
            text=f"Message ID: {payload.message_id}"
        )

        await self.send_log(
            guild,
            "messages",
            embed
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self,
        channel
    ):

        if channel.guild is None:
            return

        embed = self.log_embed(
            "Channel created",
            f"{channel.mention if hasattr(channel, 'mention') else channel.name} "
            f"was created."
        )

        embed.add_field(
            name="Type",
            value=str(channel.type),
            inline=True
        )

        embed.add_field(
            name="Channel ID",
            value=f"`{channel.id}`",
            inline=True
        )

        await self.send_log(
            channel.guild,
            "channels",
            embed
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self,
        channel
    ):

        if channel.guild is None:
            return

        embed = self.log_embed(
            "Channel deleted",
            f"**{channel.name}** was deleted."
        )

        embed.add_field(
            name="Type",
            value=str(channel.type),
            inline=True
        )

        embed.add_field(
            name="Channel ID",
            value=f"`{channel.id}`",
            inline=True
        )

        await self.send_log(
            channel.guild,
            "channels",
            embed
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before,
        after
    ):

        changes = []

        if before.name != after.name:
            changes.append(
                f"**Name:** `{before.name}` → `{after.name}`"
            )

        if hasattr(before, "topic") and hasattr(after, "topic"):
            if before.topic != after.topic:
                changes.append("**Topic:** changed")

        if not changes:
            return

        embed = self.log_embed(
            "Channel updated",
            f"{after.mention} was updated."
        )

        embed.add_field(
            name="Changes",
            value="\n".join(changes),
            inline=False
        )

        await self.send_log(
            after.guild,
            "channels",
            embed
        )

    @commands.Cog.listener()
    async def on_guild_role_create(
        self,
        role
    ):

        embed = self.log_embed(
            "Role created",
            f"{role.mention} was created."
        )

        embed.add_field(
            name="Role ID",
            value=f"`{role.id}`",
            inline=True
        )

        await self.send_log(
            role.guild,
            "roles",
            embed
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(
        self,
        role
    ):

        embed = self.log_embed(
            "Role deleted",
            f"**{role.name}** was deleted."
        )

        embed.add_field(
            name="Role ID",
            value=f"`{role.id}`",
            inline=True
        )

        await self.send_log(
            role.guild,
            "roles",
            embed
        )

    @commands.Cog.listener()
    async def on_guild_role_update(
        self,
        before,
        after
    ):

        changes = []

        if before.name != after.name:
            changes.append(
                f"**Name:** `{before.name}` → `{after.name}`"
            )

        if before.position != after.position:
            changes.append(
                f"**Position:** `{before.position}` → `{after.position}`"
            )

        if before.mentionable != after.mentionable:
            changes.append(
                f"**Mentionable:** `{before.mentionable}` → "
                f"`{after.mentionable}`"
            )

        if before.hoist != after.hoist:
            changes.append(
                f"**Displayed separately:** `{before.hoist}` → "
                f"`{after.hoist}`"
            )

        if not changes:
            return

        embed = self.log_embed(
            "Role updated",
            f"{after.mention} was updated."
        )

        embed.add_field(
            name="Changes",
            value="\n".join(changes),
            inline=False
        )

        await self.send_log(
            after.guild,
            "roles",
            embed
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member,
        before,
        after
    ):

        if before.channel == after.channel:
            return

        if before.channel is None:

            description = (
                f"{member.mention} joined {after.channel.mention}."
            )

        elif after.channel is None:

            description = (
                f"{member.mention} left {before.channel.mention}."
            )

        else:

            description = (
                f"{member.mention} moved from "
                f"{before.channel.mention} to "
                f"{after.channel.mention}."
            )

        embed = self.log_embed(
            "Voice activity",
            description
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        await self.send_log(
            member.guild,
            "voice",
            embed
        )

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild,
        user
    ):

        actor = await self.get_audit_actor(
            guild,
            discord.AuditLogAction.ban,
            user.id
        )

        description = (
            f"{user.mention if hasattr(user, 'mention') else user} "
            f"was banned."
        )

        if actor:
            description += f"\n**Moderator:** {actor.mention}"

        embed = self.log_embed(
            "Member banned",
            description
        )

        embed.add_field(
            name="User",
            value=f"{user} (`{user.id}`)",
            inline=False
        )

        await self.send_log(
            guild,
            "moderation",
            embed
        )

    @commands.Cog.listener()
    async def on_member_unban(
        self,
        guild,
        user
    ):

        actor = await self.get_audit_actor(
            guild,
            discord.AuditLogAction.unban,
            user.id
        )

        description = (
            f"**{user}** was unbanned."
        )

        if actor:
            description += f"\n**Moderator:** {actor.mention}"

        embed = self.log_embed(
            "Member unbanned",
            description
        )

        embed.add_field(
            name="User ID",
            value=f"`{user.id}`",
            inline=True
        )

        await self.send_log(
            guild,
            "moderation",
            embed
        )

    @commands.Cog.listener()
    async def on_guild_update(
        self,
        before,
        after
    ):

        changes = []

        if before.name != after.name:
            changes.append(
                f"**Name:** `{before.name}` → `{after.name}`"
            )

        if before.icon != after.icon:
            changes.append(
                "**Icon:** changed"
            )

        if before.banner != after.banner:
            changes.append(
                "**Banner:** changed"
            )

        if before.description != after.description:
            changes.append(
                "**Description:** changed"
            )

        if not changes:
            return

        embed = self.log_embed(
            "Server updated",
            "\n".join(changes)
        )

        await self.send_log(
            after,
            "server",
            embed
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

        await interaction.response.send_message(
            embed=self.error_embed(
                "Something went wrong while running this command."
            ),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Logging(bot))