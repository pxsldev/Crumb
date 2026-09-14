import sqlite3

import discord

from discord import app_commands
from discord.ext import commands


DB_PATH = "db/temporaryvcs.db"

ORANGE = 0xFFA500
RED = 0xFF0000


class TemporaryVCs(commands.GroupCog, group_name="tempvc"):

    def __init__(self, bot):
        self.bot = bot
        self.db = sqlite3.connect(
            DB_PATH,
            check_same_thread=False
        )
        self.db.row_factory = sqlite3.Row
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS temporaryvcs (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                trigger_channel_id INTEGER,
                category_id INTEGER,
                name_format TEXT DEFAULT '🔊 {username}''s Room',
                user_limit INTEGER DEFAULT 0
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS temp_channels (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                owner_id INTEGER
            )
        """)
        self.db.commit()

    def get_config(self, guild_id):
        return self.db.execute(
            "SELECT * FROM temporaryvcs WHERE guild_id = ?",
            (guild_id,)
        ).fetchone()

    def create_config(self, guild_id):
        self.db.execute("""
            INSERT OR IGNORE INTO temporaryvcs (
                guild_id,
                enabled
            )
            VALUES (?, 0)
        """, (guild_id,))
        self.db.commit()

    def is_temp_channel(self, channel_id):
        return self.db.execute(
            "SELECT * FROM temp_channels WHERE channel_id = ?",
            (channel_id,)
        ).fetchone()

    def add_temp_channel(self, channel_id, guild_id, owner_id):
        self.db.execute("""
            INSERT OR REPLACE INTO temp_channels (
                channel_id,
                guild_id,
                owner_id
            )
            VALUES (?, ?, ?)
        """, (
            channel_id,
            guild_id,
            owner_id
        ))
        self.db.commit()

    def remove_temp_channel(self, channel_id):
        self.db.execute(
            "DELETE FROM temp_channels WHERE channel_id = ?",
            (channel_id,)
        )
        self.db.commit()

    def embed(self, title, description, error=False):
        return discord.Embed(
            title=title,
            description=description,
            color=RED if error else ORANGE
        )

    @app_commands.command(
        name="setup",
        description="Set up temporary voice channels"
    )
    @app_commands.describe(
        category="Category where temporary VCs will be created"
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel | None = None
    ):
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "This command can only be used in a server.",
                    True
                ),
                ephemeral=True
            )
            return

        self.create_config(guild.id)
        config = self.get_config(guild.id)

        if category is None:
            if config["category_id"]:
                category = guild.get_channel(
                    config["category_id"]
                )

            if category is None:
                category = await guild.create_category(
                    "Temporary VCs"
                )

        trigger = None

        if config["trigger_channel_id"]:
            trigger = guild.get_channel(
                config["trigger_channel_id"]
            )

        if trigger is None:
            trigger = await guild.create_voice_channel(
                "➕ Create VC",
                category=category
            )

        self.db.execute("""
            UPDATE temporaryvcs
            SET
                enabled = 1,
                trigger_channel_id = ?,
                category_id = ?
            WHERE guild_id = ?
        """, (
            trigger.id,
            category.id,
            guild.id
        ))
        self.db.commit()

        await interaction.response.send_message(
            embed=self.embed(
                "Temporary VCs Enabled",
                f"Join {trigger.mention} to create your own temporary voice channel."
            )
        )

    @app_commands.command(
        name="enable",
        description="Enable temporary voice channels"
    )
    async def enable(self, interaction: discord.Interaction):
        guild = interaction.guild

        if guild is None:
            return

        config = self.get_config(guild.id)

        if config is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "Temporary VCs haven't been set up yet.\n\nUse `/tempvc setup` first.",
                    True
                ),
                ephemeral=True
            )
            return

        self.db.execute("""
            UPDATE temporaryvcs
            SET enabled = 1
            WHERE guild_id = ?
        """, (guild.id,))
        self.db.commit()

        await interaction.response.send_message(
            embed=self.embed(
                "Temporary VCs Enabled",
                "Temporary voice channels are now enabled."
            )
        )

    @app_commands.command(
        name="disable",
        description="Disable temporary voice channels"
    )
    async def disable(self, interaction: discord.Interaction):
        guild = interaction.guild

        if guild is None:
            return

        self.db.execute("""
            UPDATE temporaryvcs
            SET enabled = 0
            WHERE guild_id = ?
        """, (guild.id,))
        self.db.commit()

        await interaction.response.send_message(
            embed=self.embed(
                "Temporary VCs Disabled",
                "Temporary voice channels are now disabled."
            )
        )

    @app_commands.command(
        name="config",
        description="View temporary VC configuration"
    )
    async def config(self, interaction: discord.Interaction):
        guild = interaction.guild

        if guild is None:
            return

        config = self.get_config(guild.id)

        if config is None:
            await interaction.response.send_message(
                embed=self.embed(
                    "Error",
                    "Temporary VCs haven't been set up yet.",
                    True
                ),
                ephemeral=True
            )
            return

        trigger = (
            guild.get_channel(config["trigger_channel_id"])
            if config["trigger_channel_id"]
            else None
        )

        category = (
            guild.get_channel(config["category_id"])
            if config["category_id"]
            else None
        )

        limit = config["user_limit"]

        embed = self.embed(
            "Temporary VC Configuration",
            ""
        )

        embed.add_field(
            name="Status",
            value="Enabled" if config["enabled"] else "Disabled",
            inline=True
        )

        embed.add_field(
            name="Create Channel",
            value=trigger.mention if trigger else "Not configured",
            inline=True
        )

        embed.add_field(
            name="Category",
            value=category.mention if category else "Not configured",
            inline=True
        )

        embed.add_field(
            name="Name Format",
            value=f"`{config['name_format']}`",
            inline=False
        )

        embed.add_field(
            name="User Limit",
            value=str(limit) if limit else "Unlimited",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="reset",
        description="Reset temporary VC configuration"
    )
    async def reset(self, interaction: discord.Interaction):
        guild = interaction.guild

        if guild is None:
            return

        rows = self.db.execute("""
            SELECT channel_id
            FROM temp_channels
            WHERE guild_id = ?
        """, (guild.id,)).fetchall()

        deleted = 0

        for row in rows:
            channel = guild.get_channel(
                row["channel_id"]
            )

            if channel:
                try:
                    await channel.delete(
                        reason="Temporary VC system reset"
                    )
                    deleted += 1
                except discord.HTTPException:
                    pass

        self.db.execute(
            "DELETE FROM temp_channels WHERE guild_id = ?",
            (guild.id,)
        )

        self.db.execute(
            "DELETE FROM temporaryvcs WHERE guild_id = ?",
            (guild.id,)
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.embed(
                "Temporary VCs Reset",
                f"Temporary VC configuration has been reset.\n"
                f"Deleted `{deleted}` temporary channel(s)."
            )
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        guild = member.guild
        config = self.get_config(guild.id)

        if config is None:
            return

        if (
            after.channel
            and config["enabled"]
            and after.channel.id == config["trigger_channel_id"]
        ):
            category = None

            if config["category_id"]:
                category = guild.get_channel(
                    config["category_id"]
                )

            name = config["name_format"]

            name = name.replace(
                "{username}",
                member.display_name
            )

            name = name.replace(
                "{user}",
                member.name
            )

            name = name.replace(
                "{id}",
                str(member.id)
            )

            try:
                channel = await guild.create_voice_channel(
                    name=name,
                    category=category,
                    user_limit=config["user_limit"],
                    reason="Temporary VC created"
                )
            except discord.HTTPException:
                return

            self.add_temp_channel(
                channel.id,
                guild.id,
                member.id
            )

            try:
                await member.move_to(channel)
            except discord.HTTPException:
                try:
                    await channel.delete(
                        reason="Failed to move member into temporary VC"
                    )
                except discord.HTTPException:
                    pass

                self.remove_temp_channel(channel.id)
                return

        if before.channel:
            temp = self.is_temp_channel(
                before.channel.id
            )

            if temp is None:
                return

            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(
                        reason="Temporary VC became empty"
                    )
                except discord.HTTPException:
                    pass

                self.remove_temp_channel(
                    before.channel.id
                )

    async def cleanup_channels(self):
        for guild in self.bot.guilds:
            rows = self.db.execute("""
                SELECT channel_id
                FROM temp_channels
                WHERE guild_id = ?
            """, (guild.id,)).fetchall()

            for row in rows:
                channel = guild.get_channel(
                    row["channel_id"]
                )

                if channel is None:
                    self.remove_temp_channel(
                        row["channel_id"]
                    )
                    continue

                if len(channel.members) == 0:
                    try:
                        await channel.delete(
                            reason="Temporary VC cleanup"
                        )
                    except discord.HTTPException:
                        pass

                    self.remove_temp_channel(
                        channel.id
                    )

    def cog_unload(self):
        self.db.close()


async def setup(bot):
    await bot.add_cog(
        TemporaryVCs(bot)
    )