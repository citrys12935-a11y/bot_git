import discord
from discord import app_commands
from discord.ext import commands
import os
from utils.database import Database
import asyncio
import time  # <-- добавили для задержки
from utils.setup_achievements import setup_default_achievements, add_default_banner_to_users

# ----- ДОБАВЛЯЕМ ВЕБ-СЕРВЕР ДЛЯ RENDER -----
from keep_alive import keep_alive
# --------------------------------------------

db = Database()

async def safe_db_operation(coro, *args, **kwargs):
    try:
        return await asyncio.get_event_loop().run_in_executor(None, coro, *args, **kwargs)
    except Exception as e:
        print(f"❌ Ошибка БД в асинхронном контексте: {e}")
        return None

intents = discord.Intents.all()
intents.message_content = True

async def get_prefix(bot, message):
    if not message.guild:
        return '!'
    
    settings = db.get_server_settings(message.guild.id)
    return settings[8] if settings else '!'

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            help_command=None
        )
    
    async def setup_hook(self):
        cogs = [
            'cogs.economy',
            'cogs.levels', 
            'cogs.moderation',
            'cogs.settings',
            'cogs.logs',
            'cogs.giveaway',
            'cogs.shop',
            'cogs.tickets',
            'cogs.help',
            'cogs.admin',
            'cogs.private_rooms',
            'cogs.achievements',
            'cogs.clans',
            'cogs.utils'
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f'✅ Загружен ког: {cog}')
            except Exception as e:
                print(f'❌ Ошибка загрузки {cog}: {e}')
        
        await self.sync_commands()

    async def sync_commands(self):
        """Синхронизация слеш-команд"""
        try:
            synced = await self.tree.sync()
            print(f"✅ Синхронизировано {len(synced)} глобальных команд")
            
            for guild in self.guilds:
                try:
                    await self.tree.sync(guild=guild)
                    print(f"✅ Команды синхронизированы для сервера: {guild.name}")
                except Exception as e:
                    print(f"❌ Ошибка синхронизации для {guild.name}: {e}")
                    
        except Exception as e:
            print(f"❌ Ошибка синхронизации команд: {e}")

bot = MyBot()

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} запущен!')
    print(f'📊 На {len(bot.guilds)} серверах')
    
    commands_list = await bot.tree.fetch_commands()
    print(f'\n📋 Зарегистрировано {len(commands_list)} слеш-команд:')
    for cmd in commands_list:
        print(f"  /{cmd.name} - {cmd.description or 'Без описания'}")
    
    activity = discord.Activity(
        type=discord.ActivityType.playing, 
        name="Строит Светогорск"
    )
    await bot.change_presence(activity=activity)

@bot.event
async def on_guild_join(guild):
    """При добавлении бота на сервер"""
    print(f'✅ Бот добавлен на сервер: {guild.name} (ID: {guild.id})')
    
    db = Database()
    db.get_server_settings(guild.id)
    
    try:
        setup_default_achievements(guild.id)
        add_default_banner_to_users(guild.id)
        print(f'✅ Созданы стандартные достижения и баннеры для сервера: {guild.name}')
    except Exception as e:
        print(f'⚠️ Ошибка создания достижений для {guild.name}: {e}')
    
    try:
        await bot.tree.sync(guild=guild)
        print(f'✅ Команды синхронизированы для сервера: {guild.name}')
    except Exception as e:
        print(f'❌ Ошибка синхронизации команд для сервера {guild.name}: {e}')

@bot.event
async def on_guild_remove(guild):
    """При удалении бота с сервера"""
    print(f'🗑️ Бот удален с сервера: {guild.name} (ID: {guild.id})')
    
    db = Database()
    db.cleanup_guild_data(guild.id)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ У вас недостаточно прав для выполнения этой команды!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Не хватает аргументов. Используйте: `{ctx.prefix}help {ctx.command.name}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Неверный аргумент. Используйте: `{ctx.prefix}help {ctx.command.name}`")
    else:
        print(f"❌ Ошибка команды {ctx.command}: {error}")

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(f"❌ У вас недостаточно прав для выполнения этой команды!", ephemeral=True)
    elif isinstance(error, app_commands.CommandNotFound):
        return
    else:
        print(f"❌ Ошибка слеш-команды: {error}")
        await interaction.response.send_message("❌ Произошла ошибка при выполнении команды!", ephemeral=True)

if __name__ == "__main__":
    try:
        print("🚀 Запуск бота...")
        keep_alive()                 # <-- запускаем веб-сервер
        time.sleep(1)                # <-- даём ему время подняться
        bot.run(os.getenv('DISCORD_TOKEN'))
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
