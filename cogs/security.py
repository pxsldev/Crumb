import discord
from discord import app_commands
from discord.ext import commands, tasks

import sqlite3
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("db/security.db")
BACKUP_DIR = Path("backups")

DEFAULT_RAID_THRESHOLD = 10
DEFAULT_RAID_WINDOW = 30
DEFAULT_RAID_COOLDOWN = 600

DEFAULT_NUKE_THRESHOLD = 5
DEFAULT_NUKE_WINDOW = 10

DEFAULT_BACKUP_RETENTION = 24

class RestoreConfirmView(discord.ui.View):
    def __init__(self, cog, interaction_user_id, backup_path):
        super().__init__(timeout=60)

        self.cog = cog
        self.interaction_user_id = interaction_user_id
        self.backup_path = backup_path
        self.result = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction_user_id:
            await interaction.response.send_message(
                embed=self.cog.error_embed(
                    "Not Your Confirmation",
                    "Only the person who started the restore can confirm it."
                ),
                ephemeral=True
            )
            return False

        return True

    @discord.ui.button(
        label="Confirm Restore",
        style=discord.ButtonStyle.danger,
        emoji="⚠️"
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        self.result = True

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(view=self)

        self.stop()

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        self.result = False

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            embed=self.cog.success_embed(
                "Restore Cancelled",
                "The server restore was cancelled."
            ),
            view=self
        )

        self.stop()

class Security(commands.GroupCog, group_name="security"):

    backup_group = app_commands.Group(
        name="backup",
        description="Server backup management"
    )

    def __init__(self, bot):
        self.bot = bot

        Path("db").mkdir(exist_ok=True)
        BACKUP_DIR.mkdir(exist_ok=True)

        self.init_db()

        self.join_tracker = {}
        self.nuke_tracker = {}
        self.raid_cooldowns = {}

        self.backup_lock = asyncio.Lock()

        self.cleanup_tracker.start()
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.cleanup_tracker.cancel()
        self.auto_backup_loop.cancel()

    def init_db(self):
        with sqlite3.connect(DB_PATH) as db:

            db.execute("""
                CREATE TABLE IF NOT EXISTS security (
                    guild_id INTEGER PRIMARY KEY,

                    antiraid_enabled INTEGER NOT NULL DEFAULT 0,
                    raid_threshold INTEGER NOT NULL DEFAULT 10,
                    raid_window INTEGER NOT NULL DEFAULT 30,
                    raid_cooldown INTEGER NOT NULL DEFAULT 600,

                    antinuke_enabled INTEGER NOT NULL DEFAULT 0,
                    nuke_threshold INTEGER NOT NULL DEFAULT 5,
                    nuke_window INTEGER NOT NULL DEFAULT 10,

                    lockdown_enabled INTEGER NOT NULL DEFAULT 0,

                    log_channel_id INTEGER,

                    autobackup_enabled INTEGER NOT NULL DEFAULT 0,
                    backup_interval INTEGER NOT NULL DEFAULT 900,
                    backup_retention INTEGER NOT NULL DEFAULT 24
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS whitelist (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            db.commit()

        self.ensure_columns()

    def ensure_columns(self):
        required_columns = {
            "autobackup_enabled": "INTEGER NOT NULL DEFAULT 0",
            "backup_interval": "INTEGER NOT NULL DEFAULT 900",
            "backup_retention": "INTEGER NOT NULL DEFAULT 24"
        }

        with sqlite3.connect(DB_PATH) as db:

            existing = {
                row[1]
                for row in db.execute(
                    "PRAGMA table_info(security)"
                ).fetchall()
            }

            for column, definition in required_columns.items():

                if column not in existing:
                    db.execute(
                        f"ALTER TABLE security ADD COLUMN {column} {definition}"
                    )

            db.commit()

    def create_config(self, guild_id):
        with sqlite3.connect(DB_PATH) as db:
            db.execute("""
                INSERT OR IGNORE INTO security (guild_id)
                VALUES (?)
            """, (guild_id,))
            db.commit()

    def get_config(self, guild_id):
        self.create_config(guild_id)

        with sqlite3.connect(DB_PATH) as db:
            row = db.execute("""
                SELECT
                    antiraid_enabled,
                    raid_threshold,
                    raid_window,
                    raid_cooldown,

                    antinuke_enabled,
                    nuke_threshold,
                    nuke_window,

                    lockdown_enabled,
                    log_channel_id,

                    autobackup_enabled,
                    backup_interval,
                    backup_retention

                FROM security
                WHERE guild_id = ?
            """, (guild_id,)).fetchone()

        return {
            "antiraid_enabled": bool(row[0]),
            "raid_threshold": row[1],
            "raid_window": row[2],
            "raid_cooldown": row[3],

            "antinuke_enabled": bool(row[4]),
            "nuke_threshold": row[5],
            "nuke_window": row[6],

            "lockdown_enabled": bool(row[7]),
            "log_channel_id": row[8],

            "autobackup_enabled": bool(row[9]),
            "backup_interval": row[10],
            "backup_retention": row[11]
        }

    def update_config(self, guild_id, field, value):
        allowed = {
            "antiraid_enabled",
            "raid_threshold",
            "raid_window",
            "raid_cooldown",

            "antinuke_enabled",
            "nuke_threshold",
            "nuke_window",

            "lockdown_enabled",
            "log_channel_id",

            "autobackup_enabled",
            "backup_interval",
            "backup_retention"
        }

        if field not in allowed:
            return

        self.create_config(guild_id)

        with sqlite3.connect(DB_PATH) as db:
            db.execute(
                f"""
                UPDATE security
                SET {field} = ?
                WHERE guild_id = ?
                """,
                (value, guild_id)
            )
            db.commit()

    def success_embed(self, title, description):
        return discord.Embed(
            title=title,
            description=description,
            colour=discord.Colour.orange()
        )

    def error_embed(self, title, description):
        return discord.Embed(
            title=title,
            description=description,
            colour=discord.Colour.red()
        )

    async def require_manage_guild(self, interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Server Only",
                    "This command can only be used inside a server."
                ),
                ephemeral=True
            )
            return False

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Missing Permissions",
                    "You need **Manage Server** to use this command."
                ),
                ephemeral=True
            )
            return False

        return True

    async def security_log(
        self,
        guild,
        title,
        description,
        colour=None
    ):
        config = self.get_config(guild.id)

        channel_id = config["log_channel_id"]

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)

        if channel is None:
            return

        if colour is None:
            colour = discord.Colour.orange()

        try:
            embed = discord.Embed(
                title=title,
                description=description,
                colour=colour,
                timestamp=datetime.now(timezone.utc)
            )

            await channel.send(embed=embed)

        except (discord.Forbidden, discord.HTTPException):
            pass

    def is_whitelisted(self, guild_id, user_id):
        with sqlite3.connect(DB_PATH) as db:
            row = db.execute("""
                SELECT 1
                FROM whitelist
                WHERE guild_id = ?
                AND user_id = ?
            """, (guild_id, user_id)).fetchone()

        return row is not None

    @app_commands.command(
        name="whitelist",
        description="Add or remove a user from the security whitelist."
    )
    @app_commands.describe(
        user="The user to whitelist",
        action="Whether to add or remove them"
    )
    @app_commands.choices(action=[
        app_commands.Choice(
            name="Add",
            value="add"
        ),
        app_commands.Choice(
            name="Remove",
            value="remove"
        )
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def whitelist(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        action: app_commands.Choice[str]
    ):
        try:
            if action.value == "add":

                with sqlite3.connect(DB_PATH) as db:
                    db.execute("""
                        INSERT OR IGNORE INTO whitelist
                        (guild_id, user_id)
                        VALUES (?, ?)
                    """, (
                        interaction.guild.id,
                        user.id
                    ))
                    db.commit()

                await interaction.response.send_message(
                    embed=self.success_embed(
                        "User Whitelisted",
                        f"{user.mention} is now whitelisted from Anti-Nuke."
                    ),
                    ephemeral=True
                )

            else:

                with sqlite3.connect(DB_PATH) as db:
                    db.execute("""
                        DELETE FROM whitelist
                        WHERE guild_id = ?
                        AND user_id = ?
                    """, (
                        interaction.guild.id,
                        user.id
                    ))
                    db.commit()

                await interaction.response.send_message(
                    embed=self.success_embed(
                        "User Removed",
                        f"{user.mention} has been removed from the security whitelist."
                    ),
                    ephemeral=True
                )

        except Exception as e:
            print(f"[SECURITY] Whitelist error: {e}")

            await interaction.response.send_message(
                embed=self.error_embed(
                    "Error",
                    "Something went wrong while updating the whitelist."
                ),
                ephemeral=True
            )

    @app_commands.command(
        name="antiraid",
        description="Enable or disable Anti-Raid."
    )
    @app_commands.describe(
        action="Enable or disable Anti-Raid"
    )
    @app_commands.choices(action=[
        app_commands.Choice(
            name="Enable",
            value="enable"
        ),
        app_commands.Choice(
            name="Disable",
            value="disable"
        )
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def antiraid(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str]
    ):
        try:
            enabled = action.value == "enable"

            self.update_config(
                interaction.guild.id,
                "antiraid_enabled",
                int(enabled)
            )

            status = "enabled" if enabled else "disabled"

            await interaction.response.send_message(
                embed=self.success_embed(
                    "Anti-Raid Updated",
                    f"Anti-Raid has been **{status}**."
                ),
                ephemeral=True
            )

        except Exception as e:
            print(f"[SECURITY] Anti-Raid error: {e}")

            await interaction.response.send_message(
                embed=self.error_embed(
                    "Error",
                    "Failed to update Anti-Raid."
                ),
                ephemeral=True
            )

    @app_commands.command(
        name="antinuke",
        description="Enable or disable Anti-Nuke."
    )
    @app_commands.describe(
        action="Enable or disable Anti-Nuke"
    )
    @app_commands.choices(action=[
        app_commands.Choice(
            name="Enable",
            value="enable"
        ),
        app_commands.Choice(
            name="Disable",
            value="disable"
        )
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def antinuke(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str]
    ):
        try:
            enabled = action.value == "enable"

            self.update_config(
                interaction.guild.id,
                "antinuke_enabled",
                int(enabled)
            )

            status = "enabled" if enabled else "disabled"

            await interaction.response.send_message(
                embed=self.success_embed(
                    "Anti-Nuke Updated",
                    f"Anti-Nuke has been **{status}**."
                ),
                ephemeral=True
            )

        except Exception as e:
            print(f"[SECURITY] Anti-Nuke error: {e}")

            await interaction.response.send_message(
                embed=self.error_embed(
                    "Error",
                    "Failed to update Anti-Nuke."
                ),
                ephemeral=True
            )

    @app_commands.command(
        name="lockdown",
        description="Lock or unlock the server."
    )
    @app_commands.describe(
        action="Lock or unlock the server"
    )
    @app_commands.choices(action=[
        app_commands.Choice(
            name="Lock",
            value="lock"
        ),
        app_commands.Choice(
            name="Unlock",
            value="unlock"
        )
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def lockdown(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str]
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            guild = interaction.guild
            lock = action.value == "lock"

            changed = 0
            failed = 0

            for channel in guild.text_channels:

                try:
                    overwrite = channel.overwrites_for(
                        guild.default_role
                    )

                    overwrite.send_messages = not lock

                    await channel.set_permissions(
                        guild.default_role,
                        overwrite=overwrite,
                        reason=(
                            f"Crumb security "
                            f"{'lockdown' if lock else 'unlock'}"
                        )
                    )

                    changed += 1

                except (discord.Forbidden, discord.HTTPException):
                    failed += 1

            self.update_config(
                guild.id,
                "lockdown_enabled",
                int(lock)
            )

            status = "locked down" if lock else "unlocked"

            await interaction.followup.send(
                embed=self.success_embed(
                    "Server Lockdown",
                    f"The server has been **{status}**.\n\n"
                    f"Channels updated: **{changed}**\n"
                    f"Failed: **{failed}**"
                ),
                ephemeral=True
            )

            await self.security_log(
                guild,
                "🔒 Server Lockdown",
                f"{interaction.user.mention} "
                f"**{'enabled' if lock else 'disabled'}** server lockdown."
            )

        except Exception as e:
            print(f"[SECURITY] Lockdown error: {e}")

            await interaction.followup.send(
                embed=self.error_embed(
                    "Error",
                    "Failed to update server lockdown."
                ),
                ephemeral=True
            )

    @app_commands.command(
        name="config",
        description="View the server security configuration."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction):
        try:
            guild = interaction.guild
            config = self.get_config(guild.id)

            log_channel = (
                guild.get_channel(config["log_channel_id"])
                if config["log_channel_id"]
                else None
            )

            embed = discord.Embed(
                title="🛡️ Security Configuration",
                colour=discord.Colour.orange()
            )

            embed.add_field(
                name="Anti-Raid",
                value=(
                    f"Enabled: "
                    f"**{'Yes' if config['antiraid_enabled'] else 'No'}**\n"
                    f"Threshold: **{config['raid_threshold']} joins**\n"
                    f"Window: **{config['raid_window']} seconds**\n"
                    f"Cooldown: **{config['raid_cooldown']} seconds**"
                ),
                inline=False
            )

            embed.add_field(
                name="Anti-Nuke",
                value=(
                    f"Enabled: "
                    f"**{'Yes' if config['antinuke_enabled'] else 'No'}**\n"
                    f"Threshold: **{config['nuke_threshold']} actions**\n"
                    f"Window: **{config['nuke_window']} seconds**"
                ),
                inline=False
            )

            embed.add_field(
                name="Auto Backup",
                value=(
                    f"Enabled: "
                    f"**{'Yes' if config['autobackup_enabled'] else 'No'}**\n"
                    f"Interval: **{config['backup_interval'] // 60} minutes**\n"
                    f"Retention: **{config['backup_retention']} backups**"
                ),
                inline=False
            )

            embed.add_field(
                name="Lockdown",
                value=(
                    "Enabled"
                    if config["lockdown_enabled"]
                    else "Disabled"
                ),
                inline=True
            )

            embed.add_field(
                name="Security Logs",
                value=(
                    log_channel.mention
                    if log_channel
                    else "Not configured"
                ),
                inline=True
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

        except Exception as e:
            print(f"[SECURITY] Config error: {e}")

            await interaction.response.send_message(
                embed=self.error_embed(
                    "Error",
                    "Failed to load security configuration."
                ),
                ephemeral=True
            )

    @app_commands.command(
        name="backup",
        description="Manage server backups."
    )
    @app_commands.describe(
        action="The backup action"
    )
    @app_commands.choices(action=[
        app_commands.Choice(
            name="Create",
            value="create"
        ),
        app_commands.Choice(
            name="List",
            value="list"
        ),
        app_commands.Choice(
            name="Info",
            value="info"
        ),
        app_commands.Choice(
            name="Delete",
            value="delete"
        ),
        app_commands.Choice(
            name="Restore",
            value="restore"
        ),
        app_commands.Choice(
            name="Auto",
            value="auto"
        )
    ])
    @app_commands.describe(
        backup_id="Backup ID for info/delete/restore"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def backup(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        backup_id: str | None = None
    ):
        try:

            if action.value == "create":

                await interaction.response.defer(
                    ephemeral=True
                )

                path = await self.create_backup(
                    interaction.guild,
                    automatic=False
                )

                if path is None:
                    await interaction.followup.send(
                        embed=self.error_embed(
                            "Backup Failed",
                            "I couldn't create the server backup."
                        ),
                        ephemeral=True
                    )
                    return

                backup_id_value = path.stem.replace(
                    "backup_",
                    "",
                    1
                )

                await interaction.followup.send(
                    embed=self.success_embed(
                        "Backup Created",
                        f"Server backup created successfully.\n\n"
                        f"**Backup ID:** `{backup_id_value}`\n"
                        f"**File:** `{path.name}`"
                    ),
                    ephemeral=True
                )

                return

            if action.value == "list":

                backups = self.get_backups(
                    interaction.guild.id
                )

                if not backups:
                    await interaction.response.send_message(
                        embed=self.success_embed(
                            "Server Backups",
                            "There are no backups for this server."
                        ),
                        ephemeral=True
                    )
                    return

                lines = []

                for path in backups[:25]:
                    backup_id_value = path.stem.replace(
                        "backup_",
                        "",
                        1
                    )

                    size = path.stat().st_size

                    lines.append(
                        f"`{backup_id_value}` — "
                        f"{size / 1024:.1f} KB"
                    )

                embed = discord.Embed(
                    title="💾 Server Backups",
                    description="\n".join(lines),
                    colour=discord.Colour.orange()
                )

                embed.set_footer(
                    text=f"{len(backups)} backup(s) stored"
                )

                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True
                )

                return

            if action.value == "info":

                if not backup_id:
                    await interaction.response.send_message(
                        embed=self.error_embed(
                            "Missing Backup ID",
                            "Provide a backup ID to inspect."
                        ),
                        ephemeral=True
                    )
                    return

                path = self.get_backup_path(
                    interaction.guild.id,
                    backup_id
                )

                if path is None:
                    await interaction.response.send_message(
                        embed=self.error_embed(
                            "Backup Not Found",
                            "That backup does not exist."
                        ),
                        ephemeral=True
                    )
                    return

                with open(
                    path,
                    "r",
                    encoding="utf-8"
                ) as file:
                    data = json.load(file)

                embed = discord.Embed(
                    title="💾 Backup Information",
                    colour=discord.Colour.orange()
                )

                guild_data = data.get("guild", {})

                embed.add_field(
                    name="Server",
                    value=(
                        f"{guild_data.get('name', 'Unknown')}\n"
                        f"ID: `{guild_data.get('id', 'Unknown')}`"
                    ),
                    inline=False
                )

                embed.add_field(
                    name="Contents",
                    value=(
                        f"Roles: **{len(data.get('roles', []))}**\n"
                        f"Categories: **{len(data.get('categories', []))}**\n"
                        f"Channels: **{len(data.get('channels', []))}**"
                    ),
                    inline=False
                )

                embed.add_field(
                    name="Backup",
                    value=f"`{backup_id}`",
                    inline=False
                )

                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True
                )

                return

            if action.value == "delete":

                if not backup_id:
                    await interaction.response.send_message(
                        embed=self.error_embed(
                            "Missing Backup ID",
                            "Provide a backup ID to delete."
                        ),
                        ephemeral=True
                    )
                    return

                path = self.get_backup_path(
                    interaction.guild.id,
                    backup_id
                )

                if path is None:
                    await interaction.response.send_message(
                        embed=self.error_embed(
                            "Backup Not Found",
                            "That backup does not exist."
                        ),
                        ephemeral=True
                    )
                    return

                path.unlink()

                await interaction.response.send_message(
                    embed=self.success_embed(
                        "Backup Deleted",
                        f"Backup `{backup_id}` has been deleted."
                    ),
                    ephemeral=True
                )

                return

            if action.value == "restore":

                if not backup_id:
                    await interaction.response.send_message(
                        embed=self.error_embed(
                            "Missing Backup ID",
                            "Provide a backup ID to restore."
                        ),
                        ephemeral=True
                    )
                    return

                path = self.get_backup_path(
                    interaction.guild.id,
                    backup_id
                )

                if path is None:
                    await interaction.response.send_message(
                        embed=self.error_embed(
                            "Backup Not Found",
                            "That backup does not exist."
                        ),
                        ephemeral=True
                    )
                    return

                with open(
                    path,
                    "r",
                    encoding="utf-8"
                ) as file:
                    data = json.load(file)

                view = RestoreConfirmView(
                    self,
                    interaction.user.id,
                    path
                )

                embed = discord.Embed(
                    title="⚠️ Confirm Server Restore",
                    description=(
                        "You are about to restore this server from:\n\n"
                        f"`{backup_id}`\n\n"
                        "This will **modify the server**.\n\n"
                        "The restore will attempt to:\n"
                        "• Restore roles\n"
                        "• Restore role permissions\n"
                        "• Restore categories\n"
                        "• Restore channels\n"
                        "• Restore channel settings\n"
                        "• Restore channel positions\n"
                        "• Restore permission overwrites\n\n"
                        "**Existing server content will not be "
                        "blindly deleted.**"
                    ),
                    colour=discord.Colour.red()
                )

                await interaction.response.send_message(
                    embed=embed,
                    view=view,
                    ephemeral=True
                )

                await view.wait()

                if view.result is True:

                    await interaction.edit_original_response(
                        embed=self.success_embed(
                            "Restore Started",
                            "The server restore is now running..."
                        ),
                        view=None
                    )

                    try:
                        result = await self.restore_backup(
                            interaction.guild,
                            data
                        )

                        await interaction.edit_original_response(
                            embed=self.success_embed(
                                "Restore Complete",
                                result
                            )
                        )

                        await self.security_log(
                            interaction.guild,
                            "💾 Server Restored",
                            f"{interaction.user.mention} restored "
                            f"backup `{backup_id}`."
                        )

                    except Exception as e:
                        print(
                            f"[SECURITY] Restore error: {e}"
                        )

                        await interaction.edit_original_response(
                            embed=self.error_embed(
                                "Restore Failed",
                                "The restore encountered an error. "
                                "Check the bot console for details."
                            )
                        )

                return

            if action.value == "auto":

                config = self.get_config(
                    interaction.guild.id
                )

                enabled = not config["autobackup_enabled"]

                self.update_config(
                    interaction.guild.id,
                    "autobackup_enabled",
                    int(enabled)
                )

                if enabled:

                    await interaction.response.send_message(
                        embed=self.success_embed(
                            "Automatic Backups Enabled",
                            "Automatic server backups are now enabled.\n\n"
                            "**Interval:** 15 minutes\n"
                            f"**Retention:** "
                            f"{config['backup_retention']} backups"
                        ),
                        ephemeral=True
                    )

                else:

                    await interaction.response.send_message(
                        embed=self.success_embed(
                            "Automatic Backups Disabled",
                            "Automatic server backups have been disabled."
                        ),
                        ephemeral=True
                    )

                return

        except Exception as e:
            print(f"[SECURITY] Backup command error: {e}")

            if interaction.response.is_done():

                await interaction.followup.send(
                    embed=self.error_embed(
                        "Error",
                        "Something went wrong while handling the backup."
                    ),
                    ephemeral=True
                )

            else:

                await interaction.response.send_message(
                    embed=self.error_embed(
                        "Error",
                        "Something went wrong while handling the backup."
                    ),
                    ephemeral=True
                )

    async def create_backup(
        self,
        guild,
        automatic=False
    ):
        async with self.backup_lock:
            try:

                backup = {
                    "version": 2,
                    "created_at": datetime.now(
                        timezone.utc
                    ).isoformat(),

                    "guild": {
                        "id": guild.id,
                        "name": guild.name,
                        "description": guild.description
                    },

                    "roles": [],
                    "categories": [],
                    "channels": []
                }

                for role in guild.roles:

                    if role.is_default():
                        continue

                    backup["roles"].append({
                        "id": role.id,
                        "name": role.name,
                        "colour": role.colour.value,
                        "hoist": role.hoist,
                        "mentionable": role.mentionable,
                        "permissions": role.permissions.value,
                        "position": role.position
                    })

                for category in guild.categories:

                    backup["categories"].append({
                        "id": category.id,
                        "name": category.name,
                        "position": category.position,
                        "overwrites": self.serialize_overwrites(
                            category
                        )
                    })

                for channel in guild.channels:

                    if isinstance(
                        channel,
                        discord.CategoryChannel
                    ):
                        continue

                    data = {
                        "id": channel.id,
                        "name": channel.name,
                        "type": str(channel.type),
                        "position": channel.position,
                        "category_id": (
                            channel.category.id
                            if channel.category
                            else None
                        ),
                        "overwrites": self.serialize_overwrites(
                            channel
                        )
                    }

                    if isinstance(
                        channel,
                        discord.TextChannel
                    ):
                        data.update({
                            "topic": channel.topic,
                            "slowmode_delay": channel.slowmode_delay,
                            "nsfw": channel.nsfw
                        })

                    elif isinstance(
                        channel,
                        discord.VoiceChannel
                    ):
                        data.update({
                            "bitrate": channel.bitrate,
                            "user_limit": channel.user_limit
                        })

                    elif isinstance(
                        channel,
                        discord.StageChannel
                    ):
                        data.update({
                            "bitrate": channel.bitrate,
                            "user_limit": channel.user_limit
                        })

                    elif isinstance(
                        channel,
                        discord.ForumChannel
                    ):
                        data.update({
                            "topic": channel.topic,
                            "nsfw": channel.nsfw,
                            "slowmode_delay": channel.slowmode_delay
                        })

                    backup["channels"].append(data)

                guild_dir = (
                    BACKUP_DIR /
                    str(guild.id)
                )

                guild_dir.mkdir(
                    parents=True,
                    exist_ok=True
                )

                timestamp = datetime.now().strftime(
                    "%Y-%m-%d_%H-%M-%S"
                )

                path = guild_dir / (
                    f"backup_{timestamp}.json"
                )

                with open(
                    path,
                    "w",
                    encoding="utf-8"
                ) as file:

                    json.dump(
                        backup,
                        file,
                        indent=4,
                        ensure_ascii=False
                    )

                if automatic:

                    config = self.get_config(
                        guild.id
                    )

                    self.enforce_backup_retention(
                        guild.id,
                        config["backup_retention"]
                    )

                return path

            except Exception as e:
                print(
                    f"[SECURITY] create_backup error: {e}"
                )
                return None

    def serialize_overwrites(self, channel):

        result = []

        for target, overwrite in channel.overwrites.items():

            if isinstance(
                target,
                discord.Role
            ):
                target_type = "role"

            elif isinstance(
                target,
                discord.Member
            ):
                target_type = "member"

            else:
                continue

            allow, deny = overwrite.pair()

            result.append({
                "id": target.id,
                "type": target_type,
                "allow": allow.value,
                "deny": deny.value
            })

        return result

    def get_backups(self, guild_id):

        guild_dir = (
            BACKUP_DIR /
            str(guild_id)
        )

        if not guild_dir.exists():
            return []

        return sorted(
            [
                path
                for path in guild_dir.glob(
                    "backup_*.json"
                )
                if path.is_file()
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

    def get_backup_path(
        self,
        guild_id,
        backup_id
    ):

        if "/" in backup_id or "\\" in backup_id:
            return None

        path = (
            BACKUP_DIR /
            str(guild_id) /
            f"backup_{backup_id}.json"
        )

        if not path.is_file():
            return None

        return path

    def enforce_backup_retention(
        self,
        guild_id,
        retention
    ):

        backups = self.get_backups(
            guild_id
        )

        if retention < 1:
            retention = 1

        for old_backup in backups[retention:]:

            try:
                old_backup.unlink()

            except OSError:
                pass

    async def restore_backup(
        self,
        guild,
        backup
    ):

        role_mapping = {}
        category_mapping = {}
        channel_mapping = {}

        created_roles = 0
        updated_roles = 0

        created_categories = 0
        updated_categories = 0

        created_channels = 0
        updated_channels = 0

        failed = 0

        existing_roles = {
            role.name.lower(): role
            for role in guild.roles
        }

        roles = sorted(
            backup.get("roles", []),
            key=lambda role: role.get(
                "position",
                0
            )
        )

        for role_data in roles:

            name = role_data.get(
                "name",
                "Restored Role"
            )

            existing = existing_roles.get(
                name.lower()
            )

            if existing:

                role_mapping[
                    role_data["id"]
                ] = existing

                try:

                    await existing.edit(
                        name=name,
                        colour=discord.Colour(
                            role_data.get(
                                "colour",
                                0
                            )
                        ),
                        hoist=role_data.get(
                            "hoist",
                            False
                        ),
                        mentionable=role_data.get(
                            "mentionable",
                            False
                        ),
                        permissions=discord.Permissions(
                            role_data.get(
                                "permissions",
                                0
                            )
                        ),
                        reason="Crumb server restore"
                    )

                    updated_roles += 1

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    failed += 1

            else:

                try:

                    new_role = await guild.create_role(
                        name=name,
                        colour=discord.Colour(
                            role_data.get(
                                "colour",
                                0
                            )
                        ),
                        hoist=role_data.get(
                            "hoist",
                            False
                        ),
                        mentionable=role_data.get(
                            "mentionable",
                            False
                        ),
                        permissions=discord.Permissions(
                            role_data.get(
                                "permissions",
                                0
                            )
                        ),
                        reason="Crumb server restore"
                    )

                    role_mapping[
                        role_data["id"]
                    ] = new_role

                    created_roles += 1

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    failed += 1

        existing_categories = {
            category.name.lower(): category
            for category in guild.categories
        }

        for category_data in backup.get(
            "categories",
            []
        ):

            name = category_data.get(
                "name",
                "Restored Category"
            )

            existing = existing_categories.get(
                name.lower()
            )

            if existing:

                category_mapping[
                    category_data["id"]
                ] = existing

                try:

                    await existing.edit(
                        name=name,
                        reason="Crumb server restore"
                    )

                    updated_categories += 1

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    failed += 1

            else:

                try:

                    new_category = (
                        await guild.create_category(
                            name=name,
                            reason="Crumb server restore"
                        )
                    )

                    category_mapping[
                        category_data["id"]
                    ] = new_category

                    created_categories += 1

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    failed += 1

        existing_channels = {
            (
                channel.name.lower(),
                str(channel.type)
            ): channel
            for channel in guild.channels
            if not isinstance(
                channel,
                discord.CategoryChannel
            )
        }

        for channel_data in backup.get(
            "channels",
            []
        ):

            name = channel_data.get(
                "name",
                "restored-channel"
            )

            channel_type = channel_data.get(
                "type",
                "text"
            )

            key = (
                name.lower(),
                channel_type
            )

            existing = existing_channels.get(
                key
            )

            category = None

            old_category_id = channel_data.get(
                "category_id"
            )

            if old_category_id:
                category = category_mapping.get(
                    old_category_id
                )

            try:

                if existing:

                    channel_mapping[
                        channel_data["id"]
                    ] = existing

                    await self.update_channel(
                        existing,
                        channel_data,
                        category
                    )

                    updated_channels += 1

                else:

                    new_channel = (
                        await self.create_channel(
                            guild,
                            channel_data,
                            category
                        )
                    )

                    if new_channel:

                        channel_mapping[
                            channel_data["id"]
                        ] = new_channel

                        created_channels += 1

                    else:
                        failed += 1

            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                failed += 1

        for category_data in backup.get(
            "categories",
            []
        ):

            category = category_mapping.get(
                category_data["id"]
            )

            if category is None:
                continue

            await self.restore_overwrites(
                category,
                category_data.get(
                    "overwrites",
                    []
                ),
                role_mapping
            )

        for channel_data in backup.get(
            "channels",
            []
        ):

            channel = channel_mapping.get(
                channel_data["id"]
            )

            if channel is None:
                continue

            await self.restore_overwrites(
                channel,
                channel_data.get(
                    "overwrites",
                    []
                ),
                role_mapping
            )

        await self.restore_positions(
            guild,
            backup,
            role_mapping,
            category_mapping,
            channel_mapping
        )

        return (
            f"Restore finished.\n\n"
            f"**Roles**\n"
            f"Created: **{created_roles}**\n"
            f"Updated: **{updated_roles}**\n\n"
            f"**Categories**\n"
            f"Created: **{created_categories}**\n"
            f"Updated: **{updated_categories}**\n\n"
            f"**Channels**\n"
            f"Created: **{created_channels}**\n"
            f"Updated: **{updated_channels}**\n\n"
            f"Failed operations: **{failed}**"
        )

    async def create_channel(
        self,
        guild,
        data,
        category
    ):

        name = data.get(
            "name",
            "restored-channel"
        )

        channel_type = data.get(
            "type",
            "text"
        )

        reason = "Crumb server restore"

        if channel_type == "text":

            return await guild.create_text_channel(
                name,
                category=category,
                topic=data.get("topic"),
                slowmode_delay=data.get(
                    "slowmode_delay",
                    0
                ),
                nsfw=data.get(
                    "nsfw",
                    False
                ),
                reason=reason
            )

        if channel_type == "voice":

            return await guild.create_voice_channel(
                name,
                category=category,
                bitrate=data.get(
                    "bitrate"
                ),
                user_limit=data.get(
                    "user_limit",
                    0
                ),
                reason=reason
            )

        if channel_type == "stage_voice":

            return await guild.create_stage_channel(
                name,
                category=category,
                reason=reason
            )

        if channel_type == "forum":

            return await guild.create_forum(
                name,
                category=category,
                topic=data.get("topic"),
                slowmode_delay=data.get(
                    "slowmode_delay",
                    0
                ),
                nsfw=data.get(
                    "nsfw",
                    False
                ),
                reason=reason
            )

        return None

    async def update_channel(
        self,
        channel,
        data,
        category
    ):

        kwargs = {
            "name": data.get(
                "name",
                channel.name
            ),
            "category": category,
            "reason": "Crumb server restore"
        }

        if isinstance(
            channel,
            discord.TextChannel
        ):

            kwargs.update({
                "topic": data.get(
                    "topic"
                ),
                "slowmode_delay": data.get(
                    "slowmode_delay",
                    0
                ),
                "nsfw": data.get(
                    "nsfw",
                    False
                )
            })

        elif isinstance(
            channel,
            discord.VoiceChannel
        ):

            kwargs.update({
                "bitrate": data.get(
                    "bitrate",
                    channel.bitrate
                ),
                "user_limit": data.get(
                    "user_limit",
                    channel.user_limit
                )
            })

        await channel.edit(**kwargs)

    async def restore_overwrites(
        self,
        channel,
        overwrites,
        role_mapping
    ):

        for overwrite_data in overwrites:

            target_id = overwrite_data.get(
                "id"
            )

            target_type = overwrite_data.get(
                "type"
            )

            target = None

            if target_type == "role":

                target = role_mapping.get(
                    target_id
                )

                if target is None:

                    if target_id == channel.guild.id:
                        target = channel.guild.default_role

                    else:
                        target = discord.utils.get(
                            channel.guild.roles,
                            id=target_id
                        )

            elif target_type == "member":

                target = channel.guild.get_member(
                    target_id
                )

            if target is None:
                continue

            try:

                allow = discord.Permissions(
                    overwrite_data.get(
                        "allow",
                        0
                    )
                )

                deny = discord.Permissions(
                    overwrite_data.get(
                        "deny",
                        0
                    )
                )

                overwrite = discord.PermissionOverwrite.from_pair(
                    allow,
                    deny
                )

                await channel.set_permissions(
                    target,
                    overwrite=overwrite,
                    reason="Crumb server restore"
                )

            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

    async def restore_positions(
        self,
        guild,
        backup,
        role_mapping,
        category_mapping,
        channel_mapping
    ):
        categories = []

        for data in backup.get("categories", []):
            category = category_mapping.get(data["id"])

            if category is None:
                continue

            categories.append((
                category,
                data.get("position", 0)
            ))

        for category, position in sorted(
            categories,
            key=lambda x: x[1]
        ):
            try:
                await category.edit(
                    position=position,
                    reason="Crumb server restore"
                )
            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

        channels = []

        for data in backup.get("channels", []):
            channel = channel_mapping.get(data["id"])

            if channel is None:
                continue

            channels.append((
                channel,
                data.get("position", 0)
            ))

        for channel, position in sorted(
            channels,
            key=lambda x: x[1]
        ):
            try:
                await channel.edit(
                    position=position,
                    reason="Crumb server restore"
                )
            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

        roles = []

        for data in backup.get("roles", []):
            role = role_mapping.get(data["id"])

            if role is None:
                continue

            if guild.me and role >= guild.me.top_role:
                continue

            roles.append((
                role,
                data.get("position", 1)
            ))

        for role, position in sorted(
            roles,
            key=lambda x: x[1]
        ):
            try:
                await role.edit(
                    position=position,
                    reason="Crumb server restore"
                )
            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

    @tasks.loop(minutes=15)
    async def auto_backup_loop(self):

        for guild in self.bot.guilds:

            try:

                config = self.get_config(
                    guild.id
                )

                if not config["autobackup_enabled"]:
                    continue

                path = await self.create_backup(
                    guild,
                    automatic=True
                )

                if path:

                    await self.security_log(
                        guild,
                        "💾 Automatic Backup",
                        f"Automatic server backup created.\n\n"
                        f"**Backup:** `{path.stem.replace('backup_', '', 1)}`"
                    )

            except Exception as e:

                print(
                    f"[SECURITY] Auto backup error "
                    f"for {guild.id}: {e}"
                )

    @auto_backup_loop.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member):

        guild = member.guild

        config = self.get_config(
            guild.id
        )

        if not config["antiraid_enabled"]:
            return

        now = time.time()

        if guild.id not in self.join_tracker:
            self.join_tracker[guild.id] = []

        joins = self.join_tracker[guild.id]

        joins.append(now)

        cutoff = (
            now -
            config["raid_window"]
        )

        self.join_tracker[guild.id] = [
            timestamp
            for timestamp in joins
            if timestamp >= cutoff
        ]

        count = len(
            self.join_tracker[guild.id]
        )

        if count < config["raid_threshold"]:
            return

        last_trigger = self.raid_cooldowns.get(
            guild.id,
            0
        )

        if (
            now - last_trigger
            < config["raid_cooldown"]
        ):
            return

        self.raid_cooldowns[
            guild.id
        ] = now

        await self.activate_raid_mode(
            guild,
            count
        )

    async def activate_raid_mode(
        self,
        guild,
        join_count
    ):

        changed = 0

        for channel in guild.text_channels:

            try:

                overwrite = channel.overwrites_for(
                    guild.default_role
                )

                overwrite.send_messages = False

                await channel.set_permissions(
                    guild.default_role,
                    overwrite=overwrite,
                    reason="Crumb Anti-Raid"
                )

                changed += 1

            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

        self.update_config(
            guild.id,
            "lockdown_enabled",
            1
        )

        await self.security_log(
            guild,
            "🚨 Raid Detected",
            f"**{join_count} members** joined within "
            f"the configured raid window.\n\n"
            f"Crumb automatically activated lockdown.\n\n"
            f"Channels locked: **{changed}**",
            discord.Colour.red()
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self,
        channel
    ):

        config = self.get_config(
            channel.guild.id
        )

        if not config["antinuke_enabled"]:
            return

        await self.check_nuke(
            channel.guild,
            discord.AuditLogAction.channel_delete,
            "Channel Delete"
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(
        self,
        role
    ):

        config = self.get_config(
            role.guild.id
        )

        if not config["antinuke_enabled"]:
            return

        await self.check_nuke(
            role.guild,
            discord.AuditLogAction.role_delete,
            "Role Delete"
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self,
        channel
    ):

        config = self.get_config(
            channel.guild.id
        )

        if not config["antinuke_enabled"]:
            return

        await self.check_nuke(
            channel.guild,
            discord.AuditLogAction.channel_create,
            "Channel Create"
        )

    @commands.Cog.listener()
    async def on_guild_role_create(
        self,
        role
    ):

        config = self.get_config(
            role.guild.id
        )

        if not config["antinuke_enabled"]:
            return

        await self.check_nuke(
            role.guild,
            discord.AuditLogAction.role_create,
            "Role Create"
        )

    async def check_nuke(
        self,
        guild,
        audit_action,
        action_name
    ):

        try:

            await asyncio.sleep(0.5)

            async for entry in guild.audit_logs(
                limit=1,
                action=audit_action
            ):

                executor = entry.user

                if executor is None:
                    return

                if (
                    self.bot.user
                    and executor.id == self.bot.user.id
                ):
                    return

                if executor.id == guild.owner_id:
                    return

                if self.is_whitelisted(
                    guild.id,
                    executor.id
                ):
                    return

                now = time.time()

                key = (
                    guild.id,
                    executor.id,
                    action_name
                )

                if key not in self.nuke_tracker:
                    self.nuke_tracker[key] = []

                actions = self.nuke_tracker[key]

                actions.append(now)

                config = self.get_config(
                    guild.id
                )

                cutoff = (
                    now -
                    config["nuke_window"]
                )

                self.nuke_tracker[key] = [
                    timestamp
                    for timestamp in actions
                    if timestamp >= cutoff
                ]

                count = len(
                    self.nuke_tracker[key]
                )

                if count < config["nuke_threshold"]:
                    return

                await self.handle_nuke(
                    guild,
                    executor,
                    action_name,
                    count
                )

                self.nuke_tracker[key] = []

                return

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            return

    async def handle_nuke(
        self,
        guild,
        executor,
        action_name,
        count
    ):

        for channel in guild.text_channels:

            try:

                overwrite = channel.overwrites_for(
                    guild.default_role
                )

                overwrite.send_messages = False

                await channel.set_permissions(
                    guild.default_role,
                    overwrite=overwrite,
                    reason="Crumb Anti-Nuke"
                )

            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

        self.update_config(
            guild.id,
            "lockdown_enabled",
            1
        )

        member = guild.get_member(
            executor.id
        )

        removed_roles = 0

        if member and guild.me:

            removable_roles = [
                role
                for role in member.roles
                if (
                    role != guild.default_role
                    and role < guild.me.top_role
                    and (
                        role.permissions.administrator
                        or role.permissions.manage_guild
                        or role.permissions.manage_channels
                        or role.permissions.manage_roles
                        or role.permissions.ban_members
                        or role.permissions.kick_members
                    )
                )
            ]

            for role in removable_roles:

                try:

                    await member.remove_roles(
                        role,
                        reason="Crumb Anti-Nuke"
                    )

                    removed_roles += 1

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    pass

        await self.security_log(
            guild,
            "☢️ ANTI-NUKE TRIGGERED",
            f"**Executor:** {executor.mention}\n"
            f"**Action:** {action_name}\n"
            f"**Actions detected:** {count}\n\n"
            f"🔒 Server lockdown activated.\n"
            f"🛡️ Dangerous roles removed: **{removed_roles}**",
            discord.Colour.red()
        )

    @tasks.loop(minutes=5)
    async def cleanup_tracker(self):

        now = time.time()

        for guild_id in list(
            self.join_tracker.keys()
        ):

            self.join_tracker[guild_id] = [
                timestamp
                for timestamp in self.join_tracker[guild_id]
                if timestamp > now - 3600
            ]

            if not self.join_tracker[guild_id]:
                del self.join_tracker[guild_id]

        for key in list(
            self.nuke_tracker.keys()
        ):

            self.nuke_tracker[key] = [
                timestamp
                for timestamp in self.nuke_tracker[key]
                if timestamp > now - 3600
            ]

            if not self.nuke_tracker[key]:
                del self.nuke_tracker[key]

    @cleanup_tracker.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def cog_app_command_error(
        self,
        interaction,
        error
    ):

        if isinstance(
            error,
            app_commands.errors.MissingPermissions
        ):

            embed = self.error_embed(
                "Missing Permissions",
                "You need **Manage Server** to use this command."
            )

        else:

            print(
                f"[SECURITY] Command error: {error}"
            )

            embed = self.error_embed(
                "Something Went Wrong",
                "An unexpected error occurred while running "
                "this command."
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

async def setup(bot):
    await bot.add_cog(Security(bot))