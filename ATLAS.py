import os
import json
import requests
import discord
from discord.ext import commands, tasks
from datetime import datetime, time, timedelta

# Load configuration from config.json
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# Get constants from configuration
WEATHERBIT_HOMETOWN = config["WEATHERBIT_HOMETOWN"]
WEATHERBIT_API_KEY = config["WEATHERBIT_API_KEY"]
DISCORD_CHANNEL_ID = config["DISCORD_CHANNEL_ID"]
DISCORD_BOT_TOKEN = config["DISCORD_BOT_TOKEN"]

# Bot setup
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Bin reminder class
class BinReminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.initial_date = datetime(2024, 6, 4)  # Starting date to align with the correct schedule
        self.glass_start_date = datetime(2024, 6, 18)  # Starting date for the glass bin schedule

    def determine_bins(self, for_next_week=False):
        print("Determining bins for the week")
        today = datetime.today()
        print(f"Today is {today}")

        if for_next_week or today.weekday() > 1:  # For next week or if today is after Tuesday
            next_tuesday = today + timedelta((1 - today.weekday() + 7) % 7)
            target_day = next_tuesday
        else:  # For this week's Tuesday
            target_day = today + timedelta((1 - today.weekday()) % 7)

        print(f"Target day for bin determination: {target_day}")

        days_since_initial = (target_day - self.initial_date).days
        days_since_glass_start = (target_day - self.glass_start_date).days
        week_num = days_since_initial // 7

        organics = True
        recycling = week_num % 2 == 0  # Fortnightly
        landfill = not recycling  # Alternates with recycling
        glass = days_since_glass_start % 28 == 0  # Every 4 weeks (28 days)

        bins_out = []
        if organics:
            bins_out.append("Organics (Green Lid)")
        if recycling:
            bins_out.append("Recycling (Yellow Lid)")
        if landfill:
            bins_out.append("Landfill (Red Lid)")
        if glass:
            bins_out.append("Glass (Purple Lid)")

        print(f"Bins out this week: {bins_out}")
        return bins_out

    async def send_bin_reminder(self):
        bins_out = self.determine_bins()
        if bins_out:
            bins_str = ", ".join(bins_out)
            channel = self.bot.get_channel(DISCORD_CHANNEL_ID)
            if channel is not None:
                print(f"Sending bin reminder to channel {DISCORD_CHANNEL_ID}")
                await channel.send(f"Quick reminder, the following bins are scheduled for this week: {bins_str}")
            else:
                print(f"Channel {DISCORD_CHANNEL_ID} not found")
        else:
            print("No bins to remind for this week.")

    async def send_next_week_bin_reminder(self):
        bins_out = self.determine_bins(for_next_week=True)
        if bins_out:
            bins_str = ", ".join(bins_out)
            channel = self.bot.get_channel(DISCORD_CHANNEL_ID)
            if channel is not None:
                print(f"Sending bin reminder for next week to channel {DISCORD_CHANNEL_ID}")
                await channel.send(f"Quick reminder, the following bins are scheduled for next week: {bins_str}")
            else:
                print(f"Channel {DISCORD_CHANNEL_ID} not found")
        else:
            print("No bins to remind for next week.")

    @tasks.loop(minutes=30)
    async def check_bin_reminder(self):
        now = datetime.now()
        if now.weekday() == 0 and now.hour >= 20:  # Monday after 8pm
            bins_out = self.determine_bins()
            if bins_out:
                bins_str = ", ".join(bins_out)
                channel = self.bot.get_channel(DISCORD_CHANNEL_ID)
                if channel is not None:
                    print(f"Sending Monday night bin reminder to channel {DISCORD_CHANNEL_ID}")
                    await channel.send(f"@nodondisc, remember to take out the following bins tonight: {bins_str}")
                else:
                    print(f"Channel {DISCORD_CHANNEL_ID} not found")
            else:
                print("No bins to remind for tonight.")
        else:
            print("It's not Monday after 8pm. No reminder needed.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.content.lower() == "done":
            # Stop reminders for the current Monday night
            self.check_bin_reminder.cancel()
            await message.channel.send("Great! You've taken out the bins.")

# Weather report class using Weatherbit API
class WeatherReport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @tasks.loop(hours=24)
    async def daily_weather_report(self):
        await self.bot.wait_until_ready()
        await self.send_weather_report()

    async def send_weather_report(self):
        forecast = self.get_weather_forecast()
        channel = self.bot.get_channel(DISCORD_CHANNEL_ID)
        if channel is not None:
            print(f"Sending weather report to channel {DISCORD_CHANNEL_ID}")
            await channel.send(f"Daily Weather: {forecast}")
        else:
            print(f"Channel {DISCORD_CHANNEL_ID} not found")

    def get_weather_forecast(self):
        try:
            response = requests.get(f"https://api.weatherbit.io/v2.0/forecast/daily?city={WEATHERBIT_HOMETOWN}&key={WEATHERBIT_API_KEY}&days=1")
            data = response.json()
            print(f"Weather API response: {data}")
            weather_data = data["data"][0]
            sunrise = datetime.fromtimestamp(weather_data['sunrise_ts']).strftime('%H:%M')
            sunset = datetime.fromtimestamp(weather_data['sunset_ts']).strftime('%H:%M')
            forecast = (
                f"{weather_data['weather']['description']}\n"
                f"High: {weather_data['high_temp']}°C\n"
                f"Low: {weather_data['low_temp']}°C\n"
                f"UV Index: {weather_data['uv']}\n"
                f"Sunrise: {sunrise}\n"
                f"Sunset: {sunset}"
            )
            print(f"Forecast retrieved: {forecast}")
            return forecast
        except KeyError as e:
            print(f"KeyError retrieving weather forecast: {e}")
            return "Unable to retrieve weather forecast."
        except Exception as e:
            print(f"Error retrieving weather forecast: {e}")
            return "Unable to retrieve weather forecast."

# Event listener to start tasks when bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    bin_reminder = bot.get_cog('BinReminder')
    weather_report = bot.get_cog('WeatherReport')
    
    bin_reminder.check_bin_reminder.start()
    weather_report.daily_weather_report.change_interval(time=time(hour=6, minute=0))
    weather_report.daily_weather_report.start()

    # Post the weather and bin reminder when the bot starts
    print("Sending initial weather report and bin reminder")
    await weather_report.send_weather_report()
    
    if datetime.today().weekday() > 1:
        await bin_reminder.send_next_week_bin_reminder()
    else:
        await bin_reminder.send_bin_reminder()

# Adding all cogs to the bot
async def main():
    await bot.add_cog(BinReminder(bot))
    await bot.add_cog(WeatherReport(bot))
    await bot.start(DISCORD_BOT_TOKEN)

import asyncio
asyncio.run(main())
