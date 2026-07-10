import discord
from discord import app_commands
from discord.ext import commands
from utils.database import Database

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
    
    @commands.hybrid_command(name='help', description='Показать список всех команд для пользователей')
    async def help_command(self, ctx):
        try:
            settings = self.db.get_server_settings(ctx.guild.id)
            prefix = settings[8] if settings else '!'
            
            embed = discord.Embed(
                title="🎮 Помощь по командам бота (для пользователей)",
                description=f"Префикс команд: `{prefix}`\nТакже доступны слэш-команды (/)",
                color=0x3498db
            )
            
            # Экономика (только пользовательские команды)
            embed.add_field(
                name="💼 Экономика",
                value=f"""
`{prefix}work` - Заработать монеты
`{prefix}balance [@user]` - Посмотреть баланс
`{prefix}slots <ставка>` - Игра в слот-машину
`{prefix}transfer @user <сумма>` - Перевести деньги
`{prefix}leaderboardec` - Топ по балансу
`{prefix}rob @user [сумма]` - Попытаться ограбить пользователя
`{prefix}robstats [@user]` - Статистика ограблений
`{prefix}robleaderboard [тип]` - Топ воришек (profit, success, net, rate)
""",
                inline=False
            )

            # Уровни (только пользовательские команды)
            embed.add_field(
                name="🏆 Уровни и Награды",
                value=f"""
`{prefix}level [@user]` - Посмотреть уровень
`{prefix}leaderboardlv` - Топ по уровням
`{prefix}rank [@user]` - Детальная карточка профиля
`{prefix}levelreward info <уровень>` - Информация о награде
""",
                inline=False
            )
            
            # Кланы (только пользовательские команды)
            embed.add_field(
                name="🏰 Кланы",
                value=f"""
`{prefix}clan create <название> <описание> [тип] [префикс]` - Создать клан
`{prefix}clan info [название]` - Информация о клане
`{prefix}clan join <название/код>` - Вступить в клан
`{prefix}clan leave` - Покинуть клан
`{prefix}clan deposit <сумма>` - Внести деньги в банк клана
`{prefix}clan members` - Список участников клана
`{prefix}clan list [страница]` - Список всех кланов сервера
`{prefix}clan lb [тип] [страница]` - Топ кланов (bank - по банку, members - по участникам)
`{prefix}clan stats [название/ID]` - Детальная статистика клана
`{prefix}clan xp [название/ID]` - Информация об опыте и уровне
`{prefix}clan memberstats @участник` - Статистика участника клана
`{prefix}clan xp_events [дни] [страница]` - История получения опыта
`{prefix}clan lb level [страница]` - Топ кланов по уровню
`{prefix}clan lb xp [страница]` - Топ кланов по опыту
""",
                inline=False
            )
            
            # Достижения и баннеры (только пользовательские команды)
            embed.add_field(
                name="🏆 Достижения и Баннеры",
                value=f"""
`{prefix}achievements` - Список всех достижений сервера
`{prefix}achievement <ID_достижения>` - Информация о достижении
`{prefix}profile [@user]` - Профиль с баннером и достижениями
`{prefix}banners` - Посмотреть все баннеры
`{prefix}bannershop [страница]` - Магазин баннеров
`{prefix}setbanner <ID_баннера>` - Установить активный баннер
""",
                inline=False
            )
            
            # Магазин (только пользовательские команды)
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
""",
                inline=False
            )
            
            # Тикеты (только пользовательские команды)
            embed.add_field(
                name="🎫 Система тикетов",
                value=f"""
`{prefix}ticket create <тип> <описание>` - Создать тикет
`{prefix}ticket close` - Закрыть тикет (в канале тикета)
`{prefix}ticket add @user` - Добавить пользователя в тикет
`{prefix}ticket remove @user` - Удалить пользователя из тикетов
""",
                inline=False
            )

            # Приватные комнаты (только пользовательские команды)
            embed.add_field(
                name="🔒 Приватные комнаты",
                value=f"""
`{prefix}roominfo` - Информация о вашей приватной комнате
""",
                inline=False
            )
            
            # Дополнительные команды
            embed.add_field(
                name="✨ Дополнительные команды",
                value=f"""
`{prefix}help` - Показать это сообщение
`/help` - Тоже самое (слеш-команда)
`{prefix}ping` - Проверить задержку бота
`{prefix}uptime` - Время работы бота
""",
                inline=False
            )
            
            # Информация об админских командах
            embed.add_field(
                name="⚙️ Административные команды",
                value=f"Для администраторов доступны дополнительные команды. Используйте `{prefix}settings help` для просмотра всех административных команд и настроек.",
                inline=False
            )
            
            embed.set_footer(text="Бот для Светогорска • [] - необязательный параметр, <> - обязательный параметр")
            
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"❌ Ошибка в команде help: {e}")
            await ctx.send("❌ Произошла ошибка при выполнении команды.")

async def setup(bot):
    await bot.add_cog(Help(bot))