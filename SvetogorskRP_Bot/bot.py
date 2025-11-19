import discord
from discord.ext import commands
import os
import sys
import asyncio

# Добавляем пути для импортов
sys.path.append('/opt/render/project/src')
sys.path.append('/opt/render/project/src/cogs')
sys.path.append('/opt/render/project/src/utils')

try:
    from utils.database import Database
    print("✅ Database импортирован")
except ImportError as e:
    print(f"❌ Ошибка импорта Database: {e}")

intents = discord.Intents.all()
intents.message_content = True

async def get_prefix(bot, message):
    if not message.guild:
        return '!'
    
    try:
        db = Database()
        settings = db.get_server_settings(message.guild.id)
        return settings[8] if settings else '!'
    except:
        return '!'

class RenderBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=get_prefix, 
            intents=intents, 
            help_command=None,
            max_messages=1000
        )
        
    async def setup_hook(self):
        print("🔄 Начинаю загрузку когов...")
        
        cogs = [
            'cogs.economy',
            'cogs.levels', 
            'cogs.moderation',
            'cogs.settings',
            'cogs.logs',
            'cogs.giveaway',
            'cogs.shop',
            'cogs.tickets'
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f'✅ Загружен ког: {cog}')
            except Exception as e:
                print(f'❌ Ошибка загрузки {cog}: {e}')

bot = RenderBot()

@bot.event
async def on_ready():
    print('=' * 50)
    print(f'✅ Бот {bot.user.name} запущен на Render!')
    print('🌐 Хостинг: Render.com (24/7)')
    print('💻 Память оптимизирована')
    print('=' * 50)
    
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="Render 🚀"
    )
    await bot.change_presence(activity=activity)

@bot.event
async def on_guild_join(guild):
    print(f'✅ Бот добавлен на сервер: {guild.name}')

@bot.event
async def on_guild_remove(guild):
    print(f'🗑️ Бот удален с сервера: {guild.name}')

@bot.command(name='ping')
async def ping(ctx):
    """Проверить пинг бота"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Понг! {latency}ms')

@bot.command(name='status')
async def status(ctx):
    """Статус бота"""
    embed = discord.Embed(title="📊 Статус бота", color=0x00ff00)
    embed.add_field(name="🏓 Пинг", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="🌐 Хостинг", value="Render.com", inline=True)
    embed.add_field(name="👥 Серверов", value=len(bot.guilds), inline=True)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    print("🚀 Запуск бота на Render...")
    print(f"Токен: {'установлен' if os.environ.get('DISCORD_TOKEN') else 'НЕ НАЙДЕН!'}")
    
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print("❌ ОШИБКА: DISCORD_TOKEN не найден!")
        print("Добавь переменную в Render Dashboard → Environment Variables")
    else:
        try:
            bot.run(token)
        except Exception as e:
            print(f"❌ Ошибка запуска: {e}")
