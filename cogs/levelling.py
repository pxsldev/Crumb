import asyncio
import os
import random
import sqlite3
import time
import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = "db/levelling.db"
EMBED_COLOR = discord.Color.orange()
ERROR_COLOR = discord.Color.red()
XP_MIN = 15
XP_MAX = 25
XP_COOLDOWN = 60
XP_PER_LEVEL = 100

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            xp_min INTEGER NOT NULL DEFAULT 15,
            xp_max INTEGER NOT NULL DEFAULT 25,
            cooldown INTEGER NOT NULL DEFAULT 60
        )
    """)
    conn.commit()
    return conn

class Levelling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}
        self.locks = {}
        conn = get_connection()
        conn.close()

    def get_lock(self, guild_id):
        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()
        return self.locks[guild_id]

    def get_settings(self, guild_id):
        conn = get_connection()
        row = conn.execute(
            """
            SELECT enabled, xp_min, xp_max, cooldown
            FROM settings
            WHERE guild_id = ?
            """,
            (guild_id,)
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO settings
                    (guild_id, enabled, xp_min, xp_max, cooldown)
                VALUES (?, 1, ?, ?, ?)
                """,
                (
                    guild_id,
                    XP_MIN,
                    XP_MAX,
                    XP_COOLDOWN
                )
            )
            conn.commit()
            row = (
                1,
                XP_MIN,
                XP_MAX,
                XP_COOLDOWN
            )

        conn.close()
        return {
            "enabled": bool(row[0]),
            "xp_min": row[1],
            "xp_max": row[2],
            "cooldown": row[3]
        }

    def update_settings(
        self,
        guild_id,
        enabled=None,
        xp_min=None,
        xp_max=None,
        cooldown=None
    ):
        settings = self.get_settings(guild_id)

        if enabled is not None:
            settings["enabled"] = enabled
        if xp_min is not None:
            settings["xp_min"] = xp_min
        if xp_max is not None:
            settings["xp_max"] = xp_max
        if cooldown is not None:
            settings["cooldown"] = cooldown

        conn = get_connection()
        conn.execute(
            """
            INSERT INTO settings
                (guild_id, enabled, xp_min, xp_max, cooldown)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET
                enabled = excluded.enabled,
                xp_min = excluded.xp_min,
                xp_max = excluded.xp_max,
                cooldown = excluded.cooldown
            """,
            (
                guild_id,
                int(settings["enabled"]),
                settings["xp_min"],
                settings["xp_max"],
                settings["cooldown"]
            )
        )
        conn.commit()
        conn.close()

    def get_user(self, guild_id, user_id):
        conn = get_connection()
        row = conn.execute(
            """
            SELECT xp, level
            FROM users
            WHERE guild_id = ?
              AND user_id = ?
            """,
            (
                guild_id,
                user_id
            )
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO users
                    (guild_id, user_id, xp, level)
                VALUES (?, ?, 0, 0)
                """,
                (
                    guild_id,
                    user_id
                )
            )
            conn.commit()
            row = (
                0,
                0
            )

        conn.close()
        return {
            "xp": row[0],
            "level": row[1]
        }

    def set_user_xp(
        self,
        guild_id,
        user_id,
        xp
    ):
        xp = max(0, xp)
        level = self.calculate_level(xp)
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO users
                (guild_id, user_id, xp, level)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
                xp = excluded.xp,
                level = excluded.level
            """,
            (
                guild_id,
                user_id,
                xp,
                level
            )
        )
        conn.commit()
        conn.close()
        return xp, level

    def add_xp(
        self,
        guild_id,
        user_id,
        amount
    ):
        data = self.get_user(guild_id, user_id)
        old_level = data["level"]
        new_xp = data["xp"] + amount
        new_level = self.calculate_level(new_xp)

        self.set_user_xp(
            guild_id,
            user_id,
            new_xp
        )

        return (
            new_xp,
            new_level,
            new_level > old_level
        )

    def xp_for_level(self, level):
        return XP_PER_LEVEL * level * level

    def xp_for_next_level(self, level):
        return self.xp_for_level(level + 1)

    def calculate_level(self, xp):
        level = 0
        while xp >= self.xp_for_level(level + 1):
            level += 1
        return level

    def get_rank(
        self,
        guild_id,
        user_id
    ):
        conn = get_connection()
        row = conn.execute(
            """
            SELECT COUNT(*) + 1
            FROM users
            WHERE guild_id = ?
              AND xp > COALESCE(
                  (
                      SELECT xp
                      FROM users
                      WHERE guild_id = ?
                        AND user_id = ?
                  ),
                  0
              )
            """,
            (
                guild_id,
                guild_id,
                user_id
            )
        ).fetchone()
        conn.close()
        return row[0] if row else 1

    def get_leaderboard(
        self,
        guild_id,
        limit=10
    ):
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT user_id, xp, level
            FROM users
            WHERE guild_id = ?
            ORDER BY xp DESC
            LIMIT ?
            """,
            (
                guild_id,
                limit
            )
        ).fetchall()
        conn.close()
        return rows

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

    level_group = app_commands.Group(
        name="level",
        description="View and manage levelling."
    )

    @level_group.command(
        name="view",
        description="View a member's level."
    )
    @app_commands.describe(
        user="The member whose level you want to view."
    )
    async def level_view(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )
            return

        target = user or interaction.user
        data = self.get_user(
            interaction.guild.id,
            target.id
        )
        xp = data["xp"]
        level = data["level"]
        current_level_xp = self.xp_for_level(level)
        next_level_xp = self.xp_for_next_level(level)
        progress = xp - current_level_xp
        required = next_level_xp - current_level_xp
        percentage = (
            int((progress / required) * 100)
            if required > 0
            else 100
        )
        rank = self.get_rank(
            interaction.guild.id,
            target.id
        )

        embed = discord.Embed(
            title=f"📈 {target.display_name}'s Level",
            color=EMBED_COLOR
        )
        embed.set_thumbnail(
            url=target.display_avatar.url
        )
        embed.add_field(
            name="Level",
            value=f"**{level}**",
            inline=True
        )
        embed.add_field(
            name="Rank",
            value=f"**#{rank}**",
            inline=True
        )
        embed.add_field(
            name="Total XP",
            value=f"**{xp:,} XP**",
            inline=True
        )
        embed.add_field(
            name="Progress",
            value=(
                f"**{progress:,} / {required:,} XP** "
                f"({percentage}%)"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )

    @level_group.command(
        name="leaderboard",
        description="View the server levelling leaderboard."
    )
    async def level_leaderboard(
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

        rows = self.get_leaderboard(
            interaction.guild.id,
            10
        )

        if not rows:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Nobody has earned any XP yet."
                ),
                ephemeral=True
            )
            return

        description = []

        for position, row in enumerate(
            rows,
            start=1
        ):
            user_id, xp, level = row
            member = interaction.guild.get_member(user_id)

            if member:
                name = member.display_name
            else:
                name = f"<@{user_id}>"

            description.append(
                f"**{position}.** {name} "
                f"— Level **{level}** "
                f"({xp:,} XP)"
            )

        embed = discord.Embed(
            title="🏆 Levelling Leaderboard",
            description="\n".join(description),
            color=EMBED_COLOR
        )
        embed.set_footer(
            text=interaction.guild.name
        )

        await interaction.response.send_message(
            embed=embed
        )

    @level_group.command(
        name="settings",
        description="View the levelling settings."
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def level_settings(
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

        settings = self.get_settings(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="⚙️ Levelling Settings",
            color=EMBED_COLOR
        )
        embed.add_field(
            name="Status",
            value=(
                "Enabled"
                if settings["enabled"]
                else "Disabled"
            ),
            inline=True
        )
        embed.add_field(
            name="XP Per Message",
            value=(
                f"{settings['xp_min']}–"
                f"{settings['xp_max']} XP"
            ),
            inline=True
        )
        embed.add_field(
            name="Cooldown",
            value=f"{settings['cooldown']} seconds",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @level_group.command(
        name="enable",
        description="Enable levelling in this server."
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def level_enable(
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

        self.update_settings(
            interaction.guild.id,
            enabled=True
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                "Levelling has been enabled."
            ),
            ephemeral=True
        )

    @level_group.command(
        name="disable",
        description="Disable levelling in this server."
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def level_disable(
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

        self.update_settings(
            interaction.guild.id,
            enabled=False
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                "Levelling has been disabled."
            ),
            ephemeral=True
        )

    @level_group.command(
        name="xp",
        description="Configure XP gained from messages."
    )
    @app_commands.describe(
        minimum="Minimum XP awarded per message.",
        maximum="Maximum XP awarded per message."
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def level_xp(
        self,
        interaction: discord.Interaction,
        minimum: app_commands.Range[int, 1, 1000],
        maximum: app_commands.Range[int, 1, 1000]
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )
            return

        if minimum > maximum:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "The minimum XP cannot be greater than the maximum XP."
                ),
                ephemeral=True
            )
            return

        self.update_settings(
            interaction.guild.id,
            xp_min=minimum,
            xp_max=maximum
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"XP per message is now **{minimum}–{maximum} XP**."
            ),
            ephemeral=True
        )

    @level_group.command(
        name="cooldown",
        description="Configure the XP message cooldown."
    )
    @app_commands.describe(
        seconds="Cooldown in seconds between XP gains."
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def level_cooldown(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 3600]
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )
            return

        self.update_settings(
            interaction.guild.id,
            cooldown=seconds
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"XP cooldown is now **{seconds} seconds**."
            ),
            ephemeral=True
        )

    @level_group.command(
        name="add",
        description="Add XP to a member."
    )
    @app_commands.describe(
        user="The member to give XP to.",
        amount="The amount of XP to add."
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def level_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 1, 1000000]
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )
            return

        async with self.get_lock(interaction.guild.id):
            old_data = self.get_user(
                interaction.guild.id,
                user.id
            )
            old_level = old_data["level"]
            xp, new_level, levelled_up = self.add_xp(
                interaction.guild.id,
                user.id,
                amount
            )

        embed = discord.Embed(
            title="📈 XP Added",
            description=(
                f"Added **{amount:,} XP** to "
                f"{user.mention}."
            ),
            color=EMBED_COLOR
        )
        embed.add_field(
            name="Total XP",
            value=f"**{xp:,} XP**",
            inline=True
        )
        embed.add_field(
            name="Level",
            value=f"**{new_level}**",
            inline=True
        )

        if new_level > old_level:
            embed.add_field(
                name="Level Up",
                value=(
                    f"🎉 {user.mention} reached "
                    f"**Level {new_level}**!"
                ),
                inline=False
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @level_group.command(
        name="remove",
        description="Remove XP from a member."
    )
    @app_commands.describe(
        user="The member to remove XP from.",
        amount="The amount of XP to remove."
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def level_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 1, 1000000]
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )
            return

        async with self.get_lock(interaction.guild.id):
            data = self.get_user(
                interaction.guild.id,
                user.id
            )
            old_xp = data["xp"]
            new_xp = max(
                0,
                old_xp - amount
            )
            new_level = self.calculate_level(new_xp)

            self.set_user_xp(
                interaction.guild.id,
                user.id,
                new_xp
            )

        actual_removed = old_xp - new_xp

        embed = discord.Embed(
            title="📉 XP Removed",
            description=(
                f"Removed **{actual_removed:,} XP** from "
                f"{user.mention}."
            ),
            color=EMBED_COLOR
        )
        embed.add_field(
            name="Total XP",
            value=f"**{new_xp:,} XP**",
            inline=True
        )
        embed.add_field(
            name="Level",
            value=f"**{new_level}**",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):
        if not message.guild:
            return
        if message.author.bot:
            return
        if not message.content.strip():
            return

        settings = self.get_settings(
            message.guild.id
        )

        if not settings["enabled"]:
            return

        user_key = (
            message.guild.id,
            message.author.id
        )
        now = time.time()
        last_xp = self.cooldowns.get(
            user_key,
            0
        )

        if now - last_xp < settings["cooldown"]:
            return

        self.cooldowns[user_key] = now

        amount = random.randint(
            settings["xp_min"],
            settings["xp_max"]
        )

        async with self.get_lock(message.guild.id):
            xp, level, levelled_up = self.add_xp(
                message.guild.id,
                message.author.id,
                amount
            )

        if not levelled_up:
            return

        embed = discord.Embed(
            title="🎉 Level Up!",
            description=(
                f"{message.author.mention} reached "
                f"**Level {level}**!"
            ),
            color=EMBED_COLOR
        )
        embed.add_field(
            name="XP",
            value=f"{xp:,} XP",
            inline=True
        )
        embed.add_field(
            name="Level",
            value=f"**{level}**",
            inline=True
        )

        try:
            await message.channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    users=True
                )
            )
        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            pass

    @level_view.error
    @level_leaderboard.error
    @level_settings.error
    @level_enable.error
    @level_disable.error
    @level_xp.error
    @level_cooldown.error
    @level_add.error
    @level_remove.error
    async def level_error(
        self,
        interaction: discord.Interaction,
        error
    ):
        if isinstance(
            error,
            app_commands.MissingPermissions
        ):
            embed = self.error_embed(
                "You need the **Manage Server** permission to use this command."
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
    await bot.add_cog(
        Levelling(bot)
    )