import io
import random
import sqlite3
import string
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter

class CaptchaModal(discord.ui.Modal, title="Server Verification"):
    answer = discord.ui.TextInput(
        label="Enter the CAPTCHA",
        placeholder="Enter the characters shown in the image",
        min_length=6,
        max_length=6,
        required=True,
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_captcha(
            interaction,
            str(self.answer.value).strip().upper(),
        )

class CaptchaView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(
        label="Enter CAPTCHA",
        style=discord.ButtonStyle.primary,
        emoji="🔢",
    )
    async def enter_captcha(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.cog.error_embed(
                    "Verification can only be used inside a server."
                ),
                ephemeral=True,
            )
            return

        row = self.cog.db.execute(
            """
            SELECT *
            FROM captcha
            WHERE guild_id = ?
              AND user_id = ?
            """,
            (
                interaction.guild.id,
                interaction.user.id,
            ),
        ).fetchone()

        if not row:
            await interaction.response.send_message(
                embed=self.cog.error_embed(
                    "Your CAPTCHA has expired.\n\n"
                    "Click **Verify** again to generate a new one."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            CaptchaModal(self.cog)
        )

class VerifyView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="crumb:verification:verify",
    )
    async def verify(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await self.cog.start_verification(interaction)

class Verification(commands.GroupCog, group_name="verification"):
    def __init__(self, bot):
        self.bot = bot

        self.db = sqlite3.connect(
            "db/verification.db",
            check_same_thread=False,
        )
        self.db.row_factory = sqlite3.Row

        self.setup_database()

        self.bot.add_view(VerifyView(self))

    def setup_database(self):
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS verification (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                verify_channel_id INTEGER,
                unverified_role_id INTEGER,
                verified_role_id INTEGER,
                message_id INTEGER
            )
            """
        )

        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS captcha (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                answer TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        self.db.commit()

    def get_config(self, guild_id):
        return self.db.execute(
            """
            SELECT *
            FROM verification
            WHERE guild_id = ?
            """,
            (guild_id,),
        ).fetchone()

    def ensure_config(self, guild_id):
        self.db.execute(
            """
            INSERT OR IGNORE INTO verification (guild_id)
            VALUES (?)
            """,
            (guild_id,),
        )

        self.db.commit()

        return self.get_config(guild_id)

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

    def verification_embed(self):
        return discord.Embed(
            title="🔐 Server Verification",
            description=(
                "Welcome to the server!\n\n"
                "Before you can access the rest of the server, "
                "you need to complete a quick CAPTCHA.\n\n"
                "This helps protect the server from bots and raids.\n\n"
                "**Click the button below to begin.**"
            ),
            color=discord.Color.orange(),
        )

    def generate_captcha_text(self):
        characters = (
            string.ascii_uppercase
            + string.digits
        )

        for character in ("O", "0", "I", "1"):
            characters = characters.replace(
                character,
                "",
            )

        return "".join(
            random.choice(characters)
            for _ in range(6)
        )

    def generate_captcha_image(self, text):
        width = 420
        height = 160

        image = Image.new(
            "RGB",
            (width, height),
            "white",
        )

        draw = ImageDraw.Draw(image)

        for _ in range(1800):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)

            shade = random.randint(150, 235)

            draw.point(
                (x, y),
                fill=(shade, shade, shade),
            )

        for _ in range(15):
            draw.line(
                (
                    random.randint(0, width),
                    random.randint(0, height),
                    random.randint(0, width),
                    random.randint(0, height),
                ),
                fill=(
                    random.randint(80, 190),
                    random.randint(80, 190),
                    random.randint(80, 190),
                ),
                width=random.randint(1, 3),
            )

        x = 45

        for character in text:
            y = random.randint(35, 70)

            draw.text(
                (x, y),
                character,
                fill="black",
            )

            x += 55

        image = image.filter(
            ImageFilter.GaussianBlur(
                radius=0.35
            )
        )

        buffer = io.BytesIO()

        image.save(
            buffer,
            format="PNG",
        )

        buffer.seek(0)

        return buffer

    async def start_verification(
        self,
        interaction: discord.Interaction,
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Verification can only be used inside a server."
                ),
                ephemeral=True,
            )
            return

        config = self.get_config(
            interaction.guild.id
        )

        if not config or not config["enabled"]:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Verification is not enabled in this server."
                ),
                ephemeral=True,
            )
            return

        member = interaction.guild.get_member(
            interaction.user.id
        )

        if not member:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "I couldn't find you in this server."
                ),
                ephemeral=True,
            )
            return

        verified_role = interaction.guild.get_role(
            config["verified_role_id"]
        )

        if verified_role and verified_role in member.roles:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "You're already verified."
                ),
                ephemeral=True,
            )
            return

        if not verified_role:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "The verified role is missing.\n\n"
                    "Ask an administrator to run "
                    "`/verification 1 setup` again."
                ),
                ephemeral=True,
            )
            return

        captcha = self.generate_captcha_text()

        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(minutes=5)
        ).isoformat()

        self.db.execute(
            """
            INSERT INTO captcha (
                guild_id,
                user_id,
                answer,
                expires_at,
                attempts
            )
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
                answer = excluded.answer,
                expires_at = excluded.expires_at,
                attempts = 0
            """,
            (
                interaction.guild.id,
                interaction.user.id,
                captcha,
                expires_at,
            ),
        )

        self.db.commit()

        image_buffer = self.generate_captcha_image(
            captcha
        )

        file = discord.File(
            image_buffer,
            filename="captcha.png",
        )

        embed = discord.Embed(
            title="🔐 CAPTCHA Verification",
            description=(
                "Enter the characters shown in the image.\n\n"
                "⏱️ This CAPTCHA expires in **5 minutes**.\n"
                "❌ You have **5 attempts**."
            ),
            color=discord.Color.orange(),
        )

        embed.set_image(
            url="attachment://captcha.png"
        )

        await interaction.response.send_message(
            embed=embed,
            file=file,
            view=CaptchaView(self),
            ephemeral=True,
        )

    async def handle_captcha(
        self,
        interaction: discord.Interaction,
        answer: str,
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Verification can only be used inside a server."
                ),
                ephemeral=True,
            )
            return

        row = self.db.execute(
            """
            SELECT *
            FROM captcha
            WHERE guild_id = ?
              AND user_id = ?
            """,
            (
                interaction.guild.id,
                interaction.user.id,
            ),
        ).fetchone()

        if not row:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Your CAPTCHA has expired.\n\n"
                    "Click **Verify** again to generate a new one."
                ),
                ephemeral=True,
            )
            return

        try:
            expires_at = datetime.fromisoformat(
                row["expires_at"]
            )

            if datetime.now(timezone.utc) >= expires_at:
                self.db.execute(
                    """
                    DELETE FROM captcha
                    WHERE guild_id = ?
                      AND user_id = ?
                    """,
                    (
                        interaction.guild.id,
                        interaction.user.id,
                    ),
                )

                self.db.commit()

                await interaction.response.send_message(
                    embed=self.error_embed(
                        "Your CAPTCHA has expired.\n\n"
                        "Click **Verify** again to generate a new one."
                    ),
                    ephemeral=True,
                )
                return

        except ValueError:
            pass

        attempts = row["attempts"] + 1

        if answer != row["answer"]:
            if attempts >= 5:
                self.db.execute(
                    """
                    DELETE FROM captcha
                    WHERE guild_id = ?
                      AND user_id = ?
                    """,
                    (
                        interaction.guild.id,
                        interaction.user.id,
                    ),
                )

                self.db.commit()

                await interaction.response.send_message(
                    embed=self.error_embed(
                        "You've reached the maximum number of "
                        "CAPTCHA attempts.\n\n"
                        "Click **Verify** again to receive a new CAPTCHA."
                    ),
                    ephemeral=True,
                )
                return

            self.db.execute(
                """
                UPDATE captcha
                SET attempts = ?
                WHERE guild_id = ?
                  AND user_id = ?
                """,
                (
                    attempts,
                    interaction.guild.id,
                    interaction.user.id,
                ),
            )

            self.db.commit()

            remaining = 5 - attempts

            await interaction.response.send_message(
                embed=self.error_embed(
                    "Incorrect CAPTCHA.\n\n"
                    f"You have **{remaining}** attempt"
                    f"{'' if remaining == 1 else 's'} remaining."
                ),
                ephemeral=True,
            )
            return

        config = self.get_config(
            interaction.guild.id
        )

        if not config:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Verification configuration could not be found."
                ),
                ephemeral=True,
            )
            return

        member = interaction.guild.get_member(
            interaction.user.id
        )

        if not member:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "I couldn't find you in the server."
                ),
                ephemeral=True,
            )
            return

        verified_role = interaction.guild.get_role(
            config["verified_role_id"]
        )

        unverified_role = interaction.guild.get_role(
            config["unverified_role_id"]
        )

        if not verified_role:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "The verified role no longer exists."
                ),
                ephemeral=True,
            )
            return

        try:
            if (
                unverified_role
                and unverified_role in member.roles
            ):
                await member.remove_roles(
                    unverified_role,
                    reason="Completed Crumb verification",
                )

            if verified_role not in member.roles:
                await member.add_roles(
                    verified_role,
                    reason="Completed Crumb verification",
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "I don't have permission to manage your "
                    "verification roles.\n\n"
                    "Make sure my bot role is above both "
                    "verification roles."
                ),
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Discord rejected the role change. "
                    "Please try again."
                ),
                ephemeral=True,
            )
            return

        self.db.execute(
            """
            DELETE FROM captcha
            WHERE guild_id = ?
              AND user_id = ?
            """,
            (
                interaction.guild.id,
                interaction.user.id,
            ),
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "You've been successfully verified! 🎉\n\n"
                "You now have access to the server."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="setup",
        description="Set up server verification",
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

        me = guild.me

        if not me:
            await interaction.followup.send(
                embed=self.error_embed(
                    "I couldn't find my member object."
                ),
                ephemeral=True,
            )
            return

        config = self.get_config(guild.id)

        unverified_role = guild.get_role(
            config["unverified_role_id"]
        )

        verified_role = guild.get_role(
            config["verified_role_id"]
        )

        try:
            if not unverified_role:
                unverified_role = await guild.create_role(
                    name="Unverified",
                    reason="Crumb verification setup",
                )

            if not verified_role:
                verified_role = await guild.create_role(
                    name="Verified",
                    reason="Crumb verification setup",
                )

        except discord.Forbidden:
            await interaction.followup.send(
                embed=self.error_embed(
                    "I don't have permission to create roles."
                ),
                ephemeral=True,
            )
            return

        if (
            unverified_role >= me.top_role
            or verified_role >= me.top_role
        ):
            await interaction.followup.send(
                embed=self.error_embed(
                    "My highest role must be above the "
                    "**Unverified** and **Verified** roles."
                ),
                ephemeral=True,
            )
            return

        channel = guild.get_channel(
            config["verify_channel_id"]
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            try:
                channel = await guild.create_text_channel(
                    "verify",
                    reason="Crumb verification setup",
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=self.error_embed(
                        "I don't have permission to create channels."
                    ),
                    ephemeral=True,
                )
                return

        try:
            await channel.set_permissions(
                guild.default_role,
                view_channel=True,
                send_messages=False,
                add_reactions=False,
                create_public_threads=False,
                create_private_threads=False,
            )

            await channel.set_permissions(
                unverified_role,
                view_channel=True,
                send_messages=False,
                add_reactions=False,
                create_public_threads=False,
                create_private_threads=False,
            )

            await channel.set_permissions(
                verified_role,
                view_channel=False,
            )

            await channel.set_permissions(
                me,
                view_channel=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                manage_messages=True,
            )

        except discord.Forbidden:
            await interaction.followup.send(
                embed=self.error_embed(
                    "I don't have permission to configure "
                    "the verification channel."
                ),
                ephemeral=True,
            )
            return

        failed_channels = 0

        for target_channel in guild.channels:
            if target_channel.id == channel.id:
                continue

            try:
                await target_channel.set_permissions(
                    unverified_role,
                    view_channel=False,
                )

            except (
                discord.Forbidden,
                discord.HTTPException,
            ):
                failed_channels += 1

        message = None

        if config["message_id"]:
            try:
                message = await channel.fetch_message(
                    config["message_id"]
                )

                await message.edit(
                    embed=self.verification_embed(),
                    view=VerifyView(self),
                )

            except discord.NotFound:
                message = None

            except discord.HTTPException:
                message = None

        if message is None:
            try:
                message = await channel.send(
                    embed=self.verification_embed(),
                    view=VerifyView(self),
                )

            except discord.Forbidden:
                await interaction.followup.send(
                    embed=self.error_embed(
                        "I couldn't send the verification message."
                    ),
                    ephemeral=True,
                )
                return

        self.db.execute(
            """
            UPDATE verification
            SET enabled = 1,
                verify_channel_id = ?,
                unverified_role_id = ?,
                verified_role_id = ?,
                message_id = ?
            WHERE guild_id = ?
            """,
            (
                channel.id,
                unverified_role.id,
                verified_role.id,
                message.id,
                guild.id,
            ),
        )

        self.db.commit()

        description = (
            "Verification has been set up successfully.\n\n"
            f"**Verification channel:** {channel.mention}\n"
            f"**Unverified role:** {unverified_role.mention}\n"
            f"**Verified role:** {verified_role.mention}\n\n"
            "All other channels have been hidden from "
            "the Unverified role."
        )

        if failed_channels:
            description += (
                f"\n\n⚠️ I couldn't configure "
                f"**{failed_channels}** channel"
                f"{'' if failed_channels == 1 else 's'}."
            )

        await interaction.followup.send(
            embed=self.success_embed(
                description
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="enable",
        description="Enable server verification",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def enable(
        self,
        interaction: discord.Interaction,
    ):
        config = self.get_config(
            interaction.guild.id
        )

        if not config or not config["verify_channel_id"]:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Verification hasn't been set up yet.\n\n"
                    "Run `/verification 1 setup` first."
                ),
                ephemeral=True,
            )
            return

        self.db.execute(
            """
            UPDATE verification
            SET enabled = 1
            WHERE guild_id = ?
            """,
            (interaction.guild.id,),
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "Server verification has been enabled."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="disable",
        description="Disable server verification",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def disable(
        self,
        interaction: discord.Interaction,
    ):
        self.db.execute(
            """
            UPDATE verification
            SET enabled = 0
            WHERE guild_id = ?
            """,
            (interaction.guild.id,),
        )

        self.db.execute(
            """
            DELETE FROM captcha
            WHERE guild_id = ?
            """,
            (interaction.guild.id,),
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "Server verification has been disabled."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="config",
        description="View verification configuration",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def config(
        self,
        interaction: discord.Interaction,
    ):
        config = self.get_config(
            interaction.guild.id
        )

        if not config:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Verification has not been configured."
                ),
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(
            config["verify_channel_id"]
        )

        unverified = interaction.guild.get_role(
            config["unverified_role_id"]
        )

        verified = interaction.guild.get_role(
            config["verified_role_id"]
        )

        embed = discord.Embed(
            title="🔐 Verification Configuration",
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
            name="Channel",
            value=(
                channel.mention
                if channel
                else "`Missing`"
            ),
            inline=True,
        )

        embed.add_field(
            name="Message",
            value=(
                f"`{config['message_id']}`"
                if config["message_id"]
                else "`Missing`"
            ),
            inline=True,
        )

        embed.add_field(
            name="Unverified Role",
            value=(
                unverified.mention
                if unverified
                else "`Missing`"
            ),
            inline=True,
        )

        embed.add_field(
            name="Verified Role",
            value=(
                verified.mention
                if verified
                else "`Missing`"
            ),
            inline=True,
        )

        embed.add_field(
            name="CAPTCHA",
            value=(
                "6 characters\n"
                "5 attempts\n"
                "5 minute expiry"
            ),
            inline=True,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="regenerate",
        description="Regenerate the verification message",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def regenerate(
        self,
        interaction: discord.Interaction,
    ):
        config = self.get_config(
            interaction.guild.id
        )

        if not config or not config["verify_channel_id"]:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Verification hasn't been set up yet."
                ),
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(
            config["verify_channel_id"]
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                embed=self.error_embed(
                    "The configured verification channel "
                    "no longer exists."
                ),
                ephemeral=True,
            )
            return

        if config["message_id"]:
            try:
                old_message = await channel.fetch_message(
                    config["message_id"]
                )

                await old_message.delete()

            except discord.NotFound:
                pass

            except (
                discord.Forbidden,
                discord.HTTPException,
            ):
                pass

        try:
            message = await channel.send(
                embed=self.verification_embed(),
                view=VerifyView(self),
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "I don't have permission to send messages "
                    "in the verification channel."
                ),
                ephemeral=True,
            )
            return

        self.db.execute(
            """
            UPDATE verification
            SET message_id = ?
            WHERE guild_id = ?
            """,
            (
                message.id,
                interaction.guild.id,
            ),
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "The verification message has been regenerated."
            ),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member,
    ):
        config = self.get_config(
            member.guild.id
        )

        if not config or not config["enabled"]:
            return

        role = member.guild.get_role(
            config["unverified_role_id"]
        )

        if not role:
            return

        try:
            await member.add_roles(
                role,
                reason="Crumb verification requirement",
            )

        except (
            discord.Forbidden,
            discord.HTTPException,
        ):
            pass

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

        else:
            message = (
                "Something went wrong while running "
                "that command."
            )

        embed = self.error_embed(message)

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
        Verification(bot)
    )