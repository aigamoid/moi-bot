import os

from dotenv import load_dotenv
import discord

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    if "もい" in message.content:
        await message.reply("もい")
        await message.add_reaction("🦆")


client.run(os.environ["DISCORD_TOKEN"])
