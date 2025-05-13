import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed, ButtonStyle
from discord.ui import View, button
import pyotp
import json
import qrcode
from io import BytesIO

with open("config.json") as f:
    config = json.load(f)

TOKEN = config["token"]
GUILD_ID = int(config["guild_id"])
ROLE_ID = int(config["role_id"])
ISSUER = config["issuer"]
BOT_NAME = config["bot_name"]

try:
    with open("verified_users.json") as f:
        verified_users = set(json.load(f))
except FileNotFoundError:
    verified_users = set()

def save_verified_users():
    with open("verified_users.json", "w") as f:
        json.dump(list(verified_users), f)

intents = discord.Intents.default()
intents.members = True
intents.dm_messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

user_secrets = {}

def generate_totp_qr(user_id: int):
    secret = pyotp.random_base32()
    user_secrets[str(user_id)] = secret

    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=str(user_id), issuer_name=ISSUER)
    img = qrcode.make(uri)

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer

class VerifyView(View):
    @button(label="✅ Verify", style=ButtonStyle.green)
    async def verify_button(self, interaction: Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)

        if user_id in verified_users:
            await interaction.response.send_message("✅ You are already verified.", ephemeral=True)
            return

        qr_image = generate_totp_qr(interaction.user.id)
        file = discord.File(qr_image, filename="qrcode.png")

        try:
            await interaction.user.send(
                content="📱 Scan this QR code with Google Authenticator (or any TOTP app), then reply with the 6-digit code.",
                file=file
            )
            await interaction.response.send_message("📬 Check your DMs for the QR code!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I can't DM you. Please enable DMs and try again.", ephemeral=True)

@tree.command(name="verifychannel", description="Send the verification embed with button.")
@app_commands.checks.has_permissions(administrator=True)
async def verify_channel(interaction: Interaction):
    embed = Embed(
        title="🔐 Verification Required",
        description="Click the button below to verify using Google Authenticator.",
        color=discord.Color.blurple()
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("✅ Verification panel sent.", ephemeral=True)

@bot.event
async def on_message(message):
    if message.guild is None and not message.author.bot:
        user_id = str(message.author.id)

        if user_id in verified_users:
            await message.channel.send("✅ You are already verified.")
            return

        if user_id not in user_secrets:
            await message.channel.send("❌ You haven't started verification. Use the `/verifychannel` first.")
            return

        code = message.content.strip()
        totp = pyotp.TOTP(user_secrets[user_id])

        if totp.verify(code):
            guild = bot.get_guild(GUILD_ID)
            role = guild.get_role(ROLE_ID)
            member = guild.get_member(int(user_id))

            if member:
                await member.add_roles(role)
                verified_users.add(user_id)
                save_verified_users()
                await message.channel.send("✅ Verification successful! You've been given the verified role.")
            else:
                await message.channel.send("❌ Could not find you in the server.")
        else:
            await message.channel.send("❌ Invalid code. Try again.")

@bot.event
async def on_ready():
    await tree.sync()
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")
    print("[INFO] Slash commands synced globally.")

bot.run(TOKEN)
