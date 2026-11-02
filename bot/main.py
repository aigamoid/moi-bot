import os

from dotenv import load_dotenv
import discord

from bot.responder import MoiResponder


def create_client(responder=None):
    intents = discord.Intents.default()
    intents.message_content = True
    # discord.py supports a minimum of 30 seconds for this setting. Our own
    # per-action deadline is shorter and also covers network/API stalls.
    client = discord.Client(intents=intents, max_ratelimit_timeout=30.0)
    responder = responder if responder is not None else MoiResponder()

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user} (ID: {client.user.id})")

    @client.event
    async def on_message(message):
        await responder.on_message(message)

    return client


def main():
    load_dotenv(override=False)
    create_client().run(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    main()
