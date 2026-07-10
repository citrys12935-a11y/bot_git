import discord
from discord import app_commands
from discord.ext import commands
from utils.database import Database
import random
import string
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import sqlite3
import math
from collections import defaultdict
from utils.checks import has_permission

class Clans(commands.Cog):
    """Система кланов с опытом и статистикой"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.xp_cooldowns = {}  # Кэш для кд на XP
        self.user_message_cooldowns = {}  # Кэш для сообщений
    
    def generate_join_code(self, length=8):
        """Генерация кода для вступления"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    
    def get_clan_info(self, clan_id, guild_id):
        """Получить информацию о клане"""
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT 
                c.clan_id,               -- 0
                c.guild_id,              -- 1
                c.name,                  -- 2
                c.owner_id,              -- 3
                c.description,           -- 4
                c.clan_type,             -- 5
                c.join_code,             -- 6
                c.prefix,                -- 7
                c.role_id,               -- 8
                c.bank,                  -- 9
                c.created_at,            -- 10
                
                cs.member_role_name,     -- 11
                cs.coowner_role_name,    -- 12
                cs.owner_role_name,      -- 13
                
                cx.level,                -- 14
                cx.xp,                   -- 15
                cx.total_xp_earned       -- 16
            FROM clans c
            LEFT JOIN clan_settings cs ON c.clan_id = cs.clan_id
            LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
            WHERE c.clan_id = ? AND c.guild_id = ?
        ''', (clan_id, guild_id))
        result = cursor.fetchone()
        return result
    
    def get_user_clan(self, user_id, guild_id):
        """Получить клан пользователя"""
        cursor = self.db.conn.cursor()
        try:
            cursor.execute('''
                SELECT cm.user_id, cm.guild_id, cm.clan_id, cm.role, cm.joined_at,
                       c.name, c.owner_id, c.clan_type, c.bank, c.join_code,
                       cx.level, cx.xp
                FROM clan_members cm
                JOIN clans c ON cm.clan_id = c.clan_id
                LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                WHERE cm.user_id = ? AND cm.guild_id = ?
            ''', (user_id, guild_id))
            result = cursor.fetchone()
            return result
        except sqlite3.Error as e:
            print(f"❌ Ошибка получения клана пользователя: {e}")
            return None
    
    def get_clan_members(self, clan_id):
        """Получить всех участников клана"""
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT cm.user_id, cm.role, cm.joined_at,
                   cms.total_deposited, cms.xp_contributed
            FROM clan_members cm
            LEFT JOIN clan_member_stats cms ON cm.user_id = cms.user_id AND cm.clan_id = cms.clan_id
            WHERE cm.clan_id = ?
            ORDER BY 
                CASE cm.role
                    WHEN 'owner' THEN 1
                    WHEN 'coowner' THEN 2
                    ELSE 3
                END,
                cms.total_deposited DESC
        ''', (clan_id,))
        return cursor.fetchall()
    
    async def add_clan_xp(self, clan_id, xp_amount, user_id=None, event_type="other", details=""):
        """Добавить опыт клану"""
        new_level, reward = self.db.add_clan_xp(clan_id, xp_amount, user_id, event_type, details)
        
        # Если пользователь указан, обновляем его вклад в XP
        if user_id:
            cursor = self.db.conn.cursor()
            cursor.execute('''
                SELECT guild_id FROM clan_members 
                WHERE user_id = ? AND clan_id = ?
            ''', (user_id, clan_id))
            result = cursor.fetchone()
            if result:
                guild_id = result[0]
                self.db.update_clan_member_stats(
                    user_id, guild_id, clan_id,
                    xp_contributed=xp_amount,
                    last_active=int(datetime.now().timestamp())
                )
        
        return new_level, reward
    
    async def process_clan_xp_event(self, user_id, guild_id, event_type, xp_amount=0, details=""):
        """Обработать событие для начисления XP клану"""
        user_clan = self.get_user_clan(user_id, guild_id)
        if not user_clan:
            return None
        
        clan_id = user_clan[2]
        
        # Настройки начисления XP за разные события
        xp_settings = {
            "member_join": 100,  # XP за вступление нового участника
            "deposit": 2,  # XP за каждые 100 монет вклада
            "message": 1,  # XP за сообщение (с кд)
            "voice_minute": 0.5,  # XP за минуту в голосовом канале
            "command": 5,  # XP за использование команд бота
            "achievement": 50,  # XP за получение достижения
            "level_up": 100,  # XP за повышение уровня участника
            "daily": 25,  # XP за ежедневную награду
            "work": 10,  # XP за работу
        }
        
        # Если xp_amount не указан, используем настройки
        if xp_amount == 0 and event_type in xp_settings:
            xp_amount = xp_settings[event_type]
        
        # Применяем модификаторы
        if event_type == "deposit" and "amount" in details:
            try:
                amount = int(details.split(":")[1])
                xp_amount = max(1, amount // 50)  # 2 XP за 100 монет, но минимум 1
            except:
                pass
        
        # Проверяем кд для сообщений
        if event_type == "message":
            key = f"{user_id}:{guild_id}:message"
            current_time = datetime.now().timestamp()
            if key in self.user_message_cooldowns:
                last_time = self.user_message_cooldowns[key]
                if current_time - last_time < 60:  # 60 секунд кд
                    return None
            self.user_message_cooldowns[key] = current_time
        
        # Добавляем XP
        return await self.add_clan_xp(clan_id, xp_amount, user_id, event_type, details)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Начисление XP за сообщения"""
        if message.author.bot or not message.guild:
            return
        
        # Игнорируем команды
        if message.content.startswith(tuple(['!', '/', '.', '-'])):
            return
        
        await self.process_clan_xp_event(
            message.author.id, message.guild.id,
            event_type="message",
            details=f"Сообщение в канале {message.channel.name}"
        )
        
        # Обновляем статистику сообщений пользователя
        user_clan = self.get_user_clan(message.author.id, message.guild.id)
        if user_clan:
            self.db.update_clan_member_stats(
                message.author.id, message.guild.id, user_clan[2],
                messages_count=1,
                last_active=int(datetime.now().timestamp())
            )
    
    @commands.hybrid_group(name='clan', description='Команды кланов')
    async def clan_group(self, ctx):
        """Группа команд кланов"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @clan_group.command(name='stats', description='Подробная статистика клана')
    @app_commands.describe(clan='Название или ID клана')
    async def clan_stats(self, ctx, clan: Optional[str] = None):
        """Показать детальную статистику клана"""
        try:
            if clan:
                # Ищем клан по имени или ID
                cursor = self.db.conn.cursor()
                if clan.isdigit():
                    cursor.execute('''
                        SELECT clan_id FROM clans 
                        WHERE guild_id = ? AND clan_id = ?
                    ''', (ctx.guild.id, int(clan)))
                else:
                    cursor.execute('''
                        SELECT clan_id FROM clans 
                        WHERE guild_id = ? AND name LIKE ?
                    ''', (ctx.guild.id, f"%{clan}%"))
                
                result = cursor.fetchone()
                if not result:
                    await ctx.send("❌ Клан не найден!", ephemeral=True)
                    return
                clan_id = result[0]
            else:
                # Статистика своего клана
                user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
                if not user_clan:
                    await ctx.send("❌ Вы не состоите в клане! Укажите название или ID клана.", ephemeral=True)
                    return
                clan_id = user_clan[2]
            
            # Получаем детальную статистику
            clan_stats, member_stats = self.db.get_clan_detailed_stats(clan_id)
            
            if not clan_stats:
                await ctx.send("❌ Статистика клана не найдена!", ephemeral=True)
                return
            
            # Создаем основное embed
            embed = discord.Embed(
                title=f"📊 Детальная статистика клана: {clan_stats[0]}",
                color=0x3498db
            )
            
            # Основная информация
            embed.add_field(
                name="🏆 Уровень и опыт",
                value=f"**Уровень:** {clan_stats[2] or 1}\n"
                      f"**Опыт:** {clan_stats[3] or 0:,}\n"
                      f"**Всего заработано опыта:** {clan_stats[8] or 0:,}",
                inline=True
            )
            
            embed.add_field(
                name="💰 Финансы",
                value=f"**Банк клана:** {clan_stats[1] or 0:,} монет\n"
                      f"**Всего внесено:** {clan_stats[5] or 0:,} монет",
                inline=True
            )
            
            embed.add_field(
                name="👥 Участники",
                value=f"**Всего участников:** {clan_stats[4] or 0}\n"
                      f"**Активных:** {sum(1 for m in member_stats if m[8] and (datetime.now().timestamp() - m[8]) < 86400)}",
                inline=True
            )
            
            # Активность
            embed.add_field(
                name="💬 Активность",
                value=f"**Сообщений:** {clan_stats[6] or 0:,}\n"
                      f"**Голосовых минут:** {clan_stats[7] or 0:,}",
                inline=True
            )
            
            embed.add_field(
                name="📈 Вклад в XP",
                value=f"**Всего вложено в XP:** {clan_stats[8] or 0:,}\n"
                      f"**Средний вклад на участника:** {clan_stats[8] // max(1, clan_stats[4] or 1):,}",
                inline=True
            )
            
            # Время создания клана
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT created_at FROM clans WHERE clan_id = ?', (clan_id,))
            created_at_result = cursor.fetchone()
            if created_at_result and created_at_result[0]:
                created_at_timestamp = created_at_result[0]
                created_date = datetime.fromtimestamp(created_at_timestamp)
                days_exist = (datetime.now() - created_date).days
                embed.add_field(
                    name="📅 Возраст клана",
                    value=f"**Создан:** <t:{created_at_timestamp}:D>\n"
                          f"**Существует:** {days_exist} дней",
                    inline=True
                )
            
            # Топ 5 вкладчиков
            top_depositors = sorted(member_stats, key=lambda x: x[3] or 0, reverse=True)[:5]
            depositors_text = ""
            for i, member in enumerate(top_depositors, 1):
                user = ctx.guild.get_member(member[0])
                name = user.display_name if user else f"Пользователь ({member[0]})"
                amount = member[3] or 0
                depositors_text += f"{i}. **{name[:15]}** - {amount:,} монет\n"
            
            if depositors_text:
                embed.add_field(
                    name="🏅 Топ вкладчиков",
                    value=depositors_text,
                    inline=False
                )
            
            # Топ 5 по вкладу в XP
            top_xp_contributors = sorted(member_stats, key=lambda x: x[7] or 0, reverse=True)[:5]
            xp_text = ""
            for i, member in enumerate(top_xp_contributors, 1):
                user = ctx.guild.get_member(member[0])
                name = user.display_name if user else f"Пользователь ({member[0]})"
                xp = member[7] or 0
                xp_text += f"{i}. **{name[:15]}** - {xp:,} XP\n"
            
            if xp_text:
                embed.add_field(
                    name="🌟 Топ по вкладу в опыт",
                    value=xp_text,
                    inline=False
                )
            
            # Последняя активность
            active_members = [m for m in member_stats if m[8] and (datetime.now().timestamp() - m[8]) < 604800]  # 7 дней
            embed.set_footer(text=f"Активных за неделю: {len(active_members)}/{len(member_stats)}")
            
            await ctx.send(embed=embed)
            
            # Создаем второе embed для детальной статистики участников
            if member_stats:
                member_embed = discord.Embed(
                    title=f"👥 Детальная статистика участников клана {clan_stats[0]}",
                    color=0x2ecc71
                )
                
                # Группируем по ролям
                roles = {'owner': [], 'coowner': [], 'member': []}
                for member in member_stats:
                    role = member[1]
                    if role in roles:
                        roles[role].append(member)
                
                for role_name, members in roles.items():
                    if not members:
                        continue
                    
                    role_display = {
                        'owner': '👑 Владельцы',
                        'coowner': '👥 Совладельцы',
                        'member': '👤 Участники'
                    }[role_name]
                    
                    members_text = ""
                    for member in members[:10]:  # Ограничиваем 10 участниками на роль
                        user = ctx.guild.get_member(member[0])
                        name = user.display_name if user else f"ID: {member[0]}"
                        
                        # Форматируем дату вступления
                        join_date = f"<t:{member[2]}:D>" if member[2] else "Неизвестно"
                        
                        # Форматируем последнюю активность
                        last_active = f"<t:{int(member[8])}:R>" if member[8] else "Неактивен"
                        
                        members_text += (
                            f"**{name[:20]}**\n"
                            f"• Внесено: **{member[3] or 0:,}** монет\n"
                            f"• Вклад в XP: **{member[7] or 0:,}**\n"
                            f"• Вступил: {join_date}\n"
                            f"• Активен: {last_active}\n"
                        )
                    
                    if members_text:
                        member_embed.add_field(
                            name=f"{role_display} ({len(members)})",
                            value=members_text,
                            inline=True
                        )
                
                if len(member_stats) > 30:
                    member_embed.set_footer(text=f"Показано 30 из {len(member_stats)} участников")
                
                await ctx.send(embed=member_embed)
            
        except Exception as e:
            print(f"❌ Ошибка в clan_stats: {e}")
            await ctx.send(f"❌ Ошибка при получении статистики: {str(e)[:200]}", ephemeral=True)
    
    @clan_group.command(name='xp', description='Информация об опыте и уровне клана')
    @app_commands.describe(clan='Название или ID клана (необязательно)')
    async def clan_xp_info(self, ctx, clan: Optional[str] = None):
        """Информация об опыте и уровне клана"""
        try:
            if clan:
                # Ищем клан по имени или ID
                cursor = self.db.conn.cursor()
                if clan.isdigit():
                    cursor.execute('''
                        SELECT clan_id FROM clans 
                        WHERE guild_id = ? AND clan_id = ?
                    ''', (ctx.guild.id, int(clan)))
                else:
                    cursor.execute('''
                        SELECT clan_id FROM clans 
                        WHERE guild_id = ? AND name LIKE ?
                    ''', (ctx.guild.id, f"%{clan}%"))
                
                result = cursor.fetchone()
                if not result:
                    await ctx.send("❌ Клан не найден!", ephemeral=True)
                    return
                clan_id = int(result[0])
            else:
                # Информация о своем клане
                user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
                if not user_clan:
                    await ctx.send("❌ Вы не состоите в клане! Укажите название или ID клана.", ephemeral=True)
                    return
                clan_id = int(user_clan[2])
            
            # Получаем информацию об опыте
            xp_info = self.get_clan_info(clan_id, ctx.guild.id)
            if not xp_info:
                await ctx.send("❌ Информация об опыте клана не найдена!", ephemeral=True)
                return
            
            # Безопасное получение данных с правильными индексами
            clan_name = xp_info[2] if len(xp_info) > 2 and xp_info[2] else "Неизвестно"
            current_level = xp_info[14] if len(xp_info) > 14 and xp_info[14] is not None else 1
            current_xp = xp_info[15] if len(xp_info) > 15 and xp_info[15] is not None else 0
            
            # Преобразуем в int
            try:
                current_level = int(current_level)
            except (ValueError, TypeError):
                current_level = 1
                
            try:
                current_xp = int(current_xp)
            except (ValueError, TypeError):
                current_xp = 0
            
            # Рассчитываем XP для следующего уровня
            xp_for_next_level = ((current_level + 1) ** 2) * 100
            xp_for_current_level = (current_level ** 2) * 100
            xp_needed = max(0, xp_for_next_level - current_xp)
            
            progress = 0
            if xp_for_next_level > xp_for_current_level:
                progress = ((current_xp - xp_for_current_level) / 
                           max(1, (xp_for_next_level - xp_for_current_level))) * 100
            
            # Получаем историю набора XP
            xp_history = self.db.get_clan_xp_history(clan_id, limit=10)
            
            embed = discord.Embed(
                title=f"🏆 Система опыта клана: {clan_name}",
                description=f"**Уровень {current_level}**\n"
                          f"Прогресс до следующего уровня:",
                color=0x9b59b6
            )
            
            # Прогресс бар
            bars = 20
            filled_bars = min(bars, int(progress / 100 * bars))
            progress_bar = "█" * filled_bars + "░" * (bars - filled_bars)
            
            embed.add_field(
                name="📊 Прогресс",
                value=f"```{progress_bar} {progress:.1f}%```\n"
                      f"**{current_xp - xp_for_current_level:,} / {xp_for_next_level - xp_for_current_level:,} XP**\n"
                      f"Всего опыта: **{current_xp:,}**",
                inline=False
            )
            
            embed.add_field(
                name="🎯 Цели",
                value=f"**Текущий уровень:** {current_level}\n"
                      f"**Следующий уровень:** {current_level + 1}\n"
                      f"**Нужно опыта:** {xp_needed:,}",
                inline=True
            )
            
            # Получаем total_xp_earned если есть
            total_xp_earned = xp_info[16] if len(xp_info) > 16 and xp_info[16] is not None else current_xp
            try:
                total_xp_earned = int(total_xp_earned)
            except (ValueError, TypeError):
                total_xp_earned = current_xp
            
            embed.add_field(
                name="📈 Статистика",
                value=f"**Всего заработано:** {total_xp_earned:,} XP\n"
                      f"**Текущий XP:** {current_xp:,} XP",
                inline=True
            )
            
            # Время последнего получения XP (если есть в отдельной таблице)
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT last_xp_gain FROM clan_xp WHERE clan_id = ?', (clan_id,))
            last_xp_result = cursor.fetchone()
            if last_xp_result and last_xp_result[0]:
                try:
                    last_xp_time = int(last_xp_result[0])
                    embed.add_field(
                        name="⏰ Последний XP",
                        value=f"<t:{last_xp_time}:R>",
                        inline=True
                    )
                except (ValueError, TypeError):
                    pass
            
            # Последние события XP
            if xp_history:
                events_text = ""
                for event in xp_history[:5]:
                    if len(event) > 6:
                        event_type = str(event[3]) if event[3] else "other"
                        xp_amount = int(event[4]) if event[4] else 0
                        details = str(event[5]) if event[5] else ""
                        timestamp = int(event[6]) if event[6] else 0
                        
                        # Форматируем тип события
                        type_emojis = {
                            "member_join": "👥",
                            "deposit": "💰",
                            "message": "💬",
                            "voice_minute": "🔊",
                            "command": "⚡",
                            "achievement": "🏆",
                            "level_up": "📈",
                            "daily": "🎁",
                            "work": "💼"
                        }
                        
                        emoji = type_emojis.get(event_type, "✨")
                        time_ago = f"<t:{timestamp}:R>" if timestamp else "Недавно"
                        
                        events_text += f"{emoji} **+{xp_amount} XP** - {details[:30]}... {time_ago}\n"
                
                if events_text:
                    embed.add_field(
                        name="📝 Последние события",
                        value=events_text,
                        inline=False
                    )
            
            # Бонусы за уровень
            level_bonuses = {
                5: "🏆 +5% к наградам за работу",
                10: "💰 +10% к доходам от депозитов",
                15: "💬 +15% XP за сообщения",
                20: "👥 Возможность иметь +5 участников",
                25: "🎁 Ежедневная награда x2",
                30: "👑 Уникальная роль владельца",
                50: "🚀 Легендарный статус клана"
            }
            
            next_bonus_level = min([lvl for lvl in level_bonuses.keys() if lvl > current_level], default=None)
            if next_bonus_level:
                embed.add_field(
                    name="🎁 Следующий бонус",
                    value=f"На **уровне {next_bonus_level}**:\n{level_bonuses[next_bonus_level]}",
                    inline=False
                )
            
            embed.set_footer(text=f"ID клана: {clan_id}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"❌ Ошибка в clan_xp_info: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ Ошибка при получении информации об опыте: {str(e)[:100]}", ephemeral=True)
    
    @clan_group.command(name='leaderboard', aliases=['lb'], description='Топ кланов')
    @app_commands.describe(
        sort_by='Сортировка (bank, members, level, xp)',
        page='Номер страницы'
    )
    async def clan_leaderboard(self, ctx, sort_by: str = 'level', page: int = 1):
        """Топ кланов сервера"""
        if sort_by not in ['bank', 'members', 'level', 'xp']:
            await ctx.send("❌ Неверный параметр сортировки! Доступные: bank, members, level, xp", ephemeral=True)
            return
        
        cursor = self.db.conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM clans WHERE guild_id = ?', (ctx.guild.id,))
        total_clans = cursor.fetchone()[0]
        
        if total_clans == 0:
            await ctx.send("🏰 На этом сервере пока нет кланов.")
            return
        
        items_per_page = 10
        total_pages = max(1, (total_clans + items_per_page - 1) // items_per_page)
        
        if page < 1 or page > total_pages:
            await ctx.send(f"❌ Страница должна быть от 1 до {total_pages}!", ephemeral=True)
            return
        
        offset = (page - 1) * items_per_page
        
        if sort_by == 'bank':
            cursor.execute('''
                SELECT c.clan_id, c.name, c.bank, c.owner_id,
                       COUNT(cm.user_id) as member_count,
                       cx.level, cx.xp
                FROM clans c
                LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
                LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                WHERE c.guild_id = ?
                GROUP BY c.clan_id
                ORDER BY c.bank DESC, cx.level DESC
                LIMIT ? OFFSET ?
            ''', (ctx.guild.id, items_per_page, offset))
            title = "💰 Топ кланов по банку"
            value_template = "💰 **Банк:** {bank} монет\n🏆 **Уровень:** {level}"
            
        elif sort_by == 'members':
            cursor.execute('''
                SELECT c.clan_id, c.name, c.bank, c.owner_id,
                       COUNT(cm.user_id) as member_count,
                       cx.level, cx.xp
                FROM clans c
                LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
                LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                WHERE c.guild_id = ?
                GROUP BY c.clan_id
                ORDER BY member_count DESC, c.bank DESC
                LIMIT ? OFFSET ?
            ''', (ctx.guild.id, items_per_page, offset))
            title = "👥 Топ кланов по участникам"
            value_template = "👥 **Участники:** {member_count}\n🏆 **Уровень:** {level}"
            
        elif sort_by == 'level':
            cursor.execute('''
                SELECT c.clan_id, c.name, c.bank, c.owner_id,
                       COUNT(cm.user_id) as member_count,
                       cx.level, cx.xp
                FROM clans c
                LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
                LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                WHERE c.guild_id = ?
                GROUP BY c.clan_id
                ORDER BY cx.level DESC, cx.xp DESC
                LIMIT ? OFFSET ?
            ''', (ctx.guild.id, items_per_page, offset))
            title = "🏆 Топ кланов по уровню"
            value_template = "🏆 **Уровень:** {level}\n✨ **Опыт:** {xp:,}"
            
        else:  # xp
            cursor.execute('''
                SELECT c.clan_id, c.name, c.bank, c.owner_id,
                       COUNT(cm.user_id) as member_count,
                       cx.level, cx.xp
                FROM clans c
                LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
                LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                WHERE c.guild_id = ?
                GROUP BY c.clan_id
                ORDER BY cx.xp DESC, cx.level DESC
                LIMIT ? OFFSET ?
            ''', (ctx.guild.id, items_per_page, offset))
            title = "✨ Топ кланов по опыту"
            value_template = "✨ **Опыт:** {xp:,}\n🏆 **Уровень:** {level}"
        
        clans = cursor.fetchall()
        
        embed = discord.Embed(
            title=f"{title} (Страница {page}/{total_pages})",
            description=f"Всего кланов: {total_clans}",
            color=0x3498db
        )
        
        for i, clan in enumerate(clans, 1 + offset):
            clan_id, name, bank, owner_id, member_count, level, xp = clan
            
            owner = ctx.guild.get_member(owner_id)
            owner_name = owner.display_name if owner else f"Неизвестный ({owner_id})"
            
            cursor.execute('SELECT clan_type FROM clans WHERE clan_id = ?', (clan_id,))
            clan_type_result = cursor.fetchone()
            clan_type = clan_type_result[0] if clan_type_result else 'open'
            
            type_emojis = {'open': '🔓', 'closed': '🔒', 'application': '📝'}
            type_emoji = type_emojis.get(clan_type, '🏰')
            
            embed.add_field(
                name=f"{i}. {type_emoji} {name}",
                value=f"👑 **Владелец:** {owner_name}\n"
                      f"{value_template.format(bank=bank, member_count=member_count, level=level or 1, xp=xp or 0)}\n"
                      f"📊 **ID:** {clan_id}",
                inline=False
            )
        
        # Статистика сервера
        cursor.execute('''
            SELECT 
                SUM(c.bank) as total_bank,
                AVG(c.bank) as avg_bank,
                AVG(cx.level) as avg_level,
                SUM(cx.xp) as total_xp,
                COUNT(DISTINCT c.clan_id) as clan_count,
                COUNT(DISTINCT cm.user_id) as total_members
            FROM clans c
            LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
            LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
            WHERE c.guild_id = ?
        ''', (ctx.guild.id,))
        
        stats = cursor.fetchone()
        if stats and stats[0] is not None:
            total_bank, avg_bank, avg_level, total_xp, clan_count, total_members = stats
            embed.add_field(
                name="📈 Статистика сервера",
                value=f"Всего в банках: **{total_bank or 0:,}** монет\n"
                      f"Средний банк: **{int(avg_bank or 0):,}** монет\n"
                      f"Средний уровень: **{avg_level or 1:.1f}**\n"
                      f"Всего опыта: **{total_xp or 0:,}**\n"
                      f"Кланов: **{clan_count}**\n"
                      f"Участников кланов: **{total_members}**",
                inline=False
            )
        
        embed.set_footer(text=f"Сортировка: {sort_by} | Используйте /clan stats для детальной статистики")
        
        if total_pages > 1:
            view = discord.ui.View(timeout=60)
            
            class LeaderboardView(discord.ui.View):
                def __init__(self, total_pages, current_page, sort_by, guild_id, db):
                    super().__init__(timeout=60)
                    self.total_pages = total_pages
                    self.current_page = current_page
                    self.sort_by = sort_by
                    self.author_id = ctx.author.id
                    self.guild_id = guild_id
                    self.db = db
                
                @discord.ui.button(label="◀️ Назад", style=discord.ButtonStyle.secondary, disabled=True)
                async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.author_id:
                        await interaction.response.send_message("❌ Это не ваш лидерборд!", ephemeral=True)
                        return
                    
                    await self.update_page(interaction, self.current_page - 1)
                
                @discord.ui.button(label="▶️ Вперед", style=discord.ButtonStyle.secondary, disabled=False)
                async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.author_id:
                        await interaction.response.send_message("❌ Это не ваш лидерборд!", ephemeral=True)
                        return
                    
                    await self.update_page(interaction, self.current_page + 1)
                
                async def update_page(self, interaction: discord.Interaction, new_page):
                    cursor = self.db.conn.cursor()
                    offset = (new_page - 1) * items_per_page
                    
                    if self.sort_by == 'bank':
                        cursor.execute('''
                            SELECT c.clan_id, c.name, c.bank, c.owner_id,
                                   COUNT(cm.user_id) as member_count,
                                   cx.level, cx.xp
                            FROM clans c
                            LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
                            LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                            WHERE c.guild_id = ?
                            GROUP BY c.clan_id
                            ORDER BY c.bank DESC, cx.level DESC
                            LIMIT ? OFFSET ?
                        ''', (self.guild_id, items_per_page, offset))
                        title = "💰 Топ кланов по банку"
                        value_template = "💰 **Банк:** {bank} монет\n🏆 **Уровень:** {level}"
                        
                    elif self.sort_by == 'members':
                        cursor.execute('''
                            SELECT c.clan_id, c.name, c.bank, c.owner_id,
                                   COUNT(cm.user_id) as member_count,
                                   cx.level, cx.xp
                            FROM clans c
                            LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
                            LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                            WHERE c.guild_id = ?
                            GROUP BY c.clan_id
                            ORDER BY member_count DESC, c.bank DESC
                            LIMIT ? OFFSET ?
                        ''', (self.guild_id, items_per_page, offset))
                        title = "👥 Топ кланов по участникам"
                        value_template = "👥 **Участники:** {member_count}\n🏆 **Уровень:** {level}"
                        
                    elif self.sort_by == 'level':
                        cursor.execute('''
                            SELECT c.clan_id, c.name, c.bank, c.owner_id,
                                   COUNT(cm.user_id) as member_count,
                                   cx.level, cx.xp
                            FROM clans c
                            LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
                            LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                            WHERE c.guild_id = ?
                            GROUP BY c.clan_id
                            ORDER BY cx.level DESC, cx.xp DESC
                            LIMIT ? OFFSET ?
                        ''', (self.guild_id, items_per_page, offset))
                        title = "🏆 Топ кланов по уровню"
                        value_template = "🏆 **Уровень:** {level}\n✨ **Опыт:** {xp:,}"
                        
                    else:  # xp
                        cursor.execute('''
                            SELECT c.clan_id, c.name, c.bank, c.owner_id,
                                   COUNT(cm.user_id) as member_count,
                                   cx.level, cx.xp
                            FROM clans c
                            LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
                            LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                            WHERE c.guild_id = ?
                            GROUP BY c.clan_id
                            ORDER BY cx.xp DESC, cx.level DESC
                            LIMIT ? OFFSET ?
                        ''', (self.guild_id, items_per_page, offset))
                        title = "✨ Топ кланов по опыту"
                        value_template = "✨ **Опыт:** {xp:,}\n🏆 **Уровень:** {level}"
                    
                    clans = cursor.fetchall()
                    
                    embed = discord.Embed(
                        title=f"{title} (Страница {new_page}/{self.total_pages})",
                        description=f"Всего кланов: {total_clans}",
                        color=0x3498db
                    )
                    
                    for i, clan in enumerate(clans, 1 + offset):
                        clan_id, name, bank, owner_id, member_count, level, xp = clan
                        
                        owner = interaction.guild.get_member(owner_id)
                        owner_name = owner.display_name if owner else f"Неизвестный ({owner_id})"
                        
                        cursor.execute('SELECT clan_type FROM clans WHERE clan_id = ?', (clan_id,))
                        clan_type_result = cursor.fetchone()
                        clan_type = clan_type_result[0] if clan_type_result else 'open'
                        
                        type_emojis = {'open': '🔓', 'closed': '🔒', 'application': '📝'}
                        type_emoji = type_emojis.get(clan_type, '🏰')
                        
                        embed.add_field(
                            name=f"{i}. {type_emoji} {name}",
                            value=f"👑 **Владелец:** {owner_name}\n"
                                  f"{value_template.format(bank=bank, member_count=member_count, level=level or 1, xp=xp or 0)}\n"
                                  f"📊 **ID:** {clan_id}",
                            inline=False
                        )
                    
                    embed.set_footer(text=f"Сортировка: {self.sort_by} | Используйте /clan stats для детальной статистики")
                    
                    self.current_page = new_page
                    self.children[0].disabled = (new_page == 1)
                    self.children[1].disabled = (new_page == self.total_pages)
                    
                    await interaction.response.edit_message(embed=embed, view=self)
            
            view = LeaderboardView(total_pages, page, sort_by, ctx.guild.id, self.db)
            view.children[0].disabled = (page == 1)
            view.children[1].disabled = (page == total_pages)
            
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)
    
    @clan_group.command(name='create', description='Создать клан')
    @app_commands.describe(
        name='Название клана',
        description='Описание клана',
        clan_type='Тип клана (open, closed, application)',
        prefix='Префикс для роли клана (необязательно)'
    )
    async def clan_create(self, ctx, name: str, description: str = "", 
                         clan_type: str = "open", prefix: str = ""):
        """Создать новый клан"""
        cursor = self.db.conn.cursor()
        
        try:
            # Проверяем, состоит ли пользователь уже в клане
            cursor.execute('''
                SELECT clan_id FROM clan_members 
                WHERE user_id = ? AND guild_id = ?
            ''', (ctx.author.id, ctx.guild.id))
            
            if cursor.fetchone():
                await ctx.send("❌ Вы уже состоите в клане! Покиньте текущий клан перед созданием нового.", ephemeral=True)
                return
            
            # Проверяем, существует ли клан с таким названием
            cursor.execute('SELECT clan_id FROM clans WHERE guild_id = ? AND name = ?', 
                          (ctx.guild.id, name))
            if cursor.fetchone():
                await ctx.send("❌ Клан с таким названием уже существует!", ephemeral=True)
                return
            
            if clan_type not in ['open', 'closed', 'application']:
                await ctx.send("❌ Неверный тип клана! Доступные: open, closed, application", ephemeral=True)
                return
            
            # Создаем роль для клана, если указан префикс
            role = None
            role_created = False
            
            if prefix:
                try:
                    role_name = f"{prefix} | {name}"
                    role = await ctx.guild.create_role(
                        name=role_name,
                        color=discord.Color.random(),
                        mentionable=True
                    )
                    role_created = True
                    
                    await ctx.author.add_roles(role)
                    
                except discord.Forbidden:
                    await ctx.send("❌ У меня нет прав создавать роли! Нужны права 'Управление ролями'.", ephemeral=True)
                    return
                except Exception as e:
                    await ctx.send(f"❌ Ошибка при создании роли: {e}", ephemeral=True)
                    return
            
            # Генерируем код для вступления, если клан закрытый
            join_code = self.generate_join_code() if clan_type == "closed" else None
            
            self.db.conn.execute("BEGIN TRANSACTION")
            
            try:
                # Создаем клан в базе данных
                cursor.execute('''
                    INSERT INTO clans (guild_id, name, owner_id, description, 
                                     clan_type, join_code, prefix, role_id, created_at, bank)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ''', (ctx.guild.id, name, ctx.author.id, description, clan_type, 
                      join_code, prefix, role.id if role else None, int(datetime.now().timestamp())))
                
                clan_id = cursor.lastrowid
                
                # Создаем запись для XP клана
                cursor.execute('''
                    INSERT INTO clan_xp (clan_id) VALUES (?)
                ''', (clan_id,))
                
                # Добавляем создателя как владельца
                cursor.execute('''
                    INSERT INTO clan_members (user_id, guild_id, clan_id, role, joined_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (ctx.author.id, ctx.guild.id, clan_id, 'owner', int(datetime.now().timestamp())))
                
                # Создаем статистику для участника
                self.db.update_clan_member_stats(
                    ctx.author.id, ctx.guild.id, clan_id,
                    last_active=int(datetime.now().timestamp())
                )
                
                # Начисляем XP за создание клана
                await self.add_clan_xp(
                    clan_id, 500, ctx.author.id,
                    event_type="member_join",
                    details="Создание клана"
                )

                # Проверяем достижения по участникам (1 участник)
                achievements_cog = self.bot.get_cog('Achievements')
                if achievements_cog:
                    await achievements_cog.check_achievements(ctx.author.id, ctx.guild.id, 'clan_members', 1)
                
                # Создаем настройки по умолчанию
                cursor.execute('''
                    INSERT INTO clan_settings (clan_id, member_role_name, coowner_role_name, owner_role_name)
                    VALUES (?, 'Участник', 'Совладелец', 'Владелец')
                ''', (clan_id,))
                
                # Фиксируем транзакцию
                self.db.conn.commit()
                
                # Создаем embed с информацией
                embed = discord.Embed(
                    title=f"✅ Клан создан: {name}",
                    description=description if description else "Описание не указано",
                    color=0x00ff00
                )
                
                embed.add_field(name="👑 Владелец", value=ctx.author.mention, inline=True)
                embed.add_field(name="🔒 Тип", value=clan_type, inline=True)
                embed.add_field(name="💰 Банк", value="0 монет", inline=True)
                embed.add_field(name="🏆 Уровень", value="1 (+500 XP за создание)", inline=True)
                
                if role:
                    embed.add_field(name="🏷️ Роль", value=role.mention, inline=True)
                
                if clan_type == "closed" and join_code:
                    embed.add_field(name="🔑 Код для вступления", value=f"`{join_code}`", inline=False)
                    embed.set_footer(text="Сохраните этот код! Он потребуется для вступления в клан.")
                
                await ctx.send(embed=embed, ephemeral=True)
                
            except Exception as e:
                self.db.conn.rollback()
                
                if role_created and role:
                    try:
                        await role.delete()
                    except:
                        pass
                
                if "UNIQUE constraint" in str(e):
                    await ctx.send("❌ Ошибка: Вы уже состоите в каком-то клане или имя клана занято!", ephemeral=True)
                else:
                    await ctx.send(f"❌ Ошибка при создании клана: {str(e)[:100]}", ephemeral=True)
                    
        except Exception as e:
            await ctx.send(f"❌ Критическая ошибка: {str(e)[:100]}", ephemeral=True)
    
    @clan_group.command(name='info', description='Информация о клане')
    @app_commands.describe(name='Название клана (необязательно)')
    async def clan_info(self, ctx, name: Optional[str] = None):
        """Информация о клане"""
        try:
            if name:
                # Ищем клан по имени
                cursor = self.db.conn.cursor()
                cursor.execute('SELECT clan_id FROM clans WHERE guild_id = ? AND name = ?', 
                              (ctx.guild.id, name))
                result = cursor.fetchone()
                if not result:
                    await ctx.send("❌ Клан не найден!", ephemeral=True)
                    return
                clan_id = result[0]
            else:
                # Информация о своем клане
                user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
                if not user_clan:
                    await ctx.send("❌ Вы не состоите в клане! Укажите название клана.", ephemeral=True)
                    return
                clan_id = user_clan[2]
            
            # Получаем информацию о клане
            clan_info = self.get_clan_info(clan_id, ctx.guild.id)
            if not clan_info:
                await ctx.send("❌ Клан не найден!", ephemeral=True)
                return
            
            # Получаем участников
            members = self.get_clan_members(clan_id)
            
            # Создаем embed
            embed = discord.Embed(
                title=f"🏰 {clan_info[2]}",  # name
                color=0x3498db
            )
            
            # Добавляем описание
            description = clan_info[4] if clan_info[4] else "Описание не указано"
            embed.description = str(description)
            
            # Получаем владельца
            owner_id = clan_info[3] if clan_info[3] else 0
            owner = ctx.guild.get_member(owner_id)
            owner_name = owner.mention if owner else f"Неизвестный ({owner_id})"
            
            # Получаем уровень и опыт (правильные индексы!)
            clan_level = clan_info[14] if len(clan_info) > 14 and clan_info[14] is not None else 1
            clan_xp = clan_info[15] if len(clan_info) > 15 and clan_info[15] is not None else 0
            
            # Преобразуем в int если нужно
            try:
                clan_level = int(clan_level)
            except (ValueError, TypeError):
                clan_level = 1
                
            try:
                clan_xp = int(clan_xp)
            except (ValueError, TypeError):
                clan_xp = 0
            
            # Рассчитываем прогресс до следующего уровня
            xp_for_next_level = ((clan_level + 1) ** 2) * 100
            xp_for_current_level = (clan_level ** 2) * 100
            
            progress = 0
            if xp_for_next_level > xp_for_current_level:
                progress = ((clan_xp - xp_for_current_level) / 
                           (xp_for_next_level - xp_for_current_level)) * 100
            else:
                progress = 100
            
            # Банк клана
            bank_amount = clan_info[9] if clan_info[9] is not None else 0
            try:
                bank_amount = int(bank_amount)
            except (ValueError, TypeError):
                bank_amount = 0
            
            # Основные поля
            embed.add_field(name="👑 Владелец", value=str(owner_name), inline=True)
            embed.add_field(name="🔒 Тип", value=str(clan_info[5]), inline=True)  # clan_type
            embed.add_field(name="💰 Банк клана", value=f"{bank_amount} монет", inline=True)
            embed.add_field(name="👥 Участники", value=f"{len(members)} человек", inline=True)
            embed.add_field(name="🏆 Уровень", value=str(clan_level), inline=True)
            embed.add_field(name="✨ Опыт", value=f"{clan_xp:,} XP", inline=True)
            
            # Прогресс бар
            bars = 10
            filled_bars = int(progress / 100 * bars)
            progress_bar = "█" * filled_bars + "░" * (bars - filled_bars)
            embed.add_field(
                name="📊 Прогресс до след. уровня",
                value=f"```{progress_bar} {progress:.1f}%```\n"
                      f"Нужно: **{xp_for_next_level - clan_xp:,} XP**",
                inline=False
            )
            
            # Тип доступа
            clan_type = clan_info[5] if clan_info[5] else "open"
            if clan_type == 'closed':
                embed.add_field(name="🔐 Доступ", value="Закрытый (только по коду)", inline=True)
            elif clan_type == 'application':
                embed.add_field(name="📝 Доступ", value="По заявке", inline=True)
            else:
                embed.add_field(name="🔓 Доступ", value="Открытый", inline=True)
            
            # Роль клана
            role_id = clan_info[8]
            if role_id:
                try:
                    role_id_int = int(role_id)
                    role = ctx.guild.get_role(role_id_int)
                    if role:
                        embed.add_field(name="🏷️ Роль клана", value=role.mention, inline=True)
                except (ValueError, TypeError):
                    pass
            
            # Список совладельцев
            coowners = [m for m in members if m[1] == 'coowner']
            if coowners:
                coowner_list = []
                for member in coowners[:5]:
                    try:
                        user_id = int(member[0])
                        user = ctx.guild.get_member(user_id)
                        if user:
                            coowner_list.append(user.mention)
                    except (ValueError, TypeError):
                        continue
                if coowner_list:
                    embed.add_field(name="👥 Совладельцы", value=", ".join(coowner_list), inline=False)
            
            # Топ 3 вкладчика
            top_depositors = sorted(members, key=lambda x: x[3] or 0, reverse=True)[:3]
            if top_depositors:
                depositors_text = ""
                for member in top_depositors:
                    try:
                        user_id = int(member[0])
                        user = ctx.guild.get_member(user_id)
                        name = user.display_name if user else f"ID: {member[0]}"
                        amount = member[3] or 0
                        depositors_text += f"• **{name[:15]}** - {amount:,} монет\n"
                    except (ValueError, TypeError):
                        continue
                
                if depositors_text:
                    embed.add_field(name="🏅 Топ вкладчики", value=depositors_text, inline=False)
            
            embed.set_footer(text=f"ID клана: {clan_id}")
            
            # Добавляем timestamp если есть created_at
            if len(clan_info) > 10 and clan_info[10]:
                try:
                    created_at = int(clan_info[10])
                    embed.timestamp = datetime.fromtimestamp(created_at)
                    embed.set_footer(text=f"ID клана: {clan_id} | Создан")
                except (ValueError, TypeError):
                    embed.set_footer(text=f"ID клана: {clan_id}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"❌ Ошибка в clan_info: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ Ошибка при получении информации о клане: {str(e)[:100]}", ephemeral=True)
    
    @clan_group.command(name='code', description='Показать код для вступления в закрытый клан')
    async def clan_code(self, ctx):
        """Показать код для вступления в закрытый клан (только для участников)"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        clan_name = user_clan[5]
        clan_type = user_clan[7]
        join_code = user_clan[9]
        
        if clan_type != 'closed':
            await ctx.send("❌ Ваш клан не является закрытым. Код для вступления отсутствует.", ephemeral=True)
            return
        
        if not join_code:
            # Если кода нет в базе, генерируем новый и сохраняем
            cursor = self.db.conn.cursor()
            join_code = self.generate_join_code()
            cursor.execute('UPDATE clans SET join_code = ? WHERE clan_id = ?', (join_code, user_clan[2]))
            self.db.conn.commit()
            await ctx.send("⚠️ Код для вашего клана был утерян. Сгенерирован новый код.", ephemeral=True)
        
        embed = discord.Embed(
            title=f"🔑 Код для вступления в клан {clan_name}",
            description=f"Код для вступления в ваш клан: `{join_code}`",
            color=0x00ff00
        )
        embed.set_footer(text="Сохраните этот код в безопасности и не передавайте посторонним!")
        
        await ctx.send(embed=embed, ephemeral=True)
    
    @clan_group.command(name='join', description='Вступить в клан')
    @app_commands.describe(
        name='Название клана (для открытых)',
        code='Код для вступления (для закрытых)'
    )
    async def clan_join(self, ctx, name: Optional[str] = None, code: Optional[str] = None):
        """Вступить в клан"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if user_clan:
            await ctx.send(f"❌ Вы уже состоите в клане **{user_clan[5]}**!", ephemeral=True)
            return
        
        cursor = self.db.conn.cursor()
        
        if code:
            cursor.execute('''
                SELECT clan_id, name, clan_type, join_code FROM clans 
                WHERE guild_id = ? AND join_code = ?
            ''', (ctx.guild.id, code))
            
            clan = cursor.fetchone()
            if not clan:
                await ctx.send("❌ Неверный код или клан не найден!", ephemeral=True)
                return
            
            clan_id, clan_name, clan_type, db_code = clan
            
            if clan_type != 'closed':
                await ctx.send("❌ Этот клан не закрытый!", ephemeral=True)
                return
            
            if db_code != code:
                await ctx.send("❌ Неверный код!", ephemeral=True)
                return
            
            cursor.execute('''
                INSERT INTO clan_members (user_id, guild_id, clan_id, role, joined_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (ctx.author.id, ctx.guild.id, clan_id, 'member', int(datetime.now().timestamp())))
            
            # Создаем статистику для участника
            self.db.update_clan_member_stats(
                ctx.author.id, ctx.guild.id, clan_id,
                last_active=int(datetime.now().timestamp())
            )
            
            cursor.execute('SELECT role_id FROM clans WHERE clan_id = ?', (clan_id,))
            role_result = cursor.fetchone()
            role_id = role_result[0] if role_result else None
            if role_id:
                role = ctx.guild.get_role(role_id)
                if role:
                    try:
                        await ctx.author.add_roles(role)
                    except:
                        pass
            
            self.db.conn.commit()
            
            # Начисляем XP клану за нового участника
            await self.add_clan_xp(
                clan_id, 100, ctx.author.id,
                event_type="member_join",
                details=f"Вступил новый участник: {ctx.author.display_name}"
            )
            
            await ctx.send(f"✅ Вы вступили в клан **{clan_name}**!")
            
        elif name:
            cursor.execute('''
                SELECT clan_id, name, clan_type FROM clans 
                WHERE guild_id = ? AND name = ?
            ''', (ctx.guild.id, name))
            
            clan = cursor.fetchone()
            if not clan:
                await ctx.send("❌ Клан не найден!", ephemeral=True)
                return
            
            clan_id, clan_name, clan_type = clan
            
            if clan_type == 'open':
                cursor.execute('''
                    INSERT INTO clan_members (user_id, guild_id, clan_id, role, joined_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (ctx.author.id, ctx.guild.id, clan_id, 'member', int(datetime.now().timestamp())))
                
                # Создаем статистику для участника
                self.db.update_clan_member_stats(
                    ctx.author.id, ctx.guild.id, clan_id,
                    last_active=int(datetime.now().timestamp())
                )
                
                cursor.execute('SELECT role_id FROM clans WHERE clan_id = ?', (clan_id,))
                role_result = cursor.fetchone()
                role_id = role_result[0] if role_result else None
                if role_id:
                    role = ctx.guild.get_role(role_id)
                    if role:
                        try:
                            await ctx.author.add_roles(role)
                        except:
                            pass
                
                self.db.conn.commit()
                
                # Начисляем XP клану за нового участника
                await self.add_clan_xp(
                    clan_id, 100, ctx.author.id,
                    event_type="member_join",
                    details=f"Вступил новый участник: {ctx.author.display_name}"
                )
                
                await ctx.send(f"✅ Вы вступили в клан **{clan_name}**!")

                cursor.execute('SELECT COUNT(*) FROM clan_members WHERE clan_id = ?', (clan_id,))
                member_count = cursor.fetchone()[0]

                achievements_cog = self.bot.get_cog('Achievements')
                if achievements_cog:
                    cursor.execute('SELECT user_id FROM clan_members WHERE clan_id = ?', (clan_id,))
                    members = cursor.fetchall()
                    for member in members:
                        user_id = member[0]
                        await achievements_cog.check_achievements(user_id, ctx.guild.id, 'clan_members', member_count)
                
            elif clan_type == 'application':
                cursor.execute('''
                    INSERT INTO clan_applications (clan_id, user_id, guild_id, message, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (clan_id, ctx.author.id, ctx.guild.id, 
                      f"Заявка от {ctx.author.display_name}", int(datetime.now().timestamp())))
                
                self.db.conn.commit()
                
                cursor.execute('''
                    SELECT cm.user_id FROM clan_members cm
                    WHERE cm.clan_id = ? AND cm.role IN ('owner', 'coowner')
                ''', (clan_id,))
                
                leaders = cursor.fetchall()
                mentions = []
                for leader in leaders:
                    member = ctx.guild.get_member(leader[0])
                    if member:
                        mentions.append(member.mention)
                
                embed = discord.Embed(
                    title="📨 Новая заявка на вступление",
                    description=f"Пользователь {ctx.author.mention} подал заявку на вступление в клан **{clan_name}**",
                    color=0xf1c40f
                )
                embed.set_footer(text="Используйте /clan applications для просмотра заявок")
                
                if mentions:
                    await ctx.send(f"{' '.join(mentions)}", embed=embed)
                else:
                    await ctx.send(embed=embed)
                    
                await ctx.send("✅ Заявка отправлена! Ожидайте решения.", ephemeral=True)
            else:
                await ctx.send("❌ Этот клан закрыт для вступления. Используйте код.", ephemeral=True)
        else:
            await ctx.send("❌ Укажите название клана или код!", ephemeral=True)
    
    @clan_group.command(name='leave', description='Покинуть клан')
    async def clan_leave(self, ctx):
        """Покинуть клан"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        clan_id, clan_role = user_clan[2], user_clan[3]
        
        if clan_role == 'owner':
            await ctx.send("❌ Владелец не может покинуть клан! Используйте /clan disband для роспуска.", ephemeral=True)
            return
        
        cursor = self.db.conn.cursor()
        cursor.execute('DELETE FROM clan_members WHERE user_id = ? AND guild_id = ?', 
                      (ctx.author.id, ctx.guild.id))
        
        cursor.execute('SELECT role_id FROM clans WHERE clan_id = ?', (clan_id,))
        role_result = cursor.fetchone()
        role_id = role_result[0] if role_result else None
        if role_id:
            role = ctx.guild.get_role(role_id)
            if role:
                try:
                    await ctx.author.remove_roles(role)
                except:
                    pass

        cursor.execute('SELECT COUNT(*) FROM clan_members WHERE clan_id = ?', (clan_id,))
        member_count = cursor.fetchone()[0]

        achievements_cog = self.bot.get_cog('Achievements')
        if achievements_cog:
            cursor.execute('SELECT user_id FROM clan_members WHERE clan_id = ?', (clan_id,))
            members = cursor.fetchall()
            for member in members:
                user_id = member[0]
                await achievements_cog.check_achievements(user_id, ctx.guild.id, 'clan_members', member_count)
        
        self.db.conn.commit()
        await ctx.send(f"✅ Вы покинули клан **{user_clan[5]}**!")
    
    @clan_group.command(name='deposit', description='Внести деньги в банк клана')
    @app_commands.describe(amount='Сумма для внесения')
    async def clan_deposit(self, ctx, amount: int):
        """Внести деньги в банк клана"""
        if amount <= 0:
            await ctx.send("❌ Сумма должна быть положительной!", ephemeral=True)
            return
        
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        user_data = self.db.get_user(ctx.author.id, ctx.guild.id)
        if user_data[2] < amount:
            await ctx.send("❌ Недостаточно монет!", ephemeral=True)
            return
        
        clan_id = user_clan[2]
        
        cursor = self.db.conn.cursor()
        
        try:
            cursor.execute("BEGIN TRANSACTION")
            
            cursor.execute('''
                UPDATE users 
                SET balance = balance - ? 
                WHERE user_id = ? AND guild_id = ?
            ''', (amount, ctx.author.id, ctx.guild.id))
            
            cursor.execute('''
                UPDATE clans 
                SET bank = bank + ? 
                WHERE clan_id = ?
            ''', (amount, clan_id))
            
            # Обновляем статистику депозитов пользователя
            self.db.update_clan_member_stats(
                ctx.author.id, ctx.guild.id, clan_id,
                total_deposited=amount,
                last_active=int(datetime.now().timestamp())
            )
            
            cursor.execute('SELECT bank FROM clans WHERE clan_id = ?', (clan_id,))
            new_bank = cursor.fetchone()[0]
            
            cursor.execute('SELECT balance FROM users WHERE user_id = ? AND guild_id = ?', 
                         (ctx.author.id, ctx.guild.id))
            new_balance = cursor.fetchone()[0]
            
            self.db.conn.commit()
            
            # Начисляем XP клану за депозит
            xp_earned = max(1, amount // 50)  # 2 XP за 100 монет, минимум 1
            new_level, reward = await self.add_clan_xp(
                clan_id, xp_earned, ctx.author.id,
                event_type="deposit",
                details=f"Депозит: {amount} монет"
            )
            
            embed = discord.Embed(
                title="💰 Взнос в банк клана",
                description=f"{ctx.author.mention} внес **{amount}** монет в банк клана!",
                color=0x00ff00
            )
            embed.add_field(name="💎 Новый баланс клана", value=f"{new_bank} монет", inline=True)
            embed.add_field(name="📊 Ваш новый баланс", value=f"{new_balance} монет", inline=True)
            embed.add_field(name="✨ Получено опыта", value=f"+{xp_earned} XP", inline=True)
            
            if new_level:
                embed.add_field(
                    name="🎉 Новый уровень клана!",
                    value=f"Клан достиг **{new_level}** уровня!",
                    inline=False
                )
            
            await ctx.send(embed=embed)

            achievements_cog = self.bot.get_cog('Achievements')
            if achievements_cog:
                cursor.execute('SELECT user_id FROM clan_members WHERE clan_id = ?', (clan_id,))
                members = cursor.fetchall()
                for member in members:
                    user_id = member[0]
                    await achievements_cog.check_achievements(user_id, ctx.guild.id, 'clan_bank', new_bank)
            
        except Exception as e:
            self.db.conn.rollback()
            await ctx.send(f"❌ Ошибка при внесении средств: {e}", ephemeral=True)
    
    @clan_group.command(name='withdraw', description='Вывести деньги из банка клана')
    @app_commands.describe(
        amount='Сумма для вывода',
        member='Участник, которому перевести (необязательно)'
    )
    async def clan_withdraw(self, ctx, amount: int, member: discord.Member = None):
        """Вывести деньги из банка клана"""
        if amount <= 0:
            await ctx.send("❌ Сумма должна быть положительной!", ephemeral=True)
            return
        
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        if user_clan[3] not in ['owner', 'coowner']:
            await ctx.send("❌ Только владелец и совладельцы могут выводить средства из банка клана!", ephemeral=True)
            return
        
        clan_id = user_clan[2]
        clan_name = user_clan[5]
        
        recipient = member or ctx.author
        recipient_name = recipient.display_name
        
        if member and member.id != ctx.author.id:
            recipient_clan = self.get_user_clan(member.id, ctx.guild.id)
            if not recipient_clan or recipient_clan[2] != clan_id:
                await ctx.send(f"❌ {member.mention} не состоит в вашем клане!", ephemeral=True)
                return
        
        cursor = self.db.conn.cursor()
        
        cursor.execute('SELECT bank FROM clans WHERE clan_id = ?', (clan_id,))
        clan_bank = cursor.fetchone()[0]
        
        if clan_bank < amount:
            await ctx.send(f"❌ В банке клана недостаточно средств! Доступно: {clan_bank} монет.", ephemeral=True)
            return
        
        try:
            cursor.execute("BEGIN TRANSACTION")
            
            cursor.execute('''
                UPDATE clans 
                SET bank = bank - ? 
                WHERE clan_id = ?
            ''', (amount, clan_id))
            
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ? 
                WHERE user_id = ? AND guild_id = ?
            ''', (amount, recipient.id, ctx.guild.id))
            
            cursor.execute('SELECT bank FROM clans WHERE clan_id = ?', (clan_id,))
            new_bank = cursor.fetchone()[0]
            
            cursor.execute('SELECT balance FROM users WHERE user_id = ? AND guild_id = ?', 
                         (recipient.id, ctx.guild.id))
            recipient_new_balance = cursor.fetchone()[0]
            
            self.db.conn.commit()
            
            cursor.execute('''
                INSERT INTO transactions (from_user_id, to_user_id, guild_id, item_id, amount, transaction_type, created_at)
                VALUES (?, ?, ?, NULL, ?, ?, ?)
            ''', (0, recipient.id, ctx.guild.id, amount, 'clan_withdraw', int(datetime.now().timestamp())))
            self.db.conn.commit()
            
            embed = discord.Embed(
                title="💰 Вывод из банка клана",
                description=f"Из банка клана **{clan_name}** выведено **{amount}** монет.",
                color=0x00ff00
            )
            
            embed.add_field(name="📤 Вывел", value=ctx.author.mention, inline=True)
            embed.add_field(name="📥 Получил", value=recipient.mention, inline=True)
            embed.add_field(name="💎 Новый баланс клана", value=f"{new_bank} монет", inline=True)
            
            if recipient.id != ctx.author.id:
                embed.add_field(name="📊 Баланс получателя", value=f"{recipient_new_balance} монет", inline=True)
            
            embed.set_footer(text=f"ID клана: {clan_id}")
            
            await ctx.send(embed=embed)

            achievements_cog = self.bot.get_cog('Achievements')
            if achievements_cog:
                cursor.execute('SELECT user_id FROM clan_members WHERE clan_id = ?', (clan_id,))
                members = cursor.fetchall()
                for member in members:
                    user_id = member[0]
                    await achievements_cog.check_achievements(user_id, ctx.guild.id, 'clan_bank', new_bank)
            
        except Exception as e:
            self.db.conn.rollback()
            await ctx.send(f"❌ Ошибка при выводе средств: {e}", ephemeral=True)
    
    @clan_group.command(name='members', description='Список участников клана')
    async def clan_members(self, ctx):
        """Показать участников клана"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        clan_id, clan_name = user_clan[2], user_clan[5]
        
        members = self.get_clan_members(clan_id)
        
        owners = []
        coowners = []
        regulars = []
        
        for member in members:
            user = ctx.guild.get_member(member[0])
            if not user:
                continue
                
            join_date = datetime.fromtimestamp(member[2]).strftime('%d.%m.%Y') if member[2] else "Неизвестно"
            member_info = f"{user.mention} (с {join_date})"
            
            if member[1] == 'owner':
                owners.append(member_info)
            elif member[1] == 'coowner':
                coowners.append(member_info)
            else:
                regulars.append(member_info)
        
        embed = discord.Embed(
            title=f"👥 Участники клана {clan_name}",
            description=f"Всего участников: {len(members)}",
            color=0x3498db
        )
        
        if owners:
            embed.add_field(name="👑 Владелец", value="\n".join(owners), inline=False)
        if coowners:
            embed.add_field(name="👥 Совладельцы", value="\n".join(coowners) if coowners else "Нет", inline=False)
        if regulars:
            for i in range(0, len(regulars), 10):
                group = regulars[i:i+10]
                embed.add_field(name=f"👤 Участники (группа {i//10 + 1})", 
                              value="\n".join(group), inline=False)
        
        await ctx.send(embed=embed)
    
    @clan_group.command(name='kick', description='Исключить участника из клана')
    @app_commands.describe(member='Участник для исключения')
    async def clan_kick(self, ctx, member: discord.Member):
        """Исключить участника из клана"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        if user_clan[3] not in ['owner', 'coowner']:
            await ctx.send("❌ Только владелец и совладельцы могут исключать участников!", ephemeral=True)
            return
        
        target_clan = self.get_user_clan(member.id, ctx.guild.id)
        if not target_clan or target_clan[2] != user_clan[2]:
            await ctx.send(f"❌ {member.mention} не состоит в вашем клане!", ephemeral=True)
            return
        
        if target_clan[3] == 'owner':
            await ctx.send("❌ Нельзя исключить владельца клана!", ephemeral=True)
            return
        
        if member.id == ctx.author.id:
            await ctx.send("❌ Нельзя исключить самого себя!", ephemeral=True)
            return
        
        clan_id = user_clan[2]
        cursor = self.db.conn.cursor()
        cursor.execute('DELETE FROM clan_members WHERE user_id = ? AND guild_id = ?', 
                      (member.id, ctx.guild.id))
        
        cursor.execute('SELECT role_id FROM clans WHERE clan_id = ?', (clan_id,))
        role_result = cursor.fetchone()
        role_id = role_result[0] if role_result else None
        if role_id:
            role = ctx.guild.get_role(role_id)
            if role:
                try:
                    await member.remove_roles(role)
                except:
                    pass
        
        self.db.conn.commit()
        
        embed = discord.Embed(
            title="🚪 Исключение из клана",
            description=f"{member.mention} был исключен из клана **{user_clan[5]}**",
            color=0xe74c3c
        )
        embed.set_footer(text=f"Исключил: {ctx.author}")

        cursor.execute('SELECT COUNT(*) FROM clan_members WHERE clan_id = ?', (clan_id,))
        member_count = cursor.fetchone()[0]

        achievements_cog = self.bot.get_cog('Achievements')
        if achievements_cog:
            cursor.execute('SELECT user_id FROM clan_members WHERE clan_id = ?', (clan_id,))
            members = cursor.fetchall()
            for member in members:
                user_id = member[0]
                await achievements_cog.check_achievements(user_id, ctx.guild.id, 'clan_members', member_count)
        
        await ctx.send(embed=embed)
    
    @clan_group.command(name='disband', description='Распустить клан')
    async def clan_disband(self, ctx):
        """Распустить клан"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        if user_clan[3] != 'owner':
            await ctx.send("❌ Только владелец может распустить клан!", ephemeral=True)
            return
        
        clan_id, clan_name = user_clan[2], user_clan[5]
        
        embed = discord.Embed(
            title="⚠️ Подтверждение роспуска клана",
            description=f"Вы уверены, что хотите распустить клан **{clan_name}**?\n\nЭто действие невозможно отменить!",
            color=0xe74c3c
        )
        embed.add_field(name="👥 Участники", value="Будут удалены из клана", inline=True)
        embed.add_field(name="💰 Банк", value="Все деньги будут потеряны", inline=True)
        embed.add_field(name="🏷️ Роль", value="Будет удалена", inline=True)
        
        view = discord.ui.View(timeout=30)
        
        async def confirm_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ Это не ваше подтверждение!", ephemeral=True)
                return
            
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT role_id FROM clans WHERE clan_id = ?', (clan_id,))
            role_result = cursor.fetchone()
            role_id = role_result[0] if role_result else None
            
            if role_id:
                role = ctx.guild.get_role(role_id)
                if role:
                    try:
                        await role.delete()
                    except:
                        pass
            
            cursor.execute('DELETE FROM clans WHERE clan_id = ?', (clan_id,))
            self.db.conn.commit()
            
            await interaction.response.edit_message(
                content=f"✅ Клан **{clan_name}** был распущен!",
                embed=None,
                view=None
            )
        
        async def cancel_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ Это не ваше подтверждение!", ephemeral=True)
                return
            
            await interaction.response.edit_message(
                content="❌ Роспуск клана отменен.",
                embed=None,
                view=None
            )
        
        confirm_btn = discord.ui.Button(label="✅ Да, распустить", style=discord.ButtonStyle.danger)
        confirm_btn.callback = confirm_callback
        view.add_item(confirm_btn)
        
        cancel_btn = discord.ui.Button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = cancel_callback
        view.add_item(cancel_btn)
        
        await ctx.send(embed=embed, view=view)
    
    @clan_group.command(name='settings', description='Настройки клана')
    @app_commands.describe(
        setting='Что изменить (name, description, type, prefix, member_role, coowner_role, owner_role)',
        value='Новое значение'
    )
    async def clan_settings(self, ctx, setting: str, value: str):
        """Настройки клана"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        if user_clan[3] not in ['owner', 'coowner']:
            await ctx.send("❌ Только владелец и совладельцы могут изменять настройки!", ephemeral=True)
            return
        
        clan_id = user_clan[2]
        cursor = self.db.conn.cursor()
        
        if setting.lower() == 'name':
            cursor.execute('SELECT clan_id FROM clans WHERE guild_id = ? AND name = ? AND clan_id != ?', 
                          (ctx.guild.id, value, clan_id))
            if cursor.fetchone():
                await ctx.send("❌ Клан с таким названием уже существует!", ephemeral=True)
                return
            
            cursor.execute('UPDATE clans SET name = ? WHERE clan_id = ?', (value, clan_id))
            
            cursor.execute('SELECT role_id, prefix FROM clans WHERE clan_id = ?', (clan_id,))
            result = cursor.fetchone()
            role_id, prefix = result if result else (None, '')
            
            if role_id and prefix:
                role = ctx.guild.get_role(role_id)
                if role:
                    try:
                        await role.edit(name=f"{prefix} | {value}")
                    except:
                        pass
            
            await ctx.send(f"✅ Название клана изменено на **{value}**!")
            
        elif setting.lower() == 'description':
            cursor.execute('UPDATE clans SET description = ? WHERE clan_id = ?', (value, clan_id))
            await ctx.send(f"✅ Описание клана обновлено!")
            
        elif setting.lower() == 'type':
            valid_types = ['open', 'closed', 'application']
            if value.lower() not in valid_types:
                await ctx.send(f"❌ Неверный тип! Доступные: {', '.join(valid_types)}", ephemeral=True)
                return
            
            join_code = None
            if value.lower() == 'closed':
                join_code = self.generate_join_code()
            
            cursor.execute('UPDATE clans SET clan_type = ?, join_code = ? WHERE clan_id = ?', 
                          (value.lower(), join_code, clan_id))
            
            embed = discord.Embed(
                title="🔒 Тип клана изменен",
                description=f"Тип клана изменен на **{value}**",
                color=0x3498db
            )
            
            if join_code:
                embed.add_field(name="🔑 Новый код для вступления", value=f"`{join_code}`")
                embed.set_footer(text="Сохраните этот код! Он потребуется для вступления в клан.")
            
            await ctx.send(embed=embed)
            
        elif setting.lower() == 'prefix':
            cursor.execute('UPDATE clans SET prefix = ? WHERE clan_id = ?', (value, clan_id))
            
            cursor.execute('SELECT role_id, name FROM clans WHERE clan_id = ?', (clan_id,))
            result = cursor.fetchone()
            role_id, clan_name = result if result else (None, '')
            
            if role_id:
                role = ctx.guild.get_role(role_id)
                if role:
                    try:
                        new_name = f"{value} | {clan_name}" if value else clan_name
                        await role.edit(name=new_name)
                    except:
                        pass
            
            await ctx.send(f"✅ Префикс клана изменен на **{value}**!")
            
        elif setting.lower() == 'member_role':
            self.db.update_clan_settings(clan_id, member_role_name=value)
            await ctx.send(f"✅ Название роли участника изменено на **{value}**!")
            
        elif setting.lower() == 'coowner_role':
            self.db.update_clan_settings(clan_id, coowner_role_name=value)
            await ctx.send(f"✅ Название роли совладельца изменено на **{value}**!")
            
        elif setting.lower() == 'owner_role':
            self.db.update_clan_settings(clan_id, owner_role_name=value)
            await ctx.send(f"✅ Название роли владельца изменено на **{value}**!")
            
        else:
            await ctx.send("❌ Неизвестная настройка! Доступные: name, description, type, prefix, member_role, coowner_role, owner_role", ephemeral=True)
            return
        
        self.db.conn.commit()
    
    @clan_group.command(name='applications', description='Просмотр заявок на вступление')
    async def clan_applications(self, ctx):
        """Просмотр заявок на вступление"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        if user_clan[3] not in ['owner', 'coowner']:
            await ctx.send("❌ Только владелец и совладельцы могут просматривать заявки!", ephemeral=True)
            return
        
        clan_id = user_clan[2]
        cursor = self.db.conn.cursor()
        
        cursor.execute('''
            SELECT ca.*, u.balance as user_balance
            FROM clan_applications ca
            JOIN users u ON ca.user_id = u.user_id AND ca.guild_id = u.guild_id
            WHERE ca.clan_id = ? AND ca.status = 'pending'
            ORDER BY ca.created_at DESC
        ''', (clan_id,))
        
        applications = cursor.fetchall()
        
        if not applications:
            await ctx.send("📭 Нет активных заявок на вступление.")
            return
        
        class ApplicationView(discord.ui.View):
            def __init__(self, applications, clan_id, db, guild):
                super().__init__(timeout=60)
                self.applications = applications
                self.current_index = 0
                self.clan_id = clan_id
                self.db = db
                self.guild = guild
            
            async def update_embed(self, interaction):
                app = self.applications[self.current_index]
                user = self.guild.get_member(app[2])
                
                embed = discord.Embed(
                    title=f"📨 Заявка #{self.current_index + 1} из {len(self.applications)}",
                    color=0xf1c40f
                )
                
                if user:
                    embed.set_author(name=user.display_name, icon_url=user.avatar.url if user.avatar else None)
                    embed.add_field(name="👤 Пользователь", value=user.mention, inline=True)
                    embed.add_field(name="💰 Баланс", value=f"{app[8]} монет", inline=True)
                else:
                    embed.add_field(name="👤 Пользователь", value=f"Не в сервере ({app[2]})", inline=True)
                
                embed.add_field(name="📝 Сообщение", value=app[4] or "Не указано", inline=False)
                embed.add_field(name="📅 Дата подачи", 
                              value=f"<t:{app[7]}:R>", inline=True)
                
                return embed
            
            @discord.ui.button(label="⬅️ Предыдущая", style=discord.ButtonStyle.secondary)
            async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("❌ Вы не можете управлять этими заявками!", ephemeral=True)
                    return
                
                self.current_index = (self.current_index - 1) % len(self.applications)
                embed = await self.update_embed(interaction)
                
                self.children[0].disabled = (len(self.applications) <= 1)
                self.children[1].disabled = (len(self.applications) <= 1)
                
                await interaction.response.edit_message(embed=embed, view=self)
            
            @discord.ui.button(label="Следующая ➡️", style=discord.ButtonStyle.secondary)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("❌ Вы не можете управлять этими заявки!", ephemeral=True)
                    return
                
                self.current_index = (self.current_index + 1) % len(self.applications)
                embed = await self.update_embed(interaction)
                
                self.children[0].disabled = (len(self.applications) <= 1)
                self.children[1].disabled = (len(self.applications) <= 1)
                
                await interaction.response.edit_message(embed=embed, view=self)
            
            @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success)
            async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("❌ Вы не можете управлять этими заявками!", ephemeral=True)
                    return
                
                app = self.applications[self.current_index]
                user = self.guild.get_member(app[2])
                
                if not user:
                    await interaction.response.send_message("❌ Пользователь не найден на сервере!", ephemeral=True)
                    return
                
                cursor = self.db.conn.cursor()
                cursor.execute('''
                    INSERT INTO clan_members (user_id, guild_id, clan_id, role, joined_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user.id, self.guild.id, self.clan_id, 'member', int(datetime.now().timestamp())))
                
                cursor.execute('SELECT role_id FROM clans WHERE clan_id = ?', (self.clan_id,))
                role_result = cursor.fetchone()
                role_id = role_result[0] if role_result else None
                if role_id:
                    role = self.guild.get_role(role_id)
                    if role:
                        try:
                            await user.add_roles(role)
                        except:
                            pass
                
                cursor.execute('UPDATE clan_applications SET status = ? WHERE application_id = ?', 
                              ('approved', app[0]))
                
                self.db.conn.commit()
                
                self.applications.pop(self.current_index)
                if self.applications:
                    self.current_index = self.current_index % len(self.applications)
                    embed = await self.update_embed(interaction)
                    await interaction.response.edit_message(
                        content=f"✅ {user.mention} принят в клан!",
                        embed=embed,
                        view=self
                    )
                else:
                    await interaction.response.edit_message(
                        content=f"✅ {user.mention} принят в клан!\n\n📭 Больше нет активных заявок.",
                        embed=None,
                        view=None
                    )

                    cursor.execute('SELECT COUNT(*) FROM clan_members WHERE clan_id = ?', (self.clan_id,))
                    member_count = cursor.fetchone()[0]

                    achievements_cog = self.db.bot.get_cog('Achievements')
                    if achievements_cog:
                        cursor.execute('SELECT user_id FROM clan_members WHERE clan_id = ?', (self.clan_id,))
                        members = cursor.fetchall()
                        for member in members:
                            user_id = member[0]
                            await achievements_cog.check_achievements(user_id, self.guild.id, 'clan_members', member_count)
            
            @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger)
            async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("❌ Вы не можете управлять этими заявками!", ephemeral=True)
                    return
                
                app = self.applications[self.current_index]
                user = self.guild.get_member(app[2])
                
                cursor = self.db.conn.cursor()
                cursor.execute('UPDATE clan_applications SET status = ? WHERE application_id = ?', 
                              ('rejected', app[0]))
                self.db.conn.commit()
                
                self.applications.pop(self.current_index)
                if self.applications:
                    self.current_index = self.current_index % len(self.applications)
                    embed = await self.update_embed(interaction)
                    await interaction.response.edit_message(
                        content=f"❌ Заявка от {user.mention if user else 'пользователя'} отклонена!",
                        embed=embed,
                        view=self
                    )
                else:
                    await interaction.response.edit_message(
                        content=f"❌ Заявка от {user.mention if user else 'пользователя'} отклонена!\n\n📭 Больше нет активных заявок.",
                        embed=None,
                        view=None
                    )
        
        view = ApplicationView(applications, clan_id, self.db, ctx.guild)
        
        if len(applications) <= 1:
            view.children[0].disabled = True
            view.children[1].disabled = True
        
        embed = await view.update_embed(None)
        await ctx.send(embed=embed, view=view)
    
    @clan_group.command(name='transfer', description='Передать владение кланом')
    @app_commands.describe(member='Новый владелец клана')
    async def clan_transfer(self, ctx, member: discord.Member):
        """Передать владение кланом"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        if user_clan[3] != 'owner':
            await ctx.send("❌ Только владелец может передать клан!", ephemeral=True)
            return
        
        target_clan = self.get_user_clan(member.id, ctx.guild.id)
        if not target_clan or target_clan[2] != user_clan[2]:
            await ctx.send(f"❌ {member.mention} не состоит в вашем клане!", ephemeral=True)
            return
        
        clan_id = user_clan[2]
        
        embed = discord.Embed(
            title="⚠️ Передача владения кланом",
            description=f"Вы уверены, что хотите передать клан **{user_clan[5]}** пользователю {member.mention}?\n\nПосле передачи вы станете совладельцем.",
            color=0xe74c3c
        )
        
        view = discord.ui.View(timeout=30)
        
        async def confirm_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ Это не ваше подтверждение!", ephemeral=True)
                return
            
            cursor = self.db.conn.cursor()
            
            cursor.execute('UPDATE clans SET owner_id = ? WHERE clan_id = ?', (member.id, clan_id))
            
            cursor.execute('UPDATE clan_members SET role = ? WHERE user_id = ? AND clan_id = ?', 
                          ('coowner', ctx.author.id, clan_id))
            cursor.execute('UPDATE clan_members SET role = ? WHERE user_id = ? AND clan_id = ?', 
                          ('owner', member.id, clan_id))
            
            self.db.conn.commit()
            
            await interaction.response.edit_message(
                content=f"✅ Владение кланом **{user_clan[5]}** передано {member.mention}!",
                embed=None,
                view=None
            )
        
        async def cancel_callback(interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ Это не ваше подтверждение!", ephemeral=True)
                return
            
            await interaction.response.edit_message(
                content="❌ Передача владения отменена.",
                embed=None,
                view=None
            )
        
        confirm_btn = discord.ui.Button(label="✅ Да, передать", style=discord.ButtonStyle.danger)
        confirm_btn.callback = confirm_callback
        view.add_item(confirm_btn)
        
        cancel_btn = discord.ui.Button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = cancel_callback
        view.add_item(cancel_btn)
        
        await ctx.send(embed=embed, view=view)
    
    @clan_group.command(name='list', description='Список всех кланов на сервере')
    @app_commands.describe(page='Номер страницы')
    async def clan_list(self, ctx, page: int = 1):
        """Показать список всех кланов"""
        try:
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM clans WHERE guild_id = ?', (ctx.guild.id,))
            total_clans = cursor.fetchone()[0]
            
            if total_clans == 0:
                await ctx.send("🏰 На этом сервере пока нет кланов.")
                return
            
            items_per_page = 6
            total_pages = max(1, (total_clans + items_per_page - 1) // items_per_page)
            
            if page < 1 or page > total_pages:
                await ctx.send(f"❌ Страница должна быть от 1 до {total_pages}!", ephemeral=True)
                return
            
            offset = (page - 1) * items_per_page
            
            cursor.execute('''
                SELECT c.clan_id, c.name, c.description, c.clan_type, c.bank, 
                       COUNT(cm.user_id) as member_count
                FROM clans c
                LEFT JOIN clan_members cm ON c.clan_id = cm.clan_id
                WHERE c.guild_id = ?
                GROUP BY c.clan_id
                ORDER BY c.bank DESC, member_count DESC
                LIMIT ? OFFSET ?
            ''', (ctx.guild.id, items_per_page, offset))
            
            clans = cursor.fetchall()
            
            embed = discord.Embed(
                title=f"🏰 Список кланов сервера (Страница {page}/{total_pages})",
                description=f"Всего кланов: {total_clans}",
                color=0x3498db
            )
            
            clan_emojis = {'open': '🔓', 'closed': '🔒', 'application': '📝'}
            
            for clan in clans:
                clan_id, name, description, clan_type, bank, members = clan
                
                short_desc = description[:50] + "..." if description and len(description) > 50 else description or "Нет описания"
                
                embed.add_field(
                    name=f"{clan_emojis.get(clan_type, '🏰')} {name}",
                    value=f"**ID:** {clan_id}\n"
                          f"**👥 Участники:** {members}\n"
                          f"**💰 Банк:** {bank} монет\n"
                          f"**📝** {short_desc}",
                    inline=True
                )
            
            embed.set_footer(text="Используйте /clan info [название] для подробной информации")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Ошибка при получении списка кланов: {e}", ephemeral=True)
    
    @clan_group.command(name='setrole', description='Назначить/изменить роль участника')
    @app_commands.describe(
        member='Участник клана',
        role='Роль (owner, coowner, member)'
    )
    async def clan_setrole(self, ctx, member: discord.Member, role: str):
        """Назначить роль участнику клана"""
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        if user_clan[3] != 'owner':
            await ctx.send("❌ Только владелец может изменять роли!", ephemeral=True)
            return
        
        if role.lower() not in ['owner', 'coowner', 'member']:
            await ctx.send("❌ Неверная роль! Доступные: owner, coowner, member", ephemeral=True)
            return
        
        target_clan = self.get_user_clan(member.id, ctx.guild.id)
        if not target_clan or target_clan[2] != user_clan[2]:
            await ctx.send(f"❌ {member.mention} не состоит в вашем клане!", ephemeral=True)
            return
        
        clan_id = user_clan[2]
        
        if target_clan[3] == 'owner' and role.lower() != 'owner':
            await ctx.send("❌ Нельзя изменить роль владельца! Используйте /clan transfer.", ephemeral=True)
            return
        
        cursor = self.db.conn.cursor()
        cursor.execute('UPDATE clan_members SET role = ? WHERE user_id = ? AND clan_id = ?', 
                      (role.lower(), member.id, clan_id))
        self.db.conn.commit()
        
        role_names = {
            'owner': '👑 Владелец',
            'coowner': '👥 Совладелец',
            'member': '👤 Участник'
        }
        
        await ctx.send(f"✅ Роль {member.mention} изменена на **{role_names[role.lower()]}**!")
    
    @clan_group.command(name='memberstats', description='Статистика участника клана')
    @app_commands.describe(member='Участник клана')
    async def clan_memberstats(self, ctx, member: discord.Member):
        """Показать статистику участника клана"""
        # Проверяем, состоит ли участник в том же клане
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        target_clan = self.get_user_clan(member.id, ctx.guild.id)
        
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        if not target_clan or target_clan[2] != user_clan[2]:
            await ctx.send(f"❌ {member.mention} не состоит в вашем клане!", ephemeral=True)
            return
        
        clan_id = user_clan[2]
        
        # Получаем статистику участника
        stats = self.db.get_clan_member_stats(member.id, ctx.guild.id, clan_id)
        
        if not stats:
            await ctx.send("❌ Статистика участника не найдена!", ephemeral=True)
            return
        
        # Получаем информацию о клане
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT name FROM clans WHERE clan_id = ?', (clan_id,))
        clan_result = cursor.fetchone()
        clan_name = clan_result[0] if clan_result else "Неизвестный клан"
        
        # Рассчитываем ранги
        cursor.execute('''
            SELECT user_id, total_deposited 
            FROM clan_member_stats 
            WHERE clan_id = ? 
            ORDER BY total_deposited DESC
        ''', (clan_id,))
        
        all_members = cursor.fetchall()
        deposit_rank = next((i+1 for i, (uid, _) in enumerate(all_members) if uid == member.id), len(all_members))
        
        cursor.execute('''
            SELECT user_id, xp_contributed 
            FROM clan_member_stats 
            WHERE clan_id = ? 
            ORDER BY xp_contributed DESC
        ''', (clan_id,))
        
        all_members_xp = cursor.fetchall()
        xp_rank = next((i+1 for i, (uid, _) in enumerate(all_members_xp) if uid == member.id), len(all_members_xp))
        
        # Создаем embed
        embed = discord.Embed(
            title=f"📊 Статистика участника: {member.display_name}",
            color=member.color
        )
        
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        
        # Основная информация
        embed.add_field(
            name="👤 Информация",
            value=f"**Роль в клане:** {target_clan[3].capitalize()}\n"
                  f"**В клане с:** <t:{target_clan[4]}:D>\n"
                  f"**Последняя активность:** <t:{stats[9] if stats[9] else target_clan[4]}:R>",
            inline=True
        )
        
        # Финансовая статистика
        total_deposited = stats[3] or 0
        days_in_clan = max(1, (datetime.now().timestamp() - target_clan[4]) // 86400)
        
        embed.add_field(
            name="💰 Финансы",
            value=f"**Всего внесено:** {total_deposited:,} монет\n"
                  f"**Рейтинг по вкладу:** #{deposit_rank}\n"
                  f"**Средний вклад:** {int(total_deposited // days_in_clan):,}/день",
            inline=True
        )
        
        # Статистика активности
        messages_count = stats[4] or 0
        voice_minutes = stats[5] or 0
        commands_used = stats[6] or 0
        
        embed.add_field(
            name="💬 Активность",
            value=f"**Сообщений:** {messages_count:,}\n"
                  f"**Голосовых минут:** {voice_minutes:,}\n"
                  f"**Команд использовано:** {commands_used:,}",
            inline=True
        )
        
        # Вклад в опыт клана
        xp_contributed = stats[8] or 0
        
        # Получаем общий опыт клана
        cursor.execute('SELECT xp FROM clan_xp WHERE clan_id = ?', (clan_id,))
        clan_xp_result = cursor.fetchone()
        total_clan_xp = clan_xp_result[0] if clan_xp_result else 1
        
        embed.add_field(
            name="✨ Вклад в опыт",
            value=f"**Всего вложил:** {xp_contributed:,} XP\n"
                  f"**Рейтинг по XP:** #{xp_rank}\n"
                  f"**Доля в общем XP:** {xp_contributed / max(1, total_clan_xp) * 100:.1f}%",
            inline=True
        )
        
        # Процентное соотношение
        total_members = len(all_members)
        deposit_percentile = ((total_members - deposit_rank + 1) / total_members * 100) if total_members > 0 else 0
        xp_percentile = ((total_members - xp_rank + 1) / total_members * 100) if total_members > 0 else 0
        
        embed.add_field(
            name="📈 Процентили",
            value=f"**По вкладу:** Лучше {deposit_percentile:.1f}% участников\n"
                  f"**По опыту:** Лучше {xp_percentile:.1f}% участников\n"
                  f"**Общий ранг:** {min(deposit_rank, xp_rank)}/{total_members}",
            inline=True
        )
        
        embed.set_footer(text=f"Клан: {clan_name}")
        
        await ctx.send(embed=embed)
    
    @clan_group.command(name='xp_events', description='История получения опыта кланом')
    @app_commands.describe(
        days='За сколько дней показать историю (макс. 30)',
        page='Номер страницы'
    )
    async def clan_xp_events(self, ctx, days: int = 7, page: int = 1):
        """Показать историю получения опыта кланом"""
        if days < 1 or days > 30:
            await ctx.send("❌ Количество дней должно быть от 1 до 30!", ephemeral=True)
            return
        
        user_clan = self.get_user_clan(ctx.author.id, ctx.guild.id)
        if not user_clan:
            await ctx.send("❌ Вы не состоите в клане!", ephemeral=True)
            return
        
        clan_id = user_clan[2]
        
        # Рассчитываем временной диапазон
        cutoff_time = int(datetime.now().timestamp()) - (days * 86400)
        
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM clan_xp_events 
            WHERE clan_id = ? AND created_at >= ?
        ''', (clan_id, cutoff_time))
        
        total_events = cursor.fetchone()[0]
        
        if total_events == 0:
            await ctx.send(f"📭 За последние {days} дней не было событий с получением опыта.")
            return
        
        items_per_page = 10
        total_pages = max(1, (total_events + items_per_page - 1) // items_per_page)
        
        if page < 1 or page > total_pages:
            await ctx.send(f"❌ Страница должна быть от 1 до {total_pages}!", ephemeral=True)
            return
        
        offset = (page - 1) * items_per_page
        
        cursor.execute('''
            SELECT cxe.*, u.balance as user_balance
            FROM clan_xp_events cxe
            LEFT JOIN users u ON cxe.user_id = u.user_id AND u.guild_id = ?
            WHERE cxe.clan_id = ? AND cxe.created_at >= ?
            ORDER BY cxe.created_at DESC
            LIMIT ? OFFSET ?
        ''', (ctx.guild.id, clan_id, cutoff_time, items_per_page, offset))
        
        events = cursor.fetchall()
        
        # Эмодзи для типов событий
        type_emojis = {
            "member_join": "👥",
            "deposit": "💰",
            "message": "💬",
            "voice_minute": "🔊",
            "command": "⚡",
            "achievement": "🏆",
            "level_up": "📈",
            "daily": "🎁",
            "work": "💼",
            "other": "✨"
        }
        
        # Названия типов событий
        type_names = {
            "member_join": "Новый участник",
            "deposit": "Вклад в банк",
            "message": "Сообщение",
            "voice_minute": "Время в голосовом",
            "command": "Использование команды",
            "achievement": "Получение достижения",
            "level_up": "Повышение уровня",
            "daily": "Ежедневная награда",
            "work": "Работа",
            "other": "Другое"
        }
        
        embed = discord.Embed(
            title=f"📝 История опыта клана {user_clan[5]}",
            description=f"События за последние {days} дней (Страница {page}/{total_pages})",
            color=0x9b59b6
        )
        
        total_xp = 0
        xp_by_type = defaultdict(int)
        
        for event in events:
            event_id, clan_id, user_id, event_type, xp_amount, details, created_at, user_balance = event
            
            emoji = type_emojis.get(event_type, "✨")
            type_name = type_names.get(event_type, "Неизвестно")
            
            user = ctx.guild.get_member(user_id) if user_id else None
            username = user.display_name if user else f"Пользователь ({user_id})"
            
            time_ago = f"<t:{created_at}:R>"
            
            embed.add_field(
                name=f"{emoji} {type_name}",
                value=f"**Участник:** {username}\n"
                      f"**Опыт:** +{xp_amount} XP\n"
                      f"**Время:** {time_ago}\n"
                      f"**Детали:** {details[:50]}{'...' if len(details) > 50 else ''}",
                inline=False
            )
            
            total_xp += xp_amount
            xp_by_type[event_type] += xp_amount
        
        # Статистика по типам событий
        stats_text = ""
        for event_type, xp in sorted(xp_by_type.items(), key=lambda x: x[1], reverse=True)[:5]:
            emoji = type_emojis.get(event_type, "✨")
            type_name = type_names.get(event_type, "Неизвестно")
            percentage = (xp / total_xp * 100) if total_xp > 0 else 0
            stats_text += f"{emoji} {type_name}: **{xp} XP** ({percentage:.1f}%)\n"
        
        if stats_text:
            embed.add_field(
                name="📊 Статистика по типам",
                value=stats_text,
                inline=False
            )
        
        embed.set_footer(text=f"Всего событий: {total_events} | Всего опыта: {total_xp} XP")
        
        await ctx.send(embed=embed)

    # АДМИН КОМАНДЫ
    @commands.hybrid_group(name='clanadmin', description='Админ команды для управления кланами', with_app_command=True)
    @has_permission('high_admin', 'admin', 'owner')
    async def clanadmin(self, ctx):
        """Группа админ команд для кланов"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @clanadmin.command(name='addxp', description='Добавить опыт клану')
    @app_commands.describe(
        clan='Название или ID клана',
        xp='Количество XP для добавления',
        reason='Причина (необязательно)'
    )
    @has_permission('high_admin', 'admin', 'owner')
    async def clanadmin_addxp(self, ctx, clan: str, xp: int, reason: Optional[str] = None):
        """Добавить опыт клану"""
        if xp <= 0:
            await ctx.send("❌ Количество XP должно быть положительным!", ephemeral=True)
            return
        
        # Ищем клан по имени или ID
        cursor = self.db.conn.cursor()
        if clan.isdigit():
            cursor.execute('''
                SELECT clan_id, name FROM clans 
                WHERE guild_id = ? AND clan_id = ?
            ''', (ctx.guild.id, int(clan)))
        else:
            cursor.execute('''
                SELECT clan_id, name FROM clans 
                WHERE guild_id = ? AND name LIKE ?
            ''', (ctx.guild.id, f"%{clan}%"))
        
        result = cursor.fetchone()
        if not result:
            await ctx.send("❌ Клан не найден!", ephemeral=True)
            return
        
        clan_id, clan_name = result
        
        # Добавляем XP
        new_level, reward = await self.add_clan_xp(
            clan_id, xp, ctx.author.id,
            event_type="admin_add",
            details=f"Админ добавление: {reason or 'Без причины'}"
        )
        
        embed = discord.Embed(
            title="✅ Опыт добавлен клану",
            description=f"Клану **{clan_name}** добавлено **{xp} XP**",
            color=0x00ff00
        )
        
        embed.add_field(name="👤 Администратор", value=ctx.author.mention, inline=True)
        embed.add_field(name="📝 Причина", value=reason or "Не указана", inline=True)
        
        if new_level:
            embed.add_field(
                name="🎉 Новый уровень!",
                value=f"Клан достиг **{new_level}** уровня!",
                inline=False
            )
        
        # Получаем текущую информацию об опыте
        xp_info = self.db.get_clan_level_info(clan_id)
        if xp_info:
            current_level = xp_info[2] or 1
            current_xp = xp_info[1] or 0
            
            embed.add_field(
                name="📊 Текущее состояние",
                value=f"**Уровень:** {current_level}\n**Опыт:** {current_xp:,} XP",
                inline=False
            )
        
        embed.set_footer(text=f"ID клана: {clan_id}")
        
        await ctx.send(embed=embed)
    
    @clanadmin.command(name='removexp', description='Убрать опыт у клана')
    @app_commands.describe(
        clan='Название или ID клана',
        xp='Количество XP для удаления',
        reason='Причина (необязательно)'
    )
    @has_permission('high_admin', 'admin', 'owner')
    async def clanadmin_removexp(self, ctx, clan: str, xp: int, reason: Optional[str] = None):
        """Убрать опыт у клана"""
        if xp <= 0:
            await ctx.send("❌ Количество XP должно быть положительным!", ephemeral=True)
            return
        
        # Ищем клан по имени или ID
        cursor = self.db.conn.cursor()
        if clan.isdigit():
            cursor.execute('''
                SELECT clan_id, name, cx.xp FROM clans c
                LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                WHERE c.guild_id = ? AND c.clan_id = ?
            ''', (ctx.guild.id, int(clan)))
        else:
            cursor.execute('''
                SELECT c.clan_id, c.name, cx.xp FROM clans c
                LEFT JOIN clan_xp cx ON c.clan_id = cx.clan_id
                WHERE c.guild_id = ? AND c.name LIKE ?
            ''', (ctx.guild.id, f"%{clan}%"))
        
        result = cursor.fetchone()
        if not result:
            await ctx.send("❌ Клан не найден!", ephemeral=True)
            return
        
        clan_id, clan_name, current_xp = result
        current_xp = current_xp or 0
        
        # Проверяем, чтобы не уйти в минус
        if xp > current_xp:
            xp = current_xp
            if xp == 0:
                await ctx.send("❌ У клана нет опыта для удаления!", ephemeral=True)
                return
        
        # Убираем XP (добавляем отрицательное значение)
        new_level, reward = await self.add_clan_xp(
            clan_id, -xp, ctx.author.id,
            event_type="admin_remove",
            details=f"Админ удаление: {reason or 'Без причины'}"
        )
        
        embed = discord.Embed(
            title="✅ Опыт убран у клана",
            description=f"У клана **{clan_name}** убрано **{xp} XP**",
            color=0xff9900
        )
        
        embed.add_field(name="👤 Администратор", value=ctx.author.mention, inline=True)
        embed.add_field(name="📝 Причина", value=reason or "Не указана", inline=True)
        
        # Получаем обновленную информацию об опыте
        xp_info = self.db.get_clan_level_info(clan_id)
        if xp_info:
            new_level_value = xp_info[2] or 1
            new_xp = xp_info[1] or 0
            
            embed.add_field(
                name="📊 Текущее состояние",
                value=f"**Уровень:** {new_level_value}\n**Опыт:** {new_xp:,} XP",
                inline=False
            )
        
        embed.set_footer(text=f"ID клана: {clan_id}")
        
        await ctx.send(embed=embed)
    
    @clanadmin.command(name='setlevel', description='Установить уровень клану')
    @app_commands.describe(
        clan='Название или ID клана',
        level='Новый уровень',
        reason='Причина (необязательно)'
    )
    @has_permission('high_admin', 'admin', 'owner')
    async def clanadmin_setlevel(self, ctx, clan: str, level: int, reason: Optional[str] = None):
        """Установить уровень клану"""
        if level < 1:
            await ctx.send("❌ Уровень должен быть положительным!", ephemeral=True)
            return
        
        if level > 100:
            await ctx.send("❌ Уровень не может быть больше 100!", ephemeral=True)
            return
        
        # Ищем клан по имени или ID
        cursor = self.db.conn.cursor()
        if clan.isdigit():
            cursor.execute('''
                SELECT clan_id, name FROM clans 
                WHERE guild_id = ? AND clan_id = ?
            ''', (ctx.guild.id, int(clan)))
        else:
            cursor.execute('''
                SELECT clan_id, name FROM clans 
                WHERE guild_id = ? AND name LIKE ?
            ''', (ctx.guild.id, f"%{clan}%"))
        
        result = cursor.fetchone()
        if not result:
            await ctx.send("❌ Клан не найден!", ephemeral=True)
            return
        
        clan_id, clan_name = result
        
        # Рассчитываем XP для нужного уровня
        # Формула: level = floor(sqrt(xp / 100))
        # Обратная: xp = (level ** 2) * 100
        required_xp = (level ** 2) * 100
        
        # Получаем текущий XP
        cursor.execute('SELECT xp FROM clan_xp WHERE clan_id = ?', (clan_id,))
        current_xp_result = cursor.fetchone()
        current_xp = current_xp_result[0] if current_xp_result else 0
        
        # Рассчитываем разницу
        xp_difference = required_xp - current_xp
        
        if xp_difference == 0:
            await ctx.send("❌ Клан уже имеет этот уровень!", ephemeral=True)
            return
        
        event_type = "admin_setlevel_add" if xp_difference > 0 else "admin_setlevel_remove"
        
        # Обновляем XP
        new_level, reward = await self.add_clan_xp(
            clan_id, xp_difference, ctx.author.id,
            event_type=event_type,
            details=f"Установка уровня {level}: {reason or 'Без причины'}"
        )
        
        embed = discord.Embed(
            title="✅ Уровень клана установлен",
            description=f"Клану **{clan_name}** установлен **{level}** уровень",
            color=0x9b59b6
        )
        
        embed.add_field(name="👤 Администратор", value=ctx.author.mention, inline=True)
        embed.add_field(name="📝 Причина", value=reason or "Не указана", inline=True)
        
        if xp_difference > 0:
            embed.add_field(name="✨ Добавлено XP", value=f"+{xp_difference} XP", inline=True)
        else:
            embed.add_field(name="✨ Убрано XP", value=f"{xp_difference} XP", inline=True)
        
        embed.add_field(
            name="📊 Текущее состояние",
            value=f"**Уровень:** {level}\n**Опыт:** {required_xp:,} XP",
            inline=False
        )
        
        embed.set_footer(text=f"ID клана: {clan_id}")
        
        await ctx.send(embed=embed)
    
    @clanadmin.command(name='setxp', description='Установить точное количество XP клану')
    @app_commands.describe(
        clan='Название или ID клана',
        xp='Новое количество XP',
        reason='Причина (необязательно)'
    )
    @has_permission('high_admin', 'admin', 'owner')
    async def clanadmin_setxp(self, ctx, clan: str, xp: int, reason: Optional[str] = None):
        """Установить точное количество XP клану"""
        if xp < 0:
            await ctx.send("❌ XP не может быть отрицательным!", ephemeral=True)
            return
        
        # Ищем клан по имени или ID
        cursor = self.db.conn.cursor()
        if clan.isdigit():
            cursor.execute('''
                SELECT clan_id, name FROM clans 
                WHERE guild_id = ? AND clan_id = ?
            ''', (ctx.guild.id, int(clan)))
        else:
            cursor.execute('''
                SELECT clan_id, name FROM clans 
                WHERE guild_id = ? AND name LIKE ?
            ''', (ctx.guild.id, f"%{clan}%"))
        
        result = cursor.fetchone()
        if not result:
            await ctx.send("❌ Клан не найден!", ephemeral=True)
            return
        
        clan_id, clan_name = result
        
        # Получаем текущий XP
        cursor.execute('SELECT xp FROM clan_xp WHERE clan_id = ?', (clan_id,))
        current_xp_result = cursor.fetchone()
        current_xp = current_xp_result[0] if current_xp_result else 0
        
        # Рассчитываем разницу
        xp_difference = xp - current_xp
        
        if xp_difference == 0:
            await ctx.send("❌ Клан уже имеет это количество XP!", ephemeral=True)
            return
        
        event_type = "admin_setxp_add" if xp_difference > 0 else "admin_setxp_remove"
        
        # Обновляем XP
        new_level, reward = await self.add_clan_xp(
            clan_id, xp_difference, ctx.author.id,
            event_type=event_type,
            details=f"Установка XP {xp}: {reason or 'Без причины'}"
        )
        
        # Рассчитываем уровень для нового XP
        new_level_calculated = int((xp / 100) ** 0.5) if xp > 0 else 1
        
        embed = discord.Embed(
            title="✅ XP клана установлено",
            description=f"Клану **{clan_name}** установлено **{xp:,} XP**",
            color=0x9b59b6
        )
        
        embed.add_field(name="👤 Администратор", value=ctx.author.mention, inline=True)
        embed.add_field(name="📝 Причина", value=reason or "Не указана", inline=True)
        
        if xp_difference > 0:
            embed.add_field(name="✨ Добавлено XP", value=f"+{xp_difference} XP", inline=True)
        else:
            embed.add_field(name="✨ Убрано XP", value=f"{xp_difference} XP", inline=True)
        
        embed.add_field(
            name="📊 Текущее состояние",
            value=f"**Уровень:** {new_level_calculated}\n**Опыт:** {xp:,} XP",
            inline=False
        )
        
        if new_level:
            embed.add_field(
                name="🎉 Изменение уровня!",
                value=f"Клан изменил уровень на **{new_level}**!",
                inline=False
            )
        
        embed.set_footer(text=f"ID клана: {clan_id}")
        
        await ctx.send(embed=embed)
    
    @clanadmin.command(name='resetstats', description='Сбросить статистику участника клана')
    @app_commands.describe(
        clan='Название или ID клана',
        member='Участник (необязательно, если не указан - сбросить всю статистику клана)',
        reset_type='Что сбросить (all, deposits, activity, xp)'
    )
    @has_permission('high_admin', 'admin', 'owner')
    async def clanadmin_resetstats(self, ctx, clan: str, reset_type: str = 'all', member: Optional[discord.Member] = None):
        """Сбросить статистику клана или участника"""
        valid_reset_types = ['all', 'deposits', 'activity', 'xp']
        if reset_type.lower() not in valid_reset_types:
            await ctx.send(f"❌ Неверный тип сброса! Доступные: {', '.join(valid_reset_types)}", ephemeral=True)
            return
        
        # Ищем клан по имени или ID
        cursor = self.db.conn.cursor()
        if clan.isdigit():
            cursor.execute('''
                SELECT clan_id, name FROM clans 
                WHERE guild_id = ? AND clan_id = ?
            ''', (ctx.guild.id, int(clan)))
        else:
            cursor.execute('''
                SELECT clan_id, name FROM clans 
                WHERE guild_id = ? AND name LIKE ?
            ''', (ctx.guild.id, f"%{clan}%"))
        
        result = cursor.fetchone()
        if not result:
            await ctx.send("❌ Клан не найден!", ephemeral=True)
            return
        
        clan_id, clan_name = result
        
        try:
            cursor.execute("BEGIN TRANSACTION")
            
            if member:
                # Проверяем, состоит ли участник в клане
                cursor.execute('''
                    SELECT user_id FROM clan_members 
                    WHERE clan_id = ? AND user_id = ?
                ''', (clan_id, member.id))
                
                if not cursor.fetchone():
                    await ctx.send(f"❌ {member.mention} не состоит в этом клане!", ephemeral=True)
                    return
                
                # Сбрасываем статистику конкретного участника
                reset_queries = []
                
                if reset_type in ['all', 'deposits']:
                    reset_queries.append('total_deposited = 0')
                
                if reset_type in ['all', 'activity']:
                    reset_queries.append('messages_count = 0')
                    reset_queries.append('voice_minutes = 0')
                    reset_queries.append('commands_used = 0')
                
                if reset_type in ['all', 'xp']:
                    reset_queries.append('xp_contributed = 0')
                
                if reset_queries:
                    query = f'''
                        UPDATE clan_member_stats 
                        SET {', '.join(reset_queries)}
                        WHERE clan_id = ? AND user_id = ?
                    '''
                    cursor.execute(query, (clan_id, member.id))
                
                embed = discord.Embed(
                    title="✅ Статистика участника сброшена",
                    description=f"Статистика участника {member.mention} в клане **{clan_name}** сброшена",
                    color=0x00ff00
                )
                embed.add_field(name="📊 Тип сброса", value=reset_type.capitalize(), inline=True)
                embed.add_field(name="👤 Администратор", value=ctx.author.mention, inline=True)
                
            else:
                # Сбрасываем всю статистику клана
                if reset_type in ['all', 'deposits']:
                    cursor.execute('''
                        UPDATE clan_member_stats 
                        SET total_deposited = 0 
                        WHERE clan_id = ?
                    ''', (clan_id,))
                
                if reset_type in ['all', 'activity']:
                    cursor.execute('''
                        UPDATE clan_member_stats 
                        SET messages_count = 0, voice_minutes = 0, commands_used = 0 
                        WHERE clan_id = ?
                    ''', (clan_id,))
                
                if reset_type in ['all', 'xp']:
                    cursor.execute('''
                        UPDATE clan_member_stats 
                        SET xp_contributed = 0 
                        WHERE clan_id = ?
                    ''', (clan_id,))
                
                embed = discord.Embed(
                    title="✅ Статистика клана сброшена",
                    description=f"Статистика клана **{clan_name}** сброшена",
                    color=0x00ff00
                )
                embed.add_field(name="📊 Тип сброса", value=reset_type.capitalize(), inline=True)
                embed.add_field(name="👤 Администратор", value=ctx.author.mention, inline=True)
            
            self.db.conn.commit()
            
            embed.set_footer(text=f"ID клана: {clan_id}")
            await ctx.send(embed=embed)
            
        except Exception as e:
            self.db.conn.rollback()
            await ctx.send(f"❌ Ошибка при сбросе статистики: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Clans(bot))