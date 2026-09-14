import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = "db/reactionroles.db"
ORANGE = 0xFFA500
RED = 0xFF0000

class ReactionRoles(commands.GroupCog, group_name="rr"):
    def __init__(self, bot):
        self.bot = bot
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS panels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                color INTEGER DEFAULT 16753920
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                panel_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                mode TEXT DEFAULT 'toggle',
                exclusive_group TEXT DEFAULT '',
                UNIQUE(panel_id, role_id),
                UNIQUE(panel_id, emoji)
            )
        """)
        self.db.commit()

    def get_panel(self, panel_id):
        return self.db.execute(
            """
            SELECT *
            FROM panels
            WHERE id = ?
            """,
            (panel_id,)
        ).fetchone()

    def get_panel_by_message(self, message_id):
        return self.db.execute(
            """
            SELECT *
            FROM panels
            WHERE message_id = ?
            """,
            (message_id,)
        ).fetchone()

    def get_roles(self, panel_id):
        return self.db.execute(
            """
            SELECT *
            FROM roles
            WHERE panel_id = ?
            ORDER BY id ASC
            """,
            (panel_id,)
        ).fetchall()

    def get_role_mapping(self, panel_id, emoji):
        return self.db.execute(
            """
            SELECT *
            FROM roles
            WHERE panel_id = ?
            AND emoji = ?
            """,
            (panel_id, emoji)
        ).fetchone()

    def get_role_mapping_by_id(self, mapping_id):
        return self.db.execute(
            """
            SELECT *
            FROM roles
            WHERE id = ?
            """,
            (mapping_id,)
        ).fetchone()

    def embed(self, title, description, error=False):
        return discord.Embed(
            title=title,
            description=description,
            color=RED if error else ORANGE
        )

    def emoji_key(self, emoji):
        if isinstance(emoji, discord.PartialEmoji):
            return str(emoji)
        return str(emoji)

    def parse_emoji(self, emoji):
        emoji = emoji.strip()
        if emoji.startswith("<") and emoji.endswith(">"):
            try:
                parsed = discord.PartialEmoji.from_str(emoji)
                if parsed.id:
                    return parsed
            except Exception:
                pass
        return emoji

    def emoji_matches(self, stored, payload_emoji):
        incoming = str(payload_emoji)
        return stored == incoming

    def build_panel_embed(self, panel):
        embed = discord.Embed(
            title=panel["title"],
            description=panel["description"],
            color=panel["color"]
        )
        mappings = self.get_roles(panel["id"])
        if mappings:
            lines = []
            for mapping in mappings:
                role_name = f"<@&{mapping['role_id']}>"
                mode = mapping["mode"]
                if mode == "add":
                    mode_text = "Add only"
                elif mode == "remove":
                    mode_text = "Remove only"
                else:
                    mode_text = "Toggle"
                lines.append(
                    f"{mapping['emoji']} {role_name} — {mode_text}"
                )
            embed.add_field(
                name="Roles",
                value="\n".join(lines),
                inline=False
            )
        else:
            embed.add_field(
                name="Roles",
                value="No roles have been configured yet.",
                inline=False
            )
        embed.set_footer(
            text="React to this message to manage your roles."
        )
        return embed

    async def refresh_panel(self, panel_id):
        panel = self.get_panel(panel_id)
        if panel is None:
            return False
        guild = self.bot.get_guild(panel["guild_id"])
        if guild is None:
            return False
        channel = guild.get_channel(panel["channel_id"])
        if channel is None:
            return False
        try:
            message = await channel.fetch_message(panel["message_id"])
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            return False
        try:
            await message.edit(
                embed=self.build_panel_embed(panel)
            )
        except discord.HTTPException:
            return False
        mappings = self.get_roles(panel_id)
        existing = {
            str(reaction.emoji)
            for reaction in message.reactions
        }
        for mapping in mappings:
            emoji = mapping["emoji"]
            if emoji in existing:
                continue
            try:
                await message.add_reaction(emoji)
            except (
                discord.HTTPException,
                discord.NotFound
            ):
                pass
        return True

    async def can_manage_role(self, guild, role):
        if role.is_default():
            return False
        if role.managed:
            return False
        me = guild.me
        if me is None:
            return False
        if not me.guild_permissions.manage_roles:
            return False
        if role >= me.top_role:
            return False
        return True

    @app_commands.command(
        name="setup",
        description="Create a reaction role panel"
    )
    @app_commands.describe(
        channel="Channel where the panel should be created",
        title="Panel title",
        description="Panel description"
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str
    ):
        guild = interaction.guild
        if guild is None:
            return
        permissions = channel.permissions_for(guild.me)
        if not permissions.send_messages:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "I can't send messages in that channel.",
                    True
                ),
                ephemeral=True
            )
            return
        if not permissions.add_reactions:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "I need the **Add Reactions** permission in that channel.",
                    True
                ),
                ephemeral=True
            )
            return
        embed = discord.Embed(
            title=title,
            description=description,
            color=ORANGE
        )
        embed.set_footer(
            text="React to this message to manage your roles."
        )
        message = await channel.send(
            embed=embed
        )
        cursor = self.db.execute(
            """
            INSERT INTO panels (
                guild_id,
                channel_id,
                message_id,
                title,
                description,
                color
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                guild.id,
                channel.id,
                message.id,
                title,
                description,
                ORANGE
            )
        )
        self.db.commit()
        panel_id = cursor.lastrowid
        await interaction.response.send_message(
            embed=self.embed(
                "Reaction Role Panel Created",
                f"Panel `{panel_id}` has been created in {channel.mention}.\n\n"
                f"Message ID: `{message.id}`\n\n"
                f"Use `/rr add` to add roles to the panel."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="add",
        description="Add a role to a reaction role panel"
    )
    @app_commands.describe(
        panel="Reaction role panel ID",
        emoji="Emoji users will react with",
        role="Role to give",
        mode="What happens when the user reacts",
        exclusive_group="Optional group name for exclusive roles"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(
                name="Toggle",
                value="toggle"
            ),
            app_commands.Choice(
                name="Add only",
                value="add"
            ),
            app_commands.Choice(
                name="Remove only",
                value="remove"
            )
        ]
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    async def add(
        self,
        interaction: discord.Interaction,
        panel: int,
        emoji: str,
        role: discord.Role,
        mode: app_commands.Choice[str],
        exclusive_group: str = ""
    ):
        guild = interaction.guild
        if guild is None:
            return
        panel_data = self.get_panel(panel)
        if panel_data is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That reaction role panel doesn't exist.",
                    True
                ),
                ephemeral=True
            )
            return
        if panel_data["guild_id"] != guild.id:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That panel belongs to another server.",
                    True
                ),
                ephemeral=True
            )
            return
        if not await self.can_manage_role(guild, role):
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "I can't manage that role.\n\n"
                    "Make sure it isn't managed and is below my highest role.",
                    True
                ),
                ephemeral=True
            )
            return
        parsed_emoji = self.parse_emoji(emoji)
        emoji_key = self.emoji_key(parsed_emoji)
        existing_emoji = self.get_role_mapping(
            panel,
            emoji_key
        )
        if existing_emoji:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That emoji is already being used by this panel.",
                    True
                ),
                ephemeral=True
            )
            return
        existing_role = self.db.execute(
            """
            SELECT *
            FROM roles
            WHERE panel_id = ?
            AND role_id = ?
            """,
            (
                panel,
                role.id
            )
        ).fetchone()
        if existing_role:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That role is already configured on this panel.",
                    True
                ),
                ephemeral=True
            )
            return
        try:
            self.db.execute(
                """
                INSERT INTO roles (
                    panel_id,
                    role_id,
                    emoji,
                    mode,
                    exclusive_group
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    panel,
                    role.id,
                    emoji_key,
                    mode.value,
                    exclusive_group.strip()
                )
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That emoji or role is already configured.",
                    True
                ),
                ephemeral=True
            )
            return
        refreshed = await self.refresh_panel(panel)
        if not refreshed:
            await interaction.response.send_message(
                embed=self.embed(
                    "Warning",
                    "The role was saved, but I couldn't update the panel message.",
                    True
                ),
                ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=self.embed(
                "Role Added",
                f"{emoji_key} → {role.mention}\n\n"
                f"Mode: **{mode.name}**"
                + (
                    f"\nExclusive group: **{exclusive_group}**"
                    if exclusive_group.strip()
                    else ""
                )
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="remove",
        description="Remove a role from a reaction role panel"
    )
    @app_commands.describe(
        panel="Reaction role panel ID",
        emoji="Emoji mapping to remove"
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    async def remove(
        self,
        interaction: discord.Interaction,
        panel: int,
        emoji: str
    ):
        guild = interaction.guild
        if guild is None:
            return
        panel_data = self.get_panel(panel)
        if panel_data is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That reaction role panel doesn't exist.",
                    True
                ),
                ephemeral=True
            )
            return
        if panel_data["guild_id"] != guild.id:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That panel belongs to another server.",
                    True
                ),
                ephemeral=True
            )
            return
        parsed = self.parse_emoji(emoji)
        emoji_key = self.emoji_key(parsed)
        mapping = self.get_role_mapping(
            panel,
            emoji_key
        )
        if mapping is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That emoji isn't configured on this panel.",
                    True
                ),
                ephemeral=True
            )
            return
        self.db.execute(
            """
            DELETE FROM roles
            WHERE id = ?
            """,
            (mapping["id"],)
        )
        self.db.commit()
        await self.refresh_panel(panel)
        await interaction.response.send_message(
            embed=self.embed(
                "Role Removed",
                f"Removed `{emoji_key}` from panel `{panel}`."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="edit",
        description="Edit a reaction role panel"
    )
    @app_commands.describe(
        panel="Reaction role panel ID",
        title="New panel title",
        description="New panel description"
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    async def edit(
        self,
        interaction: discord.Interaction,
        panel: int,
        title: str | None = None,
        description: str | None = None
    ):
        guild = interaction.guild
        if guild is None:
            return
        panel_data = self.get_panel(panel)
        if panel_data is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That reaction role panel doesn't exist.",
                    True
                ),
                ephemeral=True
            )
            return
        if panel_data["guild_id"] != guild.id:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That panel belongs to another server.",
                    True
                ),
                ephemeral=True
            )
            return
        if title is None and description is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "Provide a new title, description, or both.",
                    True
                ),
                ephemeral=True
            )
            return
        new_title = (
            title
            if title is not None
            else panel_data["title"]
        )
        new_description = (
            description
            if description is not None
            else panel_data["description"]
        )
        self.db.execute(
            """
            UPDATE panels
            SET
                title = ?,
                description = ?
            WHERE id = ?
            """,
            (
                new_title,
                new_description,
                panel
            )
        )
        self.db.commit()
        refreshed = await self.refresh_panel(panel)
        if not refreshed:
            await interaction.response.send_message(
                embed=self.embed(
                    "Warning",
                    "The panel was edited, but I couldn't update its message.",
                    True
                ),
                ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=self.embed(
                "Panel Updated",
                f"Panel `{panel}` has been updated."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="list",
        description="List reaction role panels"
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    async def list(
        self,
        interaction: discord.Interaction
    ):
        guild = interaction.guild
        if guild is None:
            return
        panels = self.db.execute(
            """
            SELECT *
            FROM panels
            WHERE guild_id = ?
            ORDER BY id ASC
            """,
            (guild.id,)
        ).fetchall()
        if not panels:
            await interaction.response.send_message(
                embed=self.embed(
                    "Reaction Role Panels",
                    "This server doesn't have any reaction role panels."
                ),
                ephemeral=True
            )
            return
        lines = []
        for panel in panels:
            role_count = self.db.execute(
                """
                SELECT COUNT(*)
                FROM roles
                WHERE panel_id = ?
                """,
                (panel["id"],)
            ).fetchone()[0]
            channel = guild.get_channel(
                panel["channel_id"]
            )
            channel_text = (
                channel.mention
                if channel
                else "Unknown channel"
            )
            lines.append(
                f"**`{panel['id']}`** — {panel['title']}\n"
                f"└ {channel_text} • `{role_count}` role(s)"
            )
        await interaction.response.send_message(
            embed=self.embed(
                "Reaction Role Panels",
                "\n\n".join(lines)
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="refresh",
        description="Refresh a reaction role panel"
    )
    @app_commands.describe(
        panel="Reaction role panel ID"
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    async def refresh(
        self,
        interaction: discord.Interaction,
        panel: int
    ):
        guild = interaction.guild
        if guild is None:
            return
        panel_data = self.get_panel(panel)
        if panel_data is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That reaction role panel doesn't exist.",
                    True
                ),
                ephemeral=True
            )
            return
        if panel_data["guild_id"] != guild.id:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That panel belongs to another server.",
                    True
                ),
                ephemeral=True
            )
            return
        success = await self.refresh_panel(panel)
        if not success:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "I couldn't refresh that panel. "
                    "The message or channel may have been deleted.",
                    True
                ),
                ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=self.embed(
                "Panel Refreshed",
                f"Panel `{panel}` has been refreshed."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="delete",
        description="Delete a reaction role panel"
    )
    @app_commands.describe(
        panel="Reaction role panel ID",
        delete_message="Also delete the Discord message"
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    async def delete(
        self,
        interaction: discord.Interaction,
        panel: int,
        delete_message: bool = True
    ):
        guild = interaction.guild
        if guild is None:
            return
        panel_data = self.get_panel(panel)
        if panel_data is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That reaction role panel doesn't exist.",
                    True
                ),
                ephemeral=True
            )
            return
        if panel_data["guild_id"] != guild.id:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "That panel belongs to another server.",
                    True
                ),
                ephemeral=True
            )
            return
        if delete_message:
            channel = guild.get_channel(
                panel_data["channel_id"]
            )
            if channel:
                try:
                    message = await channel.fetch_message(
                        panel_data["message_id"]
                    )
                    await message.delete()
                except (
                    discord.NotFound,
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    pass
        self.db.execute(
            """
            DELETE FROM roles
            WHERE panel_id = ?
            """,
            (panel,)
        )
        self.db.execute(
            """
            DELETE FROM panels
            WHERE id = ?
            """,
            (panel,)
        )
        self.db.commit()
        await interaction.response.send_message(
            embed=self.embed(
                "Panel Deleted",
                f"Reaction role panel `{panel}` has been deleted."
            ),
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent
    ):
        if payload.guild_id is None:
            return
        if payload.user_id == self.bot.user.id:
            return
        panel = self.get_panel_by_message(
            payload.message_id
        )
        if panel is None:
            return
        mapping = self.get_role_mapping(
            panel["id"],
            str(payload.emoji)
        )
        if mapping is None:
            return
        guild = self.bot.get_guild(
            payload.guild_id
        )
        if guild is None:
            return
        member = guild.get_member(
            payload.user_id
        )
        if member is None:
            try:
                member = await guild.fetch_member(
                    payload.user_id
                )
            except (
                discord.NotFound,
                discord.HTTPException
            ):
                return
        role = guild.get_role(
            mapping["role_id"]
        )
        if role is None:
            return
        if not await self.can_manage_role(
            guild,
            role
        ):
            return
        exclusive_group = mapping["exclusive_group"]
        if exclusive_group:
            other_mappings = self.db.execute(
                """
                SELECT *
                FROM roles
                WHERE panel_id = ?
                AND exclusive_group = ?
                AND id != ?
                """,
                (
                    panel["id"],
                    exclusive_group,
                    mapping["id"]
                )
            ).fetchall()
            for other in other_mappings:
                other_role = guild.get_role(
                    other["role_id"]
                )
                if other_role is None:
                    continue
                if other_role in member.roles:
                    if await self.can_manage_role(
                        guild,
                        other_role
                    ):
                        try:
                            await member.remove_roles(
                                other_role,
                                reason="Reaction role exclusive group"
                            )
                        except discord.HTTPException:
                            pass
        try:
            if mapping["mode"] == "remove":
                if role in member.roles:
                    await member.remove_roles(
                        role,
                        reason="Reaction role"
                    )
            else:
                if role not in member.roles:
                    await member.add_roles(
                        role,
                        reason="Reaction role"
                    )
        except discord.HTTPException:
            pass
        channel = guild.get_channel(
            panel["channel_id"]
        )
        if channel:
            try:
                message = await channel.fetch_message(
                    panel["message_id"]
                )
                await message.remove_reaction(
                    payload.emoji,
                    member
                )
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self,
        payload: discord.RawReactionActionEvent
    ):
        if payload.guild_id is None:
            return
        if payload.user_id == self.bot.user.id:
            return
        panel = self.get_panel_by_message(
            payload.message_id
        )
        if panel is None:
            return
        mapping = self.get_role_mapping(
            panel["id"],
            str(payload.emoji)
        )
        if mapping is None:
            return
        if mapping["mode"] == "remove":
            return
        guild = self.bot.get_guild(
            payload.guild_id
        )
        if guild is None:
            return
        member = guild.get_member(
            payload.user_id
        )
        if member is None:
            try:
                member = await guild.fetch_member(
                    payload.user_id
                )
            except (
                discord.NotFound,
                discord.HTTPException
            ):
                return
        role = guild.get_role(
            mapping["role_id"]
        )
        if role is None:
            return
        if not await self.can_manage_role(
            guild,
            role
        ):
            return
        try:
            if role in member.roles:
                await member.remove_roles(
                    role,
                    reason="Reaction role removed"
                )
        except discord.HTTPException:
            pass

    async def cleanup_deleted_panels(self):
        panels = self.db.execute(
            """
            SELECT *
            FROM panels
            """
        ).fetchall()
        for panel in panels:
            guild = self.bot.get_guild(
                panel["guild_id"]
            )
            if guild is None:
                continue
            channel = guild.get_channel(
                panel["channel_id"]
            )
            if channel is None:
                self.db.execute(
                    """
                    DELETE FROM roles
                    WHERE panel_id = ?
                    """,
                    (panel["id"],)
                )
                self.db.execute(
                    """
                    DELETE FROM panels
                    WHERE id = ?
                    """,
                    (panel["id"],)
                )
                continue
            try:
                await channel.fetch_message(
                    panel["message_id"]
                )
            except discord.NotFound:
                self.db.execute(
                    """
                    DELETE FROM roles
                    WHERE panel_id = ?
                    """,
                    (panel["id"],)
                )
                self.db.execute(
                    """
                    DELETE FROM panels
                    WHERE id = ?
                    """,
                    (panel["id"],)
                )
            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass
        self.db.commit()

    def cog_unload(self):
        self.db.close()

async def setup(bot):
    await bot.add_cog(
        ReactionRoles(bot)
    )