import sqlite3

import discord
from discord import app_commands
from discord.ext import commands

class Honeypot(commands.GroupCog, group_name="honeypot"):
    def __init__(self, bot):
        self.bot = bot

        self.db = sqlite3.connect("db/honeypot.db")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS honeypots (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                caught INTEGER NOT NULL DEFAULT 0
            )
        """)

        columns = [
            row["name"]
            for row in self.db.execute(
                "PRAGMA table_info(honeypots)"
            ).fetchall()
        ]

        if "message_id" not in columns:
            self.db.execute(
                "ALTER TABLE honeypots ADD COLUMN message_id INTEGER"
            )

        self.db.commit()

    def get_honeypot(self, guild_id: int):
        return self.db.execute(
            "SELECT * FROM honeypots WHERE guild_id = ?",
            (guild_id,)
        ).fetchone()

    def create_honeypot_embed(self, caught: int):
        embed = discord.Embed(
            title="🍯 Honeypot",
            description=(
                "This channel is a **honeypot**.\n\n"
                "Sending a message here will result in an "
                "automatic **softban**."
            ),
            color=discord.Color.orange()
        )

        embed.add_field(
            name="Users caught",
            value=f"`{caught}`",
            inline=True
        )

        embed.set_footer(
            text="Honeypot protection"
        )

        return embed

    async def update_honeypot_message(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        caught: int
    ):
        honeypot = self.get_honeypot(guild.id)

        if not honeypot:
            return

        embed = self.create_honeypot_embed(caught)

        if honeypot["message_id"]:
            try:
                status_message = await channel.fetch_message(
                    honeypot["message_id"]
                )

                await status_message.edit(embed=embed)
                return

            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        try:
            status_message = await channel.send(embed=embed)

            self.db.execute("""
                UPDATE honeypots
                SET message_id = ?
                WHERE guild_id = ?
            """, (status_message.id, guild.id))

            self.db.commit()

        except discord.Forbidden:
            pass

    @app_commands.command(
        name="setup",
        description="Create and enable a honeypot channel"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def setup(self, interaction: discord.Interaction):
        guild = interaction.guild

        if guild is None:
            return

        existing = self.get_honeypot(guild.id)

        if existing:
            channel = guild.get_channel(existing["channel_id"])

            if channel:
                embed = discord.Embed(
                    title="🍯 Honeypot Already Enabled",
                    description=(
                        f"The honeypot is already configured as "
                        f"{channel.mention}."
                    ),
                    color=discord.Color.orange()
                )

                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True
                )
                return

        try:
            channel = await guild.create_text_channel(
                "🍯・honeypot",
                topic=(
                    "Honeypot channel — sending a message here "
                    "results in removal."
                )
            )

        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Couldn't Create Honeypot",
                description=(
                    "I don't have permission to create channels."
                ),
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        self.db.execute("""
            INSERT OR REPLACE INTO honeypots
            (guild_id, channel_id, message_id, caught)
            VALUES (?, ?, NULL, 0)
        """, (guild.id, channel.id))

        self.db.commit()

        status_message = await channel.send(
            embed=self.create_honeypot_embed(0)
        )

        self.db.execute("""
            UPDATE honeypots
            SET message_id = ?
            WHERE guild_id = ?
        """, (status_message.id, guild.id))

        self.db.commit()

        embed = discord.Embed(
            title="🍯 Honeypot Enabled",
            description=(
                f"The honeypot channel has been created: {channel.mention}\n\n"
                "Anyone who sends a message there will be "
                "**softbanned** automatically."
            ),
            color=discord.Color.orange()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="add",
        description="Use an existing channel as the honeypot"
    )
    @app_commands.describe(
        channel="The channel to use as the honeypot"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        guild = interaction.guild

        if guild is None:
            return

        existing = self.get_honeypot(guild.id)

        if existing:
            old_channel = guild.get_channel(existing["channel_id"])

            if old_channel:
                embed = discord.Embed(
                    title="❌ Honeypot Already Configured",
                    description=(
                        f"The current honeypot is {old_channel.mention}.\n"
                        "Remove it first before selecting another channel."
                    ),
                    color=discord.Color.red()
                )

                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True
                )
                return

        self.db.execute("""
            INSERT OR REPLACE INTO honeypots
            (guild_id, channel_id, message_id, caught)
            VALUES (?, ?, NULL, 0)
        """, (guild.id, channel.id))

        self.db.commit()

        status_message = await channel.send(
            embed=self.create_honeypot_embed(0)
        )

        self.db.execute("""
            UPDATE honeypots
            SET message_id = ?
            WHERE guild_id = ?
        """, (status_message.id, guild.id))

        self.db.commit()

        embed = discord.Embed(
            title="🍯 Honeypot Enabled",
            description=(
                f"{channel.mention} is now the honeypot channel.\n\n"
                "Anyone who sends a message there will be "
                "**softbanned**."
            ),
            color=discord.Color.orange()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="remove",
        description="Disable the honeypot"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def remove(self, interaction: discord.Interaction):
        guild = interaction.guild

        if guild is None:
            return

        existing = self.get_honeypot(guild.id)

        if not existing:
            embed = discord.Embed(
                title="❌ No Honeypot",
                description=(
                    "This server doesn't have a honeypot configured."
                ),
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        self.db.execute(
            "DELETE FROM honeypots WHERE guild_id = ?",
            (guild.id,)
        )

        self.db.commit()

        embed = discord.Embed(
            title="🍯 Honeypot Disabled",
            description="The honeypot has been disabled.",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="config",
        description="View the current honeypot configuration"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def config(self, interaction: discord.Interaction):
        guild = interaction.guild

        if guild is None:
            return

        existing = self.get_honeypot(guild.id)

        if not existing:
            embed = discord.Embed(
                title="🍯 Honeypot",
                description="No honeypot is currently configured.",
                color=discord.Color.orange()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        channel = guild.get_channel(existing["channel_id"])

        if channel is None:
            channel_text = (
                f"`{existing['channel_id']}` (channel not found)"
            )
        else:
            channel_text = channel.mention

        embed = discord.Embed(
            title="🍯 Honeypot Configuration",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="Channel",
            value=channel_text,
            inline=True
        )

        embed.add_field(
            name="Users caught",
            value=f"`{existing['caught']}`",
            inline=True
        )

        embed.add_field(
            name="Status",
            value="🟢 Enabled",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return

        if message.author.bot:
            return

        honeypot = self.get_honeypot(message.guild.id)

        if not honeypot:
            return

        if message.channel.id != honeypot["channel_id"]:
            return

        member = message.author
        me = message.guild.me

        if me is None:
            return

        if member == message.guild.owner:
            return

        if member.top_role >= me.top_role:
            return

        if not me.guild_permissions.ban_members:
            return

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        try:
            await message.guild.ban(
                member,
                reason="Honeypot triggered",
                delete_message_seconds=0
            )

            await message.guild.unban(
                member,
                reason="Honeypot softban"
            )

        except (discord.Forbidden, discord.HTTPException):
            return

        self.db.execute("""
            UPDATE honeypots
            SET caught = caught + 1
            WHERE guild_id = ?
        """, (message.guild.id,))

        self.db.commit()

        updated = self.get_honeypot(message.guild.id)

        if not updated:
            return

        caught = updated["caught"]

        await self.update_honeypot_message(
            message.guild,
            message.channel,
            caught
        )

async def setup(bot):
    await bot.add_cog(Honeypot(bot))