import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from utils.database import Database

load_dotenv()

intents = discord.Intents.all()
intents.message_content = True

async def get_prefix(bot, message):
    if not message.guild:
        return '!'
    
    db = Database()
    settings = db.get_server_settings(message.guild.id)
    return settings[8] if settings else '!'

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} запущен!')
    
    cogs = [
        'cogs.economy',
        'cogs.levels', 
        'cogs.moderation',
        'cogs.settings',
        'cogs.logs',
        'cogs.giveaway',
        'cogs.shop',
        'cogs.tickets'  # Добавляем тикеты
    ]
    
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f'✅ Загружен ког: {cog}')
        except Exception as e:
            print(f'❌ Ошибка загрузки {cog}: {e}')
    
    activity = discord.Activity(
        type=discord.ActivityType.playing, 
        name="Строит Светогорск"
    )
    await bot.change_presence(activity=activity)
    print('🎮 Активность установлена!')

@bot.event
async def on_guild_join(guild):
    """При добавлении бота на сервер"""
    print(f'✅ Бот добавлен на сервер: {guild.name} (ID: {guild.id})')
    
    # Создаем настройки по умолчанию для нового сервера
    db = Database()
    db.get_server_settings(guild.id)  # Это создаст настройки по умолчанию

@bot.event
async def on_guild_remove(guild):
    """При удалении бота с сервера"""
    print(f'🗑️ Бот удален с сервера: {guild.name} (ID: {guild.id})')
    
    # Очищаем данные сервера из базы
    db = Database()
    db.cleanup_guild_data(guild.id)
    print(f'✅ Данные сервера {guild.name} очищены из базы')

@bot.command(name='help')
async def help_command(ctx):
    try:
        db = Database()
        settings = db.get_server_settings(ctx.guild.id)
        prefix = settings[8] if settings else '!'
        
        embed = discord.Embed(
            title="🎮 Помощь по командам бота",
            description=f"Префикс команд: `{prefix}`",
            color=0x3498db
        )
        
        embed.add_field(
            name="💼 Экономика",
            value=f"""
`{prefix}work` - Заработать монеты
`{prefix}balance [@user]` - Посмотреть баланс
`{prefix}slots <ставка>` - Игра в слот-машину
`{prefix}transfer @user <сумма>` - Перевести деньги
`{prefix}leaderboardec` - Топ по балансу
`{prefix}addec @user <сумма>` - Выдать монеты (админ)
`{prefix}removeec @user <сумма>` - Забрать монеты (админ)
`{prefix}setbalance @user <сумма>` - Установить баланс (админ)
""",
            inline=False
        )
        
        embed.add_field(
            name="🏆 Уровни и Награды",
            value=f"""
`{prefix}level [@user]` - Посмотреть уровень
`{prefix}leaderboardlv` - Топ по уровням
`{prefix}rank [@user]` - Детальная карточка профиля
`{prefix}levelreward set <уровень> <тип> [роль] [валюта]` - Установить награду (админ)
`{prefix}levelreward remove <уровень>` - Удалить награду (админ)
`{prefix}levelreward list` - Список наград (админ)
`{prefix}levelreward info <уровень>` - Информация о награде
`{prefix}setxp @user <опыт>` - Установить опыт (админ)
`{prefix}setlevel @user <уровень>` - Установить уровень (админ)
""",
            inline=False
        )
        
        embed.add_field(
            name="🛍️ Магазин и Торговля",
            value=f"""
`{prefix}shop [страница]` - Показать магазин
`{prefix}buy <ID_предмета>` - Купить предмет из магазина
`{prefix}inventory [@user]` - Посмотреть инвентарь
`{prefix}iteminfo <ID_предмета>` - Информация о предмете
`{prefix}market [страница]` - Торговая площадка
`{prefix}market sell <ID_предмета> <цена>` - Выставить предмет на продажу
`{prefix}market buy <ID_предложения>` - Купить предмет с площадки
`{prefix}market my` - Мои предложения
`{prefix}market remove <ID_предложения>` - Убрать предложение
`{prefix}transactions [лимит]` - История транзакций
`{prefix}additem <название> <цена> <тип> [лимит] <описание>` - Добавить предмет (админ)
`{prefix}addroleitem <название> <цена> @роль [время] [лимит] <описание>` - Добавить роль (админ)
`{prefix}deleteitem <ID_предмета>` - Удалить предмет (админ)
`{prefix}clearinventory @user` - Очистить инвентарь (админ)
""",
            inline=False
        )
        
        embed.add_field(
            name="🎫 Система тикетов",
            value=f"""
`{prefix}ticket create <тип> <описание>` - Создать тикет
`{prefix}ticket close` - Закрыть тикет (в канале тикета)
`{prefix}ticket add @user` - Добавить пользователя в тикет
`{prefix}ticket remove @user` - Удалить пользователя из тикета
`{prefix}ticket list` - Список активных тикетов (админ)
""",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Модерация",
            value=f"""
`{prefix}warn @user [причина]` - Выдать предупреждение
`{prefix}warnings @user` - Посмотреть предупреждения
`{prefix}clearwarns @user` - Очистить предупреждения
`{prefix}mute @user <время> [причина]` - Заглушить пользователя
`{prefix}unmute @user [причина]` - Снять мут
`{prefix}kick @user [причина]` - Кикнуть пользователя
`{prefix}ban @user [причина]` - Забанить пользователя
`{prefix}unban @user` - Разбанить пользователя
`{prefix}clear <количество>` - Очистить сообщения
""",
            inline=False
        )
        
        embed.add_field(
            name="🎉 Розыгрыши",
            value=f"""
`{prefix}giveaway <время> <победители> <приз>` - Запустить розыгрыш
`{prefix}glist` - Список активных розыгрышей
`{prefix}greroll <id_сообщения>` - Перевыбрать победителей
`{prefix}gend <id_сообщения>` - Завершить розыгрыш досрочно
""",
            inline=False
        )
        
        embed.add_field(
            name="🔧 Настройки (админ)",
            value=f"""
`{prefix}settings` - Показать текущие настройки
`{prefix}settings help` - Помощь по настройкам
`{prefix}settings work_min <число>` - Мин. награда за work
`{prefix}settings work_max <число>` - Макс. награда за work
`{prefix}settings work_cooldown <секунды>` - Кулдаун work
`{prefix}settings xp_message <число>` - Опыт за сообщение
`{prefix}settings xp_voice <число>` - Опыт за голосовую активность
`{prefix}settings slot_min <число>` - Мин. ставка в slots
`{prefix}settings slot_max <число>` - Макс. ставка в slots
`{prefix}settings prefix <префикс>` - Изменить префикс команд
`{prefix}settings logs on/off` - Включить/выключить логи
`{prefix}settings log_channel #канал` - Установить канал для логов
`{prefix}settings role_group <группа> @роль` - Назначить роль группе
`{prefix}settings role_multiplier <economy/xp> @роль <множитель>` - Множитель для роли
`{prefix}settings level_reward <уровень> <тип> [роль] [валюта]` - Награда за уровень
`{prefix}settings ticket group <тип> @роль` - Настроить тикеты
`{prefix}resetwork` - Сбросить настройки work
`{prefix}setmultiplier @роль <economy/xp> <множитель>` - Установить множитель
""",
            inline=False
        )
        
        embed.set_footer(text="Бот для Светогорска • [] - необязательный параметр, <> - обязательный")
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"❌ Ошибка в команде help: {e}")
        await ctx.send("❌ Произошла ошибка при выполнении команды.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"❌ Ошибка команды: {error}")

if __name__ == "__main__":
    try:
        print("🚀 Запуск бота...")
        bot.run(os.getenv('DISCORD_TOKEN'))
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")