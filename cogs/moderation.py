import sqlite3

from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands, Interaction
from discord.ext import commands

class Moderation(commands.GroupCog, group_name="moderation"):
    def __init__(self, bot):
        self.bot = bot

        self.db = sqlite3.connect("db/moderation.db")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS warning_counters (
                guild_id INTEGER PRIMARY KEY,
                next_id INTEGER NOT NULL DEFAULT 1
            )
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                PRIMARY KEY (guild_id, id)
            )
        """)

        self.db.commit()

    def cog_unload(self):
        self.db.close()

    def error_embed(self, title, description):
        return discord.Embed(
            title=title,
            description=description,
            color=discord.Color.red()
        )

    def success_embed(self, title, description):
        return discord.Embed(
            title=title,
            description=description,
            color=discord.Color.orange()
        )

    async def send_error(
        self,
        interaction: Interaction,
        title,
        description
    ):
        await interaction.response.send_message(
            embed=self.error_embed(title, description),
            ephemeral=True
        )

    def get_warning_count(self, guild_id, user_id):
        result = self.db.execute(
            """
            SELECT COUNT(*) AS count
            FROM warnings
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id)
        ).fetchone()

        return result["count"]

    def get_next_warning_id(self, guild_id):
        """
        Gets the next warning ID for a server.

        Warning IDs:
        - Start at 1
        - Increment by 1
        - Never get reused after deletion
        """

        row = self.db.execute(
            """
            SELECT next_id
            FROM warning_counters
            WHERE guild_id = ?
            """,
            (guild_id,)
        ).fetchone()

        if row is None:
            warning_id = 1

            self.db.execute(
                """
                INSERT INTO warning_counters
                (guild_id, next_id)
                VALUES (?, ?)
                """,
                (guild_id, 2)
            )
        else:
            warning_id = row["next_id"]

            self.db.execute(
                """
                UPDATE warning_counters
                SET next_id = ?
                WHERE guild_id = ?
                """,
                (warning_id + 1, guild_id)
            )

        return warning_id

    @app_commands.command(
        name="ban",
        description="ban a member from the server"
    )
    @app_commands.describe(
        member="the member you want to ban",
        reason="the reason for the ban",
        delete_days="number of days of messages to delete"
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self,
        interaction: Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
        delete_days: app_commands.Range[int, 0, 7] = 0
    ):

        if member == interaction.user:
            await self.send_error(
                interaction,
                "Cannot Ban User",
                "You cannot ban yourself."
            )
            return

        if member == interaction.guild.owner:
            await self.send_error(
                interaction,
                "Cannot Ban User",
                "You cannot ban the server owner."
            )
            return

        if member.top_role >= interaction.user.top_role:
            await self.send_error(
                interaction,
                "Cannot Ban User",
                "That member has an equal or higher role than you."
            )
            return

        if member.top_role >= interaction.guild.me.top_role:
            await self.send_error(
                interaction,
                "Cannot Ban User",
                "I cannot ban that member because their role is equal to or higher than mine."
            )
            return

        try:
            await member.ban(
                reason=f"{reason} | Moderator: {interaction.user}",
                delete_message_days=delete_days
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Ban Failed",
                "I don't have permission to ban that member."
            )
            return

        except discord.HTTPException:
            await self.send_error(
                interaction,
                "Ban Failed",
                "Discord rejected the ban request."
            )
            return

        embed = self.success_embed(
            "🔨 Member Banned",
            f"{member.mention} has been banned."
        )

        embed.add_field(
            name="👤 Member",
            value=f"{member} (`{member.id}`)",
            inline=False
        )

        embed.add_field(
            name="📝 Reason",
            value=reason,
            inline=False
        )

        embed.add_field(
            name="👮 Moderator",
            value=interaction.user.mention,
            inline=True
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="kick",
        description="kick a member from the server"
    )
    @app_commands.describe(
        member="the member you want to kick",
        reason="the reason for the kick"
    )
    @app_commands.default_permissions(kick_members=True)
    async def kick(
        self,
        interaction: Interaction,
        member: discord.Member,
        reason: str = "No reason provided"
    ):

        if member == interaction.user:
            await self.send_error(
                interaction,
                "Cannot Kick User",
                "You cannot kick yourself."
            )
            return

        if member == interaction.guild.owner:
            await self.send_error(
                interaction,
                "Cannot Kick User",
                "You cannot kick the server owner."
            )
            return

        if member.top_role >= interaction.user.top_role:
            await self.send_error(
                interaction,
                "Cannot Kick User",
                "That member has an equal or higher role than you."
            )
            return

        if member.top_role >= interaction.guild.me.top_role:
            await self.send_error(
                interaction,
                "Cannot Kick User",
                "I cannot kick that member because their role is equal to or higher than mine."
            )
            return

        try:
            await member.kick(
                reason=f"{reason} | Moderator: {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Kick Failed",
                "I don't have permission to kick that member."
            )
            return

        except discord.HTTPException:
            await self.send_error(
                interaction,
                "Kick Failed",
                "Discord rejected the kick request."
            )
            return

        embed = self.success_embed(
            "👢 Member Kicked",
            f"{member.mention} has been kicked."
        )

        embed.add_field(
            name="👤 Member",
            value=f"{member} (`{member.id}`)",
            inline=False
        )

        embed.add_field(
            name="📝 Reason",
            value=reason,
            inline=False
        )

        embed.add_field(
            name="👮 Moderator",
            value=interaction.user.mention,
            inline=True
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="timeout",
        description="timeout a member"
    )
    @app_commands.describe(
        member="the member you want to timeout",
        duration="timeout duration, for example 10m, 1h or 1d",
        reason="the reason for the timeout"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: Interaction,
        member: discord.Member,
        duration: str,
        reason: str = "No reason provided"
    ):

        if member == interaction.user:
            await self.send_error(
                interaction,
                "Cannot Timeout User",
                "You cannot timeout yourself."
            )
            return

        if member == interaction.guild.owner:
            await self.send_error(
                interaction,
                "Cannot Timeout User",
                "You cannot timeout the server owner."
            )
            return

        if member.top_role >= interaction.user.top_role:
            await self.send_error(
                interaction,
                "Cannot Timeout User",
                "That member has an equal or higher role than you."
            )
            return

        if member.top_role >= interaction.guild.me.top_role:
            await self.send_error(
                interaction,
                "Cannot Timeout User",
                "I cannot timeout that member because their role is equal to or higher than mine."
            )
            return

        duration_lower = duration.lower().strip()

        try:
            if duration_lower.endswith("s"):
                amount = int(duration_lower[:-1])
                delta = timedelta(seconds=amount)

            elif duration_lower.endswith("m"):
                amount = int(duration_lower[:-1])
                delta = timedelta(minutes=amount)

            elif duration_lower.endswith("h"):
                amount = int(duration_lower[:-1])
                delta = timedelta(hours=amount)

            elif duration_lower.endswith("d"):
                amount = int(duration_lower[:-1])
                delta = timedelta(days=amount)

            else:
                raise ValueError

        except ValueError:
            await self.send_error(
                interaction,
                "Invalid Duration",
                "Use a duration such as `30s`, `10m`, `2h` or `7d`."
            )
            return

        if delta <= timedelta(0):
            await self.send_error(
                interaction,
                "Invalid Duration",
                "The timeout duration must be greater than zero."
            )
            return

        if delta > timedelta(days=28):
            await self.send_error(
                interaction,
                "Invalid Duration",
                "Discord allows a maximum timeout of 28 days."
            )
            return

        until = datetime.now(timezone.utc) + delta

        try:
            await member.timeout(
                until,
                reason=f"{reason} | Moderator: {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Timeout Failed",
                "I don't have permission to timeout that member."
            )
            return

        except discord.HTTPException:
            await self.send_error(
                interaction,
                "Timeout Failed",
                "Discord rejected the timeout request."
            )
            return

        embed = self.success_embed(
            "⏱️ Member Timed Out",
            f"{member.mention} has been timed out."
        )

        embed.add_field(
            name="👤 Member",
            value=f"{member} (`{member.id}`)",
            inline=False
        )

        embed.add_field(
            name="⏰ Duration",
            value=duration_lower,
            inline=True
        )

        embed.add_field(
            name="📝 Reason",
            value=reason,
            inline=False
        )

        embed.add_field(
            name="👮 Moderator",
            value=interaction.user.mention,
            inline=True
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="untimeout",
        description="remove a member's timeout"
    )
    @app_commands.describe(
        member="the member whose timeout you want to remove",
        reason="the reason for removing the timeout"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout(
        self,
        interaction: Interaction,
        member: discord.Member,
        reason: str = "No reason provided"
    ):

        try:
            await member.timeout(
                None,
                reason=f"{reason} | Moderator: {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Untimeout Failed",
                "I don't have permission to remove that timeout."
            )
            return

        except discord.HTTPException:
            await self.send_error(
                interaction,
                "Untimeout Failed",
                "Discord rejected the request."
            )
            return

        embed = self.success_embed(
            "⏱️ Timeout Removed",
            f"{member.mention}'s timeout has been removed."
        )

        embed.add_field(
            name="👮 Moderator",
            value=interaction.user.mention,
            inline=True
        )

        embed.add_field(
            name="📝 Reason",
            value=reason,
            inline=False
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="warn",
        description="warn a member"
    )
    @app_commands.describe(
        member="the member you want to warn",
        reason="the reason for the warning"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: Interaction,
        member: discord.Member,
        reason: str = "No reason provided"
    ):

        if member == interaction.user:
            await self.send_error(
                interaction,
                "Cannot Warn User",
                "You cannot warn yourself."
            )
            return

        if member == interaction.guild.owner:
            await self.send_error(
                interaction,
                "Cannot Warn User",
                "You cannot warn the server owner."
            )
            return

        if member.top_role >= interaction.user.top_role:
            await self.send_error(
                interaction,
                "Cannot Warn User",
                "That member has an equal or higher role than you."
            )
            return

        warning_id = self.get_next_warning_id(
            interaction.guild.id
        )

        timestamp = datetime.now(timezone.utc).isoformat()

        self.db.execute(
            """
            INSERT INTO warnings
            (
                id,
                guild_id,
                user_id,
                moderator_id,
                reason,
                timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                warning_id,
                interaction.guild.id,
                member.id,
                interaction.user.id,
                reason,
                timestamp
            )
        )

        self.db.commit()

        count = self.get_warning_count(
            interaction.guild.id,
            member.id
        )

        embed = self.success_embed(
            "⚠️ Member Warned",
            f"{member.mention} has been warned."
        )

        embed.add_field(
            name="🆔 Warning ID",
            value=f"`#{warning_id}`",
            inline=True
        )

        embed.add_field(
            name="⚠️ Total Warnings",
            value=str(count),
            inline=True
        )

        embed.add_field(
            name="👤 Member",
            value=f"{member} (`{member.id}`)",
            inline=False
        )

        embed.add_field(
            name="📝 Reason",
            value=reason,
            inline=False
        )

        embed.add_field(
            name="👮 Moderator",
            value=interaction.user.mention,
            inline=True
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="warnings",
        description="view a member's warnings"
    )
    @app_commands.describe(
        member="the member whose warnings you want to view"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(
        self,
        interaction: Interaction,
        member: discord.Member
    ):

        rows = self.db.execute(
            """
            SELECT *
            FROM warnings
            WHERE guild_id = ?
            AND user_id = ?
            ORDER BY id DESC
            """,
            (
                interaction.guild.id,
                member.id
            )
        ).fetchall()

        embed = self.success_embed(
            f"⚠️ Warnings — {member.display_name}",
            f"{member.mention} has **{len(rows)}** warning(s)."
        )

        if not rows:
            embed.description = (
                f"{member.mention} has no warnings."
            )

        else:
            for row in rows[:10]:

                try:
                    moderator = interaction.guild.get_member(
                        row["moderator_id"]
                    )

                    moderator_text = (
                        moderator.mention
                        if moderator
                        else f"`{row['moderator_id']}`"
                    )

                    timestamp = datetime.fromisoformat(
                        row["timestamp"]
                    )

                    date = discord.utils.format_dt(
                        timestamp,
                        style="R"
                    )

                except Exception:
                    moderator_text = (
                        f"`{row['moderator_id']}`"
                    )
                    date = "Unknown"

                embed.add_field(
                    name=f"Warning #{row['id']}",
                    value=(
                        f"**Reason:** {row['reason']}\n"
                        f"**Moderator:** {moderator_text}\n"
                        f"**Date:** {date}"
                    ),
                    inline=False
                )

            if len(rows) > 10:
                embed.set_footer(
                    text=f"Showing 10 of {len(rows)} warnings • User ID: {member.id}"
                )
            else:
                embed.set_footer(
                    text=f"User ID: {member.id}"
                )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="unwarn",
        description="remove a warning from a member"
    )
    @app_commands.describe(
        member="the member whose warning you want to remove",
        warning_id="the warning ID to remove"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def unwarn(
        self,
        interaction: Interaction,
        member: discord.Member,
        warning_id: int
    ):

        warning = self.db.execute(
            """
            SELECT *
            FROM warnings
            WHERE id = ?
            AND guild_id = ?
            AND user_id = ?
            """,
            (
                warning_id,
                interaction.guild.id,
                member.id
            )
        ).fetchone()

        if warning is None:
            await self.send_error(
                interaction,
                "Warning Not Found",
                "That warning doesn't exist for this member."
            )
            return

        self.db.execute(
            """
            DELETE FROM warnings
            WHERE id = ?
            AND guild_id = ?
            AND user_id = ?
            """,
            (
                warning_id,
                interaction.guild.id,
                member.id
            )
        )

        self.db.commit()

        embed = self.success_embed(
            "✅ Warning Removed",
            f"Warning `#{warning_id}` has been removed from {member.mention}."
        )

        embed.add_field(
            name="🆔 Warning ID",
            value=f"`#{warning_id}`",
            inline=True
        )

        embed.add_field(
            name="👤 Member",
            value=f"{member} (`{member.id}`)",
            inline=False
        )

        embed.add_field(
            name="📝 Original Reason",
            value=warning["reason"],
            inline=False
        )

        embed.add_field(
            name="👮 Moderator",
            value=interaction.user.mention,
            inline=True
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="purge",
        description="delete multiple messages"
    )
    @app_commands.describe(
        amount="number of messages to delete"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge(
        self,
        interaction: Interaction,
        amount: app_commands.Range[int, 1, 100]
    ):

        if not isinstance(
            interaction.channel,
            discord.TextChannel
        ):
            await self.send_error(
                interaction,
                "Invalid Channel",
                "This command can only be used in a text channel."
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        try:
            deleted = await interaction.channel.purge(
                limit=amount
            )

        except discord.Forbidden:
            await interaction.followup.send(
                embed=self.error_embed(
                    "Purge Failed",
                    "I don't have permission to delete messages here."
                ),
                ephemeral=True
            )
            return

        embed = self.success_embed(
            "🧹 Messages Deleted",
            f"Deleted **{len(deleted)}** message(s)."
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="clear",
        description="clear multiple messages"
    )
    @app_commands.describe(
        amount="number of messages to delete"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def clear(
        self,
        interaction: Interaction,
        amount: app_commands.Range[int, 1, 100]
    ):

        if not isinstance(
            interaction.channel,
            discord.TextChannel
        ):
            await self.send_error(
                interaction,
                "Invalid Channel",
                "This command can only be used in a text channel."
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        try:
            deleted = await interaction.channel.purge(
                limit=amount
            )

        except discord.Forbidden:
            await interaction.followup.send(
                embed=self.error_embed(
                    "Clear Failed",
                    "I don't have permission to delete messages here."
                ),
                ephemeral=True
            )
            return

        embed = self.success_embed(
            "🧹 Messages Cleared",
            f"Deleted **{len(deleted)}** message(s)."
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="slowmode",
        description="set the channel slowmode"
    )
    @app_commands.describe(
        seconds="slowmode delay in seconds, 0 to disable"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(
        self,
        interaction: Interaction,
        seconds: app_commands.Range[int, 0, 21600]
    ):

        if not isinstance(
            interaction.channel,
            discord.TextChannel
        ):
            await self.send_error(
                interaction,
                "Invalid Channel",
                "Slowmode can only be configured in text channels."
            )
            return

        try:
            await interaction.channel.edit(
                slowmode_delay=seconds,
                reason=f"Slowmode changed by {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Slowmode Failed",
                "I don't have permission to manage this channel."
            )
            return

        if seconds == 0:
            description = (
                "Slowmode has been **disabled**."
            )
        else:
            description = (
                f"Slowmode has been set to **{seconds} seconds**."
            )

        await interaction.response.send_message(
            embed=self.success_embed(
                "🐌 Slowmode Updated",
                description
            )
        )

    @app_commands.command(
        name="lock",
        description="lock the current channel"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def lock(
        self,
        interaction: Interaction
    ):

        if not isinstance(
            interaction.channel,
            discord.TextChannel
        ):
            await self.send_error(
                interaction,
                "Invalid Channel",
                "This command can only be used in a text channel."
            )
            return

        everyone = interaction.guild.default_role

        overwrite = interaction.channel.overwrites_for(
            everyone
        )

        overwrite.send_messages = False

        try:
            await interaction.channel.set_permissions(
                everyone,
                overwrite=overwrite,
                reason=f"Channel locked by {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Lock Failed",
                "I don't have permission to manage this channel."
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                "🔒 Channel Locked",
                f"{interaction.channel.mention} has been locked."
            )
        )

    @app_commands.command(
        name="unlock",
        description="unlock the current channel"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(
        self,
        interaction: Interaction
    ):

        if not isinstance(
            interaction.channel,
            discord.TextChannel
        ):
            await self.send_error(
                interaction,
                "Invalid Channel",
                "This command can only be used in a text channel."
            )
            return

        everyone = interaction.guild.default_role

        overwrite = interaction.channel.overwrites_for(
            everyone
        )

        overwrite.send_messages = None

        try:
            await interaction.channel.set_permissions(
                everyone,
                overwrite=overwrite,
                reason=f"Channel unlocked by {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Unlock Failed",
                "I don't have permission to manage this channel."
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                "🔓 Channel Unlocked",
                f"{interaction.channel.mention} has been unlocked."
            )
        )

    @app_commands.command(
        name="hide",
        description="hide the current channel from @everyone"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def hide(
        self,
        interaction: Interaction
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.abc.GuildChannel
        ):
            await self.send_error(
                interaction,
                "Invalid Channel",
                "This command can only be used inside a server."
            )
            return

        everyone = interaction.guild.default_role

        overwrite = channel.overwrites_for(
            everyone
        )

        overwrite.view_channel = False

        try:
            await channel.set_permissions(
                everyone,
                overwrite=overwrite,
                reason=f"Channel hidden by {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Hide Failed",
                "I don't have permission to manage this channel."
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                "🙈 Channel Hidden",
                f"{channel.mention} has been hidden from @everyone."
            )
        )

    @app_commands.command(
        name="unhide",
        description="unhide the current channel"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def unhide(
        self,
        interaction: Interaction
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.abc.GuildChannel
        ):
            await self.send_error(
                interaction,
                "Invalid Channel",
                "This command can only be used inside a server."
            )
            return

        everyone = interaction.guild.default_role

        overwrite = channel.overwrites_for(
            everyone
        )

        overwrite.view_channel = None

        try:
            await channel.set_permissions(
                everyone,
                overwrite=overwrite,
                reason=f"Channel unhidden by {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Unhide Failed",
                "I don't have permission to manage this channel."
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                "👀 Channel Unhidden",
                f"{channel.mention} has been unhidden."
            )
        )

    @app_commands.command(
        name="nick",
        description="change a member's nickname"
    )
    @app_commands.describe(
        member="the member whose nickname you want to change",
        nickname="the new nickname, or leave blank to remove it"
    )
    @app_commands.default_permissions(manage_nicknames=True)
    async def nick(
        self,
        interaction: Interaction,
        member: discord.Member,
        nickname: str | None = None
    ):

        if member == interaction.guild.owner:
            await self.send_error(
                interaction,
                "Cannot Change Nickname",
                "You cannot change the server owner's nickname."
            )
            return

        if member.top_role >= interaction.user.top_role:
            await self.send_error(
                interaction,
                "Cannot Change Nickname",
                "That member has an equal or higher role than you."
            )
            return

        if member.top_role >= interaction.guild.me.top_role:
            await self.send_error(
                interaction,
                "Cannot Change Nickname",
                "I cannot change that member's nickname because their role is equal to or higher than mine."
            )
            return

        try:
            await member.edit(
                nick=nickname,
                reason=f"Nickname changed by {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Nickname Failed",
                "I don't have permission to change that member's nickname."
            )
            return

        new_name = nickname or "their username"

        await interaction.response.send_message(
            embed=self.success_embed(
                "🏷️ Nickname Updated",
                f"{member.mention}'s nickname has been changed to **{new_name}**."
            )
        )

    @app_commands.command(
        name="deafen",
        description="server-deafen a member"
    )
    @app_commands.describe(
        member="the member you want to deafen",
        reason="the reason for the deafen"
    )
    @app_commands.default_permissions(deafen_members=True)
    async def deafen(
        self,
        interaction: Interaction,
        member: discord.Member,
        reason: str = "No reason provided"
    ):

        if not member.voice:
            await self.send_error(
                interaction,
                "Member Not In Voice",
                f"{member.mention} is not currently in a voice channel."
            )
            return

        if member.top_role >= interaction.user.top_role:
            await self.send_error(
                interaction,
                "Cannot Deafen User",
                "That member has an equal or higher role than you."
            )
            return

        try:
            await member.edit(
                deafen=True,
                reason=f"{reason} | Moderator: {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Deafen Failed",
                "I don't have permission to deafen that member."
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                "🔇 Member Deafened",
                f"{member.mention} has been server-deafened."
            )
        )

    @app_commands.command(
        name="undeafen",
        description="remove a member's server deafen"
    )
    @app_commands.default_permissions(deafen_members=True)
    async def undeafen(
        self,
        interaction: Interaction,
        member: discord.Member
    ):

        try:
            await member.edit(
                deafen=False,
                reason=f"Server deafen removed by {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Undeafen Failed",
                "I don't have permission to undeafen that member."
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                "🔊 Member Undeafened",
                f"{member.mention} has been server-undeafened."
            )
        )

    @app_commands.command(
        name="move",
        description="move a member to another voice channel"
    )
    @app_commands.describe(
        member="the member you want to move",
        channel="the voice channel to move them to"
    )
    @app_commands.default_permissions(move_members=True)
    async def move(
        self,
        interaction: Interaction,
        member: discord.Member,
        channel: discord.VoiceChannel
    ):

        if not member.voice:
            await self.send_error(
                interaction,
                "Member Not In Voice",
                f"{member.mention} is not currently in a voice channel."
            )
            return

        try:
            await member.move_to(
                channel,
                reason=f"Moved by {interaction.user}"
            )

        except discord.Forbidden:
            await self.send_error(
                interaction,
                "Move Failed",
                "I don't have permission to move that member."
            )
            return

        except discord.HTTPException:
            await self.send_error(
                interaction,
                "Move Failed",
                "Discord rejected the move request."
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                "🔀 Member Moved",
                f"{member.mention} has been moved to {channel.mention}."
            )
        )

async def setup(bot):
    await bot.add_cog(Moderation(bot))