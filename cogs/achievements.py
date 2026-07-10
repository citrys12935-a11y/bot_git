import discord
from discord import app_commands
from discord.ext import commands
from utils.database import Database
from utils.checks import has_permission, check_permission
import random
from datetime import datetime
import os
import asyncio

class Achievements(commands.Cog):
    """Система достижений и баннеров"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.rarity_colors = {
            'common': 0x808080,
            'rare': 0x0099ff,
            'epic': 0x9b59b6,
            'legendary': 0xff9900,
            'exclusive': 0xff0000
        }
        self.rarity_emojis = {
            'common': '⚪',
            'rare': '🔵',
            'epic': '🟣',
            'legendary': '🟠',
            'exclusive': '🔴'
        }
        print("✅ Ког ачивок загружен")
    
    async def check_achievements(self, user_id, guild_id, achievement_type, value):
        """Проверка и выдача достижений"""
        print(f"🔍 Проверка ачивок: user={user_id}, guild={guild_id}, type={achievement_type}, value={value}")
        
        cursor = self.db.conn.cursor()
        
        # Получаем все достижения этого типа, которые пользователь еще не выполнил
        cursor.execute('''
            SELECT a.* FROM achievements a
            LEFT JOIN user_achievements ua ON a.achievement_id = ua.achievement_id 
                AND ua.user_id = ? AND ua.guild_id = ?
            WHERE a.guild_id = ? 
            AND a.requirement_type = ?
            AND a.requirement_value <= ?
            AND (ua.completed IS NULL OR ua.completed = 0)
        ''', (user_id, guild_id, guild_id, achievement_type, value))
        
        achievements = cursor.fetchall()
        
        print(f"📊 Найдено достижений для проверки: {len(achievements)}")
        
        for achievement in achievements:
            achievement_id = achievement[0]
            print(f"🎯 Проверяем достижение ID {achievement_id}: {achievement[2]}")
            
            # Проверяем, есть ли уже у пользователя это достижение
            cursor.execute('''
                SELECT * FROM user_achievements 
                WHERE user_id = ? AND guild_id = ? AND achievement_id = ?
            ''', (user_id, guild_id, achievement_id))
            
            existing = cursor.fetchone()
            
            if not existing:
                print(f"🎉 Выдаем достижение {achievement_id} пользователю {user_id}")
                cursor.execute('''
                    INSERT INTO user_achievements (user_id, guild_id, achievement_id, progress, completed, completed_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                ''', (user_id, guild_id, achievement_id, value, int(datetime.now().timestamp())))
                
                reward_currency = achievement[6]
                reward_xp = achievement[7]
                
                # Выдаем награды
                if reward_currency > 0:
                    print(f"💰 Выдаем {reward_currency} монет")
                    self.db.update_balance(user_id, guild_id, reward_currency)
                
                if reward_xp > 0:
                    print(f"⭐ Выдаем {reward_xp} опыта")
                    self.db.update_xp(user_id, guild_id, reward_xp)
                
                # Получаем информацию о сервере и пользователе
                guild = self.bot.get_guild(guild_id)
                if guild:
                    member = guild.get_member(user_id)
                    if member:
                        embed = discord.Embed(
                            title="🎉 Новое достижение!",
                            description=f"**{member.mention} получил достижение:**",
                            color=self.rarity_colors.get(achievement[5], 0x00ff00)
                        )
                        
                        embed.add_field(
                            name=f"{achievement[4]} {achievement[2]}", 
                            value=achievement[3],
                            inline=False
                        )
                        
                        embed.add_field(
                            name="Редкость", 
                            value=f"{self.rarity_emojis.get(achievement[5], '🏆')} {achievement[5].upper()}",
                            inline=True
                        )
                        
                        if reward_currency > 0:
                            embed.add_field(name="Награда", value=f"💰 {reward_currency} монет", inline=True)
                        
                        if reward_xp > 0:
                            embed.add_field(name="Опыт", value=f"⭐ {reward_xp} XP", inline=True)
                        
                        try:
                            # Пытаемся отправить в системный канал
                            channel = guild.system_channel
                            if channel and channel.permissions_for(guild.me).send_messages:
                                await channel.send(embed=embed)
                            else:
                                # Пытаемся отправить в ЛС
                                await member.send(embed=embed)
                        except Exception as e:
                            print(f"❌ Ошибка отправки уведомления: {e}")
            
            elif existing and not existing[5]:  # Если есть запись, но не завершено
                # Обновляем прогресс
                cursor.execute('''
                    UPDATE user_achievements 
                    SET progress = ? 
                    WHERE user_id = ? AND guild_id = ? AND achievement_id = ?
                ''', (value, user_id, guild_id, achievement_id))
                
                # Если достижение теперь выполнено
                if value >= achievement[9]:  # requirement_value
                    cursor.execute('''
                        UPDATE user_achievements 
                        SET completed = 1, completed_at = ?
                        WHERE user_id = ? AND guild_id = ? AND achievement_id = ?
                    ''', (int(datetime.now().timestamp()), user_id, guild_id, achievement_id))
                    
                    print(f"✅ Обновляем прогресс для ачивки {achievement_id}: {value}/{achievement[9]}")
        
        self.db.conn.commit()
        print(f"✅ Проверка ачивок завершена для типа {achievement_type}")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Счетчик сообщений для достижений"""
        if message.author.bot or not message.guild:
            return
        
        user_id = message.author.id
        guild_id = message.guild.id
        
        # Получаем текущее количество сообщений пользователя
        cursor = self.db.conn.cursor()
        
        # Получаем общее количество сообщений пользователя
        cursor.execute('''
            SELECT COALESCE(MAX(progress), 0) FROM user_achievements ua
            JOIN achievements a ON ua.achievement_id = a.achievement_id
            WHERE ua.user_id = ? AND ua.guild_id = ? AND a.requirement_type = 'messages'
        ''', (user_id, guild_id))
        
        result = cursor.fetchone()
        current_messages = result[0] + 1 if result else 1
        
        print(f"💬 Сообщение от {message.author.name}. Всего сообщений: {current_messages}")
        
        # Проверяем достижения по сообщениям
        await self.check_achievements(user_id, guild_id, 'messages', current_messages)
    
    @commands.Cog.listener()
    async def on_level_up(self, user_id, guild_id, level):
        """Обработчик повышения уровня"""
        await self.check_achievements(user_id, guild_id, 'level', level)
    
    @commands.hybrid_command(name='achievements', description='Список всех достижений сервера')
    async def show_achievements(self, ctx):
        """Показать все достижения сервера"""
        # Используем check_permission без await (она не асинхронная)
        is_admin = check_permission(ctx.author, ctx.guild, ['admin', 'high_admin', 'owner'])
        
        guild_id = ctx.guild.id
        
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM achievements WHERE guild_id = ? AND is_secret = 0 ORDER BY requirement_value ASC', 
                      (guild_id,))
        
        achievements = cursor.fetchall()
        
        if not achievements:
            embed = discord.Embed(
                title="🏆 Достижения сервера",
                description="Достижения еще не созданы.\nИспользуйте `/achievementadmin create` чтобы создать достижение.",
                color=0x808080
            )
            await ctx.send(embed=embed)
            return
        
        achievements_by_type = {}
        for ach in achievements:
            req_type = ach[8]
            if req_type not in achievements_by_type:
                achievements_by_type[req_type] = []
            achievements_by_type[req_type].append(ach)
        
        embed = discord.Embed(
            title="🏆 Все достижения сервера",
            description=f"Всего достижений: {len(achievements)}" + (f"\n👑 Вы видите ID (админ режим)" if is_admin else ""),
            color=0x00ff00
        )
        
        for req_type, type_achievements in achievements_by_type.items():
            text = ""
            for ach in type_achievements[:5]:  # Показываем первые 5 каждого типа
                rarity_emoji = self.rarity_emojis.get(ach[5], '🏆')
                reward_text = ""
                if ach[6] > 0:
                    reward_text += f"💰 {ach[6]} "
                if ach[7] > 0:
                    reward_text += f"⭐ {ach[7]}"
                
                # Для админов показываем ID
                if is_admin:
                    text += f"**ID: {ach[0]}** - {rarity_emoji} {ach[2]}\n"
                else:
                    text += f"**{rarity_emoji} {ach[2]}**\n"
                    
                text += f"▸ {ach[3]}\n"
                text += f"▸ Требование: `{req_type} {ach[9]}`\n"
                if reward_text:
                    text += f"▸ Награда: {reward_text}\n"
                text += "\n"
            
            if len(type_achievements) > 5:
                text += f"... и еще {len(type_achievements) - 5} достижений\n"
            
            type_names = {
                'level': '📊 Уровни',
                'balance': '💰 Баланс', 
                'messages': '💬 Сообщения',
                'work_count': '💼 Работа',
                'voice_time': '🎤 Голосовой чат',
                'slots_jackpot': '🎰 Слоты',
                'robbery_success': '🔪 Успешные ограбления',
                'robbery_fail': '💀 Неудачные ограбления',
                'clan_bank': '🏰 Банк клана',
                'clan_members': '👥 Участники клана'
            }
            
            embed.add_field(
                name=type_names.get(req_type, f"📋 {req_type}"),
                value=text or "Нет достижений",
                inline=False
            )
        
        cursor.execute('SELECT COUNT(*) FROM achievements WHERE guild_id = ? AND is_secret = 1', 
                      (guild_id,))
        secret_count = cursor.fetchone()[0]
        
        if secret_count > 0:
            embed.add_field(
                name="🔒 Секретные достижения",
                value=f"На сервере {secret_count} скрытых достижений.\nОткройте их, выполняя различные действия!",
                inline=False
            )
        
        if is_admin:
            embed.set_footer(text="Используйте /achievement [ID] для информации об ачивке")
        else:
            embed.set_footer(text="Используйте /profile для просмотра своих ачивок")
            
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='achievement', description='Информация о достижении')
    @app_commands.describe(achievement_id='ID достижения')
    async def achievement_info(self, ctx, achievement_id: int):
        """Информация о конкретном достижении"""
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM achievements WHERE achievement_id = ? AND guild_id = ?', 
                      (achievement_id, ctx.guild.id))
        
        achievement = cursor.fetchone()
        
        if not achievement:
            await ctx.send("❌ Достижение не найдено!", ephemeral=True)
            return
        
        # Распаковываем значения
        achievement_data = {
            'id': achievement[0],
            'guild_id': achievement[1],
            'name': achievement[2],
            'description': achievement[3],
            'icon': achievement[4],
            'rarity': achievement[5],
            'reward_currency': achievement[6],
            'reward_xp': achievement[7],
            'req_type': achievement[8],
            'req_value': achievement[9],
            'is_secret': achievement[10],
            'created_at': achievement[11]
        }
        
        embed = discord.Embed(
            title=f"{achievement_data['icon']} {achievement_data['name']}",
            description=achievement_data['description'],
            color=self.rarity_colors.get(achievement_data['rarity'], 0x00ff00)
        )
        
        embed.add_field(name="Редкость", value=f"{self.rarity_emojis.get(achievement_data['rarity'], '🏆')} {achievement_data['rarity'].upper()}", inline=True)
        embed.add_field(name="Тип требования", value=achievement_data['req_type'], inline=True)
        embed.add_field(name="Требуемое значение", value=achievement_data['req_value'], inline=True)
        
        if achievement_data['reward_currency'] > 0:
            embed.add_field(name="Награда в валюте", value=f"💰 {achievement_data['reward_currency']} монет", inline=True)
        
        if achievement_data['reward_xp'] > 0:
            embed.add_field(name="Награда в опыте", value=f"⭐ {achievement_data['reward_xp']} XP", inline=True)
        
        if achievement_data['is_secret']:
            embed.add_field(name="🔒 Секретное", value="Да", inline=True)
        
        cursor.execute('''
            SELECT COUNT(*) FROM user_achievements 
            WHERE achievement_id = ? AND completed = 1
        ''', (achievement_data['id'],))
        completed_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE guild_id = ?', (achievement_data['guild_id'],))
        total_users = cursor.fetchone()[0]
        
        percentage = (completed_count / total_users * 100) if total_users > 0 else 0
        embed.add_field(
            name="Статистика выполнения", 
            value=f"Получили: {completed_count}/{total_users} ({percentage:.1f}%)",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_group(name='achievementadmin', aliases=['aadmin'], description='Управление достижениями (админ)')
    @has_permission('admin', 'high_admin', 'owner')
    async def achievement_admin(self, ctx):
        """Группа команд для управления достижениями"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @achievement_admin.command(name='create', description='Создать новое достижение')
    @app_commands.describe(
        name='Название достижения',
        description='Описание достижения',
        icon='Эмодзи или текст иконки',
        rarity='Редкость (common, rare, epic, legendary)',
        requirement_type='Тип требования (level, balance, messages, work_count, voice_time)',
        requirement_value='Значение требования',
        reward_currency='Награда в валюте',
        reward_xp='Награда в опыте',
        is_secret='Секретное достижение'
    )
    async def create_achievement(self, ctx, name: str, description: str, icon: str = '🏆',
                               rarity: str = 'common', requirement_type: str = 'level', 
                               requirement_value: int = 1, reward_currency: int = 0, 
                               reward_xp: int = 0, is_secret: bool = False):
        """Создание нового достижения"""
        
        valid_rarities = ['common', 'rare', 'epic', 'legendary']
        valid_types = ['level', 'balance', 'messages', 'work_count', 'voice_time', 
                      'robbery_success', 'robbery_fail', 'clan_bank', 'clan_members']
        
        if rarity not in valid_rarities:
            await ctx.send(f"❌ Неверная редкость! Доступные: {', '.join(valid_rarities)}")
            return
        
        if requirement_type not in valid_types:
            valid_types_desc = {
                'level': 'Уровень',
                'balance': 'Баланс',
                'messages': 'Сообщения',
                'work_count': 'Работа',
                'voice_time': 'Время в голосовом чате',
                'robbery_success': 'Успешные ограбления',
                'robbery_fail': 'Неудачные ограбления',
                'clan_bank': 'Банк клана',
                'clan_members': 'Участники клана'
            }
            desc = "\n".join([f"- {t} ({valid_types_desc.get(t, t)})" for t in valid_types])
            await ctx.send(f"❌ Неверный тип требования! Доступные:\n{desc}", ephemeral=True)
            return
        
        cursor = self.db.conn.cursor()
        cursor.execute('''
            INSERT INTO achievements (guild_id, name, description, icon, rarity, reward_currency, 
                                    reward_xp, requirement_type, requirement_value, is_secret, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ctx.guild.id, name, description, icon, rarity, reward_currency, reward_xp, 
              requirement_type, requirement_value, 1 if is_secret else 0, int(datetime.now().timestamp())))
        
        self.db.conn.commit()
        achievement_id = cursor.lastrowid
        
        embed = discord.Embed(
            title="✅ Достижение создан!",
            description=f"ID: {achievement_id}",
            color=0x00ff00
        )
        
        embed.add_field(name="Название", value=f"{icon} {name}", inline=True)
        embed.add_field(name="Редкость", value=rarity.upper(), inline=True)
        embed.add_field(name="Требование", value=f"{requirement_type}: {requirement_value}", inline=True)
        embed.add_field(name="Награды", value=f"💰 {reward_currency} монет | ⭐ {reward_xp} XP", inline=True)
        embed.add_field(name="Секретное", value="Да" if is_secret else "Нет", inline=True)
        
        await ctx.send(embed=embed)
    
    @achievement_admin.command(name='give', description='Выдать достижение пользователю')
    @app_commands.describe(
        member='Пользователь',
        achievement_id='ID достижения'
    )
    async def give_achievement(self, ctx, member: discord.Member, achievement_id: int):
        """Выдать достижение пользователю"""
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM achievements WHERE achievement_id = ? AND guild_id = ?', 
                      (achievement_id, ctx.guild.id))
        
        achievement = cursor.fetchone()
        
        if not achievement:
            await ctx.send("❌ Достижение не найдено!", ephemeral=True)
            return
        
        cursor.execute('''
            SELECT * FROM user_achievements 
            WHERE user_id = ? AND guild_id = ? AND achievement_id = ?
        ''', (member.id, ctx.guild.id, achievement_id))
        
        if cursor.fetchone():
            await ctx.send("❌ У пользователя уже есть это достижение!", ephemeral=True)
            return
        
        cursor.execute('''
            INSERT INTO user_achievements (user_id, guild_id, achievement_id, completed, completed_at)
            VALUES (?, ?, ?, 1, ?)
        ''', (member.id, ctx.guild.id, achievement_id, int(datetime.now().timestamp())))
        
        reward_currency = achievement[6]
        reward_xp = achievement[7]
        
        if reward_currency > 0:
            self.db.update_balance(member.id, ctx.guild.id, reward_currency)
        
        if reward_xp > 0:
            self.db.update_xp(member.id, ctx.guild.id, reward_xp)
        
        self.db.conn.commit()
        
        embed = discord.Embed(
            title="✅ Достижение выдано!",
            description=f"{member.mention} получил достижение:",
            color=0x00ff00
        )
        
        embed.add_field(name="Достижение", value=f"{achievement[4]} {achievement[2]}", inline=True)
        embed.add_field(name="Награда", value=f"💰 {reward_currency} монет + ⭐ {reward_xp} XP", inline=True)
        
        await ctx.send(embed=embed)
    
    @achievement_admin.command(name='createbanner', description='Создать новый баннер')
    @app_commands.describe(
        name='Название баннера',
        image_url='URL изображения баннера',
        rarity='Редкость (common, rare, epic, legendary, exclusive)',
        price='Цена в магазине (0 - нельзя купить)',
        achievement_id='ID достижения для разблокировки (0 - без достижения)',
        is_default='Сделать баннером по умолчанию для новых игроков',
        is_exclusive='Эксклюзивный баннер (только для high_admin+)'
    )
    async def create_banner(self, ctx, name: str, image_url: str, rarity: str = 'common',
                           price: int = 0, achievement_id: int = 0, is_default: bool = False,
                           is_exclusive: bool = False):
        """Создание нового баннера"""
        
        valid_rarities = ['common', 'rare', 'epic', 'legendary', 'exclusive']
        
        if rarity not in valid_rarities:
            await ctx.send(f"❌ Неверная редкость! Доступные: {', '.join(valid_rarities)}")
            return
        
        if price < 0:
            await ctx.send("❌ Цена не может быть отрицательной!")
            return
        
        # Проверяем достижение, если указано
        if achievement_id > 0:
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT * FROM achievements WHERE achievement_id = ? AND guild_id = ?', 
                          (achievement_id, ctx.guild.id))
            if not cursor.fetchone():
                await ctx.send("❌ Достижение не найдено!")
                return
        
        # Проверяем, что эксклюзивные баннеры можно создавать только с правами high_admin+
        if is_exclusive and not check_permission(ctx.author, ctx.guild, ['high_admin', 'owner']):
            await ctx.send("❌ Только high_admin+ могут создавать эксклюзивные баннеры!", ephemeral=True)
            return
        
        cursor = self.db.conn.cursor()
        cursor.execute('''
            INSERT INTO banners (guild_id, name, image_url, rarity, achievement_id, price, is_default, is_exclusive, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ctx.guild.id, name, image_url, rarity, achievement_id if achievement_id > 0 else None, 
            price, 1 if is_default else 0, 1 if is_exclusive else 0, int(datetime.now().timestamp())))
        
        self.db.conn.commit()
        banner_id = cursor.lastrowid
        
        embed = discord.Embed(
            title="✅ Баннер создан!",
            description=f"ID: {banner_id}",
            color=self.rarity_colors.get(rarity, 0x00ff00)
        )
        
        embed.add_field(name="Название", value=name, inline=True)
        embed.add_field(name="Редкость", value=rarity.upper(), inline=True)
        embed.add_field(name="Цена", value=f"{price} монет" if price > 0 else "Не продается", inline=True)
        
        if achievement_id > 0:
            embed.add_field(name="Требуемое достижение", value=f"ID: {achievement_id}", inline=True)
        
        embed.add_field(name="По умолчанию", value="Да" if is_default else "Нет", inline=True)
        embed.add_field(name="Эксклюзивный", value="Да" if is_exclusive else "Нет", inline=True)
        
        embed.set_image(url=image_url)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='banners', description='Посмотреть все баннеры')
    async def show_banners(self, ctx):
        """Показать все баннеры сервера"""
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM banners WHERE guild_id = ? ORDER BY price ASC, rarity DESC', 
                      (ctx.guild.id,))
        
        banners = cursor.fetchall()
        
        if not banners:
            embed = discord.Embed(
                title="🎨 Баннеры сервера",
                description="Баннеры еще не созданы.",
                color=0x808080
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🎨 Баннеры сервера",
            description=f"Всего: {len(banners)}",
            color=0x9b59b6
        )
        
        banners_by_rarity = {}
        for banner in banners:
            try:
                rarity = banner[4]
                if rarity not in banners_by_rarity:
                    banners_by_rarity[rarity] = []
                banners_by_rarity[rarity].append(banner)
            except IndexError:
                continue
        
        for rarity in ['common', 'rare', 'epic', 'legendary', 'exclusive']:
            if rarity in banners_by_rarity:
                rarity_banners = banners_by_rarity[rarity]
                text = ""
                for banner in rarity_banners[:3]:
                    banner_id = banner[0]
                    name = banner[2]
                    achievement_id = banner[5]
                    price = banner[6]
                    is_exclusive = banner[8] if len(banner) > 8 else 0
                    
                    condition = ""
                    if is_exclusive:
                        condition = " 🔴 Эксклюзив"
                    elif achievement_id:
                        condition = f" 🔓 Ач. {achievement_id}"
                    elif price > 0:
                        condition = f" 💰 {price} монет"
                    else:
                        condition = " 🎁 Подарок"
                    
                    text += f"**{banner_id}** - {name}{condition}\n"
                
                if len(rarity_banners) > 3:
                    text += f"... и еще {len(rarity_banners) - 3}"
                
                embed.add_field(
                    name=f"{self.rarity_emojis.get(rarity, '🟡')} {rarity.upper()}",
                    value=text or "Нет баннеров",
                    inline=False
                )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='setbanner', description='Установить активный баннер')
    @app_commands.describe(banner_id='ID баннера')
    async def set_banner(self, ctx, banner_id: int):
        """Установить баннер в качестве активного"""
        cursor = self.db.conn.cursor()
    
        cursor.execute('SELECT * FROM banners WHERE banner_id = ? AND guild_id = ?', 
                      (banner_id, ctx.guild.id))

        banner = cursor.fetchone()

        if not banner:
            await ctx.send("❌ Баннер не найден!", ephemeral=True)
            return
    
        try:
            if len(banner) >= 9:
                name = banner[2]
                image_url = banner[3]
                rarity = banner[4]
                achievement_id = banner[5] if len(banner) > 5 else None
                price = banner[6] if len(banner) > 6 else 0
                is_exclusive = banner[8] if len(banner) > 8 else 0
            else:
                await ctx.send("❌ Неизвестная структура баннера!", ephemeral=True)
                return
        except Exception as e:
            await ctx.send(f"❌ Ошибка обработки баннера: {e}", ephemeral=True)
            return
    
        # Проверяем, не эксклюзивный ли баннер
        if is_exclusive and not check_permission(ctx.author, ctx.guild, ['high_admin', 'owner']):
            await ctx.send("❌ Это эксклюзивный баннер! Только high_admin+ могут его использовать.", ephemeral=True)
            return
    
        if achievement_id:
            cursor.execute('''
                SELECT * FROM user_achievements 
                WHERE user_id = ? AND guild_id = ? AND achievement_id = ? AND completed = 1
            ''', (ctx.author.id, ctx.guild.id, achievement_id))
        
            if not cursor.fetchone():
                await ctx.send("❌ У вас нет необходимого достижения для этого баннера!", ephemeral=True)
                return
    
        # Проверяем, есть ли у пользователя этот баннер в коллекции
        cursor.execute('''
            SELECT obtained_at FROM user_banners 
            WHERE user_id = ? AND guild_id = ? AND banner_id = ?
        ''', (ctx.author.id, ctx.guild.id, banner_id))
    
        banner_data = cursor.fetchone()
    
        if not banner_data:
            # Баннера нет в коллекции, проверяем возможность покупки
            if price > 0:
                user_data = self.db.get_user(ctx.author.id, ctx.guild.id)
                if user_data[2] < price:
                    await ctx.send(f"❌ Недостаточно монет для покупки баннера! Нужно: {price}", ephemeral=True)
                    return
            
                self.db.update_balance(ctx.author.id, ctx.guild.id, -price)
                cursor.execute('''
                    INSERT INTO user_banners (user_id, guild_id, banner_id, is_active, obtained_at)
                    VALUES (?, ?, ?, 0, ?)
                ''', (ctx.author.id, ctx.guild.id, banner_id, int(datetime.now().timestamp())))
            
                await ctx.send(f"✅ Баннер куплен за {price} монет!", ephemeral=True)
            else:
                await ctx.send("❌ У вас нет этого баннера!", ephemeral=True)
                return
        else:
            # Баннер есть в коллекции, проверяем тип получения
            obtained_at = banner_data[0]
        
            # Если баннер получен через админскую установку (-2), пользователь не может его менять
            if obtained_at == -2:
                await ctx.send("❌ Этот баннер был установлен администратором и не может быть изменен вами!", ephemeral=True)
                return
            # Если баннер получен через админскую выдачу (-1), пользователь может его установить
            elif obtained_at <= 0:
                # Это админская выдача, пользователь может установить баннер
                pass
    
        # Деактивируем все другие баннеры пользователя
        cursor.execute('''
            UPDATE user_banners 
            SET is_active = 0 
            WHERE user_id = ? AND guild_id = ?
        ''', (ctx.author.id, ctx.guild.id))
    
        # Активируем выбранный баннер
        cursor.execute('''
            UPDATE user_banners 
            SET is_active = 1 
            WHERE user_id = ? AND guild_id = ? AND banner_id = ?
        ''', (ctx.author.id, ctx.guild.id, banner_id))
    
        self.db.conn.commit()
    
        embed = discord.Embed(
            title="✅ Баннер установлен!",
            description=f"Баннер **{name}** теперь активен в вашем профиле.",
            color=self.rarity_colors.get(rarity, 0x00ff00)
        )
    
        if image_url:
            embed.set_image(url=image_url)
    
        embed.add_field(name="Редкость", value=rarity.upper(), inline=True)
        embed.add_field(name="ID", value=banner_id, inline=True)
        if is_exclusive:
            embed.add_field(name="🔴 Эксклюзивный", value="Да", inline=True)
    
        await ctx.send(embed=embed, ephemeral=True)
    
    @achievement_admin.command(name='givebanner', description='Выдать баннер пользователю (только high_admin+)')
    @has_permission('high_admin', 'owner')
    @app_commands.describe(
        member='Пользователь',
        banner_id='ID баннера'
    )
    async def give_banner(self, ctx, member: discord.Member, banner_id: int):
        """Выдать баннер пользователю"""
        cursor = self.db.conn.cursor()
        
        cursor.execute('SELECT * FROM banners WHERE banner_id = ? AND guild_id = ?', 
                      (banner_id, ctx.guild.id))

        banner = cursor.fetchone()

        if not banner:
            await ctx.send("❌ Баннер не найден!", ephemeral=True)
            return
        
        # Упрощенная обработка
        try:
            if len(banner) >= 10:
                name = banner[2]
                image_url = banner[3]
                rarity = banner[4]
                is_exclusive = banner[8]
            elif len(banner) >= 9:
                name = banner[2]
                image_url = banner[3]
                rarity = banner[4]
                is_exclusive = 0
            else:
                await ctx.send("❌ Неизвестная структура баннера!", ephemeral=True)
                return
        except Exception as e:
            await ctx.send("❌ Ошибка обработки баннера!", ephemeral=True)
            return
        
        # Проверяем, есть ли уже у пользователя
        cursor.execute('''
            SELECT * FROM user_banners 
            WHERE user_id = ? AND guild_id = ? AND banner_id = ?
        ''', (member.id, ctx.guild.id, banner_id))
        
        if cursor.fetchone():
            await ctx.send("❌ У пользователя уже есть этот баннер!", ephemeral=True)
            return
        
        # Добавляем баннер пользователю
        cursor.execute('''
            INSERT INTO user_banners (user_id, guild_id, banner_id, is_active, obtained_at)
            VALUES (?, ?, ?, 0, ?)
        ''', (member.id, ctx.guild.id, banner_id, int(datetime.now().timestamp())))
        
        self.db.conn.commit()
        
        embed = discord.Embed(
            title="✅ Баннер выдан!",
            description=f"{member.mention} получил баннер:",
            color=self.rarity_colors.get(rarity, 0x00ff00)
        )
        
        embed.add_field(name="Баннер", value=f"**{name}** ({rarity})", inline=True)
        embed.add_field(name="ID", value=banner_id, inline=True)
        if is_exclusive:
            embed.add_field(name="🔴 Эксклюзивный", value="Да", inline=True)
        
        if image_url:
            embed.set_image(url=image_url)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='profile', description='Профиль как в Arcane')
    @app_commands.describe(member='Пользователь для просмотра профиля')
    async def profile(self, ctx, member: discord.Member = None):
        """Профиль с карточкой как в Arcane"""
        member = member or ctx.author
        
        await ctx.defer()
        
        user_data = self.db.get_user(member.id, ctx.guild.id)
        if not user_data:
            await ctx.send("❌ Данные пользователя не найдены!")
            return
            
        balance = user_data[2]
        xp = user_data[3]
        level = user_data[4]
        
        cursor = self.db.conn.cursor()
        
        # Получаем активный баннер пользователя
        cursor.execute('''
            SELECT b.banner_id, b.name, b.image_url, b.rarity, b.is_exclusive, ub.is_active
            FROM user_banners ub
            JOIN banners b ON ub.banner_id = b.banner_id
            WHERE ub.user_id = ? AND ub.guild_id = ? AND ub.is_active = 1
        ''', (member.id, ctx.guild.id))
        
        banner_result = cursor.fetchone()
        banner_info = None
        
        if banner_result:
            banner_info = {
                'id': banner_result[0],
                'name': banner_result[1],
                'image_url': banner_result[2],
                'rarity': banner_result[3],
                'is_exclusive': banner_result[4] if len(banner_result) > 4 else 0,
                'is_active': banner_result[5] if len(banner_result) > 5 else 0
            }
        
        # Получаем информацию о клане
        cursor.execute('''
            SELECT c.name, cm.role, cs.owner_role_name, cs.coowner_role_name, cs.member_role_name 
            FROM clan_members cm
            JOIN clans c ON cm.clan_id = c.clan_id
            LEFT JOIN clan_settings cs ON c.clan_id = cs.clan_id
            WHERE cm.user_id = ? AND cm.guild_id = ?
        ''', (member.id, ctx.guild.id))
        
        clan_data = cursor.fetchone()
        clan_info = ""
        if clan_data:
            clan_name, clan_role, owner_role_name, coowner_role_name, member_role_name = clan_data
            
            if clan_role == 'owner':
                display_role = owner_role_name or 'Владелец'
            elif clan_role == 'coowner':
                display_role = coowner_role_name or 'Совладелец'
            else:
                display_role = member_role_name or 'Участник'
            
            clan_info = f"{display_role} клана **{clan_name}**"
        else:
            clan_info = "Не состоит в клане"
        
        # Пробуем сгенерировать карточку с помощью PIL
        try:
            from utils.profile_generator import profile_generator
            from utils.profile_generator import cleanup_old_cards
            
            # Очищаем старые карточки при запуске команды
            cleanup_old_cards()
            
            # Получаем достижения для прогресса
            cursor.execute('''
                SELECT COUNT(*) FROM user_achievements 
                WHERE user_id = ? AND guild_id = ? AND completed = 1
            ''', (member.id, ctx.guild.id))
            
            completed = cursor.fetchone()
            completed_count = completed[0] if completed else 0
            
            cursor.execute('SELECT COUNT(*) FROM achievements WHERE guild_id = ? AND is_secret = 0', (ctx.guild.id,))
            total_result = cursor.fetchone()
            total_count = total_result[0] if total_result else 0
            
            progress_percent = int((completed_count / total_count * 100)) if total_count > 0 else 0
            
            # URL баннера
            banner_url = banner_info['image_url'] if banner_info and 'image_url' in banner_info else None
            
            # Генерируем карточку
            if profile_generator.PIL_AVAILABLE:
                card_path = await profile_generator.create_profile_card(
                    member=member,
                    user_data=user_data,
                    banner_url=banner_url,
                    progress_percent=progress_percent
                )
                
                if card_path and os.path.exists(card_path):
                    # Отправляем карточку как файл
                    file = discord.File(card_path, filename=f"profile_{member.id}.png")
                    
                    # Создаем embed с дополнительной информацией
                    embed = discord.Embed(
                        title=f"📊 Профиль {member.display_name}",
                        color=member.color if member.color else 0x00ff00
                    )
                    
                    embed.set_image(url=f"attachment://profile_{member.id}.png")
                    
                    # Добавляем информацию о достижениях
                    if completed_count > 0:
                        embed.add_field(
                            name="🏆 Достижения", 
                            value=f"{completed_count}/{total_count} выполнено", 
                            inline=True
                        )
                    
                    # Информация о баннере
                    if banner_info:
                        banner_text = f"{banner_info['name']} ({banner_info['rarity']})"
                        if banner_info.get('is_exclusive'):
                            banner_text += " 🔴"
                        embed.add_field(
                            name="🎨 Баннер", 
                            value=banner_text, 
                            inline=True
                        )
                    
                    # Дополнительная информация
                    embed.add_field(
                        name="Баланс", 
                        value=f"{balance:,} монет", 
                        inline=True
                    )

                    # Информация о клане
                    embed.add_field(
                        name="🏰 Клан", 
                        value=clan_info, 
                        inline=True
                    )
                    
                    embed.set_footer(text=f"ID: {member.id} | Используйте /myachievements для просмотра ачивок")
                    
                    await ctx.send(file=file, embed=embed)
                    
                    # Удаляем временный файл через 5 секунд
                    await asyncio.sleep(5)
                    try:
                        os.remove(card_path)
                    except:
                        pass
                    return
                    
        except ImportError:
            print("⚠️ profile_generator не найден")
        except Exception as e:
            print(f"⚠️ Ошибка генерации карточки: {e}")
        
        # Стандартный embed (запасной вариант)
        embed = discord.Embed(
            title=f"📊 Профиль {member.display_name}",
            color=member.color if member.color else 0x00ff00
        )
        
        # Устанавливаем баннер как изображение, если есть
        if banner_info and banner_info.get('image_url'):
            try:
                if banner_info['image_url'] and banner_info['image_url'].startswith('http'):
                    embed.set_image(url=banner_info['image_url'])
                    banner_text = f"{banner_info['name']} ({banner_info['rarity']})"
                    if banner_info.get('is_exclusive'):
                        banner_text += " 🔴"
                    embed.add_field(name="🎨 Баннер", value=banner_text, inline=True)
            except Exception as e:
                print(f"❌ Ошибка установки баннера: {e}")
        
        # Основная информация
        embed.add_field(name="🏆 Уровень", value=level, inline=True)
        embed.add_field(name="💰 Баланс", value=f"{balance:,} монет", inline=True)
        embed.add_field(name="⭐ Опыт", value=f"{xp:,}", inline=True)
        embed.add_field(name="🏰 Клан", value=clan_info, inline=True)
        
        # Достижения
        cursor.execute('''
            SELECT COUNT(*) FROM user_achievements 
            WHERE user_id = ? AND guild_id = ? AND completed = 1
        ''', (member.id, ctx.guild.id))
        
        completed = cursor.fetchone()
        completed_count = completed[0] if completed else 0
        
        cursor.execute('SELECT COUNT(*) FROM achievements WHERE guild_id = ? AND is_secret = 0', (ctx.guild.id,))
        total = cursor.fetchone()
        total_count = total[0] if total else 0
        
        if total_count > 0:
            embed.add_field(
                name="🏆 Достижения", 
                value=f"{completed_count}/{total_count} выполнено", 
                inline=True
            )
        
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_footer(text=f"ID: {member.id} | Используйте /myachievements для просмотра ачивок")
        
        await ctx.send(embed=embed)

    @achievement_admin.command(name='deletebanner', description='Удалить баннер')
    @app_commands.describe(banner_id='ID баннера для удаления')
    async def delete_banner(self, ctx, banner_id: int):
        """Удаление баннера"""
        cursor = self.db.conn.cursor()
        
        cursor.execute('SELECT * FROM banners WHERE banner_id = ? AND guild_id = ?', 
                      (banner_id, ctx.guild.id))
        
        banner = cursor.fetchone()
        
        if not banner:
            await ctx.send("❌ Баннер не найден!", ephemeral=True)
            return
        
        name = banner[2]
        
        cursor.execute('DELETE FROM user_banners WHERE banner_id = ? AND guild_id = ?', 
                      (banner_id, ctx.guild.id))
        
        cursor.execute('DELETE FROM banners WHERE banner_id = ? AND guild_id = ?', 
                      (banner_id, ctx.guild.id))
        
        self.db.conn.commit()
        
        embed = discord.Embed(
            title="✅ Баннер удален!",
            description=f"Баннер **{name}** удален с сервера.",
            color=0x00ff00
        )
        
        await ctx.send(embed=embed)
    
    @achievement_admin.command(name='deleteachievement', description='Удалить достижение')
    @app_commands.describe(achievement_id='ID достижения для удаления')
    async def delete_achievement(self, ctx, achievement_id: int):
        """Удаление достижения"""
        cursor = self.db.conn.cursor()
        
        cursor.execute('SELECT * FROM achievements WHERE achievement_id = ? AND guild_id = ?', 
                      (achievement_id, ctx.guild.id))
        
        achievement = cursor.fetchone()
        
        if not achievement:
            await ctx.send("❌ Достижение не найдено!", ephemeral=True)
            return
        
        name = achievement[2]
        
        cursor.execute('DELETE FROM user_achievements WHERE achievement_id = ? AND guild_id = ?', 
                      (achievement_id, ctx.guild.id))
        
        cursor.execute('DELETE FROM achievements WHERE achievement_id = ? AND guild_id = ?', 
                      (achievement_id, ctx.guild.id))
        
        self.db.conn.commit()
        
        embed = discord.Embed(
            title="✅ Достижение удалено!",
            description=f"Достижение **{name}** удалено с сервера.",
            color=0x00ff00
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='bannershop', description='Магазин баннеров')
    async def banner_shop(self, ctx, page: int = 1):
        """Магазин баннеров с пагинацией"""
        cursor = self.db.conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM banners WHERE guild_id = ? AND price > 0 AND is_exclusive = 0', 
                      (ctx.guild.id,))
        total_banners = cursor.fetchone()[0]
        
        if total_banners == 0:
            embed = discord.Embed(
                title="🎨 Магазин баннеров",
                description="В магазине пока нет баннеров для покупки.",
                color=0x808080
            )
            await ctx.send(embed=embed)
            return
        
        items_per_page = 6
        total_pages = (total_banners + items_per_page - 1) // items_per_page
        
        if page < 1 or page > total_pages:
            await ctx.send(f"❌ Страница должна быть от 1 до {total_pages}!", ephemeral=True)
            return
        
        offset = (page - 1) * items_per_page
        
        cursor.execute('''
            SELECT * FROM banners 
            WHERE guild_id = ? AND price > 0 AND is_exclusive = 0
            ORDER BY price ASC 
            LIMIT ? OFFSET ?
        ''', (ctx.guild.id, items_per_page, offset))
        
        banners = cursor.fetchall()
        
        embed = discord.Embed(
            title=f"🎨 Магазин баннеров (Страница {page}/{total_pages})",
            description=f"Всего баннеров: {total_banners}",
            color=0x9b59b6
        )
        
        for banner in banners:
            if len(banner) >= 7:
                banner_id = banner[0]
                name = banner[2]
                rarity = banner[4]
                achievement_id = banner[5] if len(banner) > 5 else None
                price = banner[6] if len(banner) > 6 else 0
        
                condition = ""
                if achievement_id:
                    cursor.execute('SELECT name FROM achievements WHERE achievement_id = ?', (achievement_id,))
                    ach_name = cursor.fetchone()
                    condition = f"Требуется достижение: {ach_name[0] if ach_name else 'Неизвестно'}"
                else:
                    condition = f"Цена: {price} монет"
        
                embed.add_field(
                    name=f"{self.rarity_emojis.get(rarity, '🟡')} {name}",
                    value=f"**ID:** {banner_id}\n**Редкость:** {rarity}\n**{condition}**",
                    inline=True
                )
        
        embed.set_footer(text="Используйте /setbanner [ID] для покупки и установки")
        
        class ShopView(discord.ui.View):
            def __init__(self, total_pages, current_page, author_id, db, rarity_emojis):
                super().__init__(timeout=60)
                self.total_pages = total_pages
                self.current_page = current_page
                self.author_id = author_id
                self.db = db
                self.rarity_emojis = rarity_emojis
            
            @discord.ui.button(label="◀️ Назад", style=discord.ButtonStyle.gray, disabled=False)
            async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("❌ Это не ваш запрос!", ephemeral=True)
                    return
                
                await self.update_page(interaction, self.current_page - 1)
            
            @discord.ui.button(label="▶️ Вперед", style=discord.ButtonStyle.gray, disabled=False)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("❌ Это не ваш запрос!", ephemeral=True)
                    return
                
                await self.update_page(interaction, self.current_page + 1)
            
            async def update_page(self, interaction: discord.Interaction, new_page):
                cursor = self.db.conn.cursor()
                items_per_page = 6
                offset = (new_page - 1) * items_per_page
                
                cursor.execute('SELECT COUNT(*) FROM banners WHERE guild_id = ? AND price > 0 AND is_exclusive = 0', 
                              (interaction.guild.id,))
                total_banners = cursor.fetchone()[0]
                total_pages = (total_banners + items_per_page - 1) // items_per_page
                
                cursor.execute('''
                    SELECT * FROM banners 
                    WHERE guild_id = ? AND price > 0 AND is_exclusive = 0
                    ORDER BY price ASC 
                    LIMIT ? OFFSET ?
                ''', (interaction.guild.id, items_per_page, offset))
                
                banners = cursor.fetchall()
                
                embed = discord.Embed(
                    title=f"🎨 Магазин баннеров (Страница {new_page}/{total_pages})",
                    description=f"Всего баннеров: {total_banners}",
                    color=0x9b59b6
                )
                
                for banner in banners:
                    banner_id = banner[0]
                    name = banner[2]
                    rarity = banner[4]
                    achievement_id = banner[5]
                    price = banner[6]
                    
                    condition = ""
                    if achievement_id:
                        cursor.execute('SELECT name FROM achievements WHERE achievement_id = ?', (achievement_id,))
                        ach_name = cursor.fetchone()
                        condition = f"Требуется достижение: {ach_name[0] if ach_name else 'Неизвестно'}"
                    else:
                        condition = f"Цена: {price} монет"
                    
                    embed.add_field(
                        name=f"{self.rarity_emojis.get(rarity, '🟡')} {name}",
                        value=f"**ID:** {banner_id}\n**Редкость:** {rarity}\n**{condition}**",
                        inline=True
                    )
                
                embed.set_footer(text="Используйте /setbanner [ID] для покупки и установки")
                
                self.current_page = new_page
                self.total_pages = total_pages
                
                # Обновляем состояние кнопок
                self.children[0].disabled = (new_page == 1)
                self.children[1].disabled = (new_page == total_pages)
                
                await interaction.response.edit_message(embed=embed, view=self)
        
        # Устанавливаем начальное состояние кнопок
        view = ShopView(total_pages, page, ctx.author.id, self.db, self.rarity_emojis)
        view.children[0].disabled = (page == 1)
        view.children[1].disabled = (page == total_pages)
        
        await ctx.send(embed=embed, view=view)

    @achievement_admin.command(name='setbannerad', description='Установить баннер пользователю (принудительно)')
    @has_permission('high_admin', 'owner')
    @app_commands.describe(
        member='Пользователь',
        banner_id='ID баннера'
    )
    async def set_banner_ad(self, ctx, member: discord.Member, banner_id: int):
        """Установить баннер пользователю принудительно (без добавления в коллекцию)"""
        cursor = self.db.conn.cursor()
    
        cursor.execute('SELECT * FROM banners WHERE banner_id = ? AND guild_id = ?', 
                      (banner_id, ctx.guild.id))

        banner = cursor.fetchone()

        if not banner:
            await ctx.send("❌ Баннер не найден!", ephemeral=True)
            return
    
        try:
            if len(banner) >= 9:
                name = banner[2]
                image_url = banner[3]
                rarity = banner[4]
                is_exclusive = banner[8] if len(banner) > 8 else 0
            else:
                await ctx.send("❌ Неизвестная структура баннера!", ephemeral=True)
                return
        except Exception as e:
            await ctx.send("❌ Ошибка обработки баннера!", ephemeral=True)
            return
    
        # Проверяем, есть ли уже у пользователя этот баннер (включая админские выдачи)
        cursor.execute('''
            SELECT * FROM user_banners 
            WHERE user_id = ? AND guild_id = ? AND banner_id = ?
        ''', (member.id, ctx.guild.id, banner_id))
    
        has_banner = cursor.fetchone()
    
        if not has_banner:
            # Создаем запись с отрицательным obtained_at для админской установки
            cursor.execute('''
                INSERT INTO user_banners (user_id, guild_id, banner_id, is_active, obtained_at)
               VALUES (?, ?, ?, 0, -2)
           ''', (member.id, ctx.guild.id, banner_id, int(datetime.now().timestamp())))
    
        # Деактивируем все другие баннеры пользователя
        cursor.execute('''
            UPDATE user_banners 
            SET is_active = 0 
            WHERE user_id = ? AND guild_id = ?
        ''', (member.id, ctx.guild.id))
    
        # Активируем выбранный баннер
        cursor.execute('''
            UPDATE user_banners 
            SET is_active = 1 
            WHERE user_id = ? AND guild_id = ? AND banner_id = ?
        ''', (member.id, ctx.guild.id, banner_id))
    
        self.db.conn.commit()
    
        embed = discord.Embed(
            title="✅ Баннер установлен (админская установка)!",
           description=f"Баннер установлен для {member.mention}:",
           color=self.rarity_colors.get(rarity, 0x00ff00)
        )
    
        embed.add_field(name="Баннер", value=f"**{name}** ({rarity})", inline=True)
        embed.add_field(name="Тип установки", value="👑 Принудительная", inline=True)
        embed.add_field(name="Примечание", value="Пользователь не сможет изменить этот баннер через /setbanner", inline=False)
    
        if is_exclusive:
            embed.add_field(name="🔴 Эксклюзивный", value="Да", inline=True)
    
        if image_url:
            embed.set_image(url=image_url)
    
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='mybanners', description='Посмотреть вашу коллекцию баннеров')
    async def my_banners(self, ctx):
        """Показать баннеры пользователя"""
        cursor = self.db.conn.cursor()
    
        cursor.execute('''
            SELECT b.banner_id, b.name, b.image_url, b.rarity, b.is_exclusive, 
                   ub.is_active, ub.obtained_at
            FROM user_banners ub
            JOIN banners b ON ub.banner_id = b.banner_id
            WHERE ub.user_id = ? AND ub.guild_id = ?
            ORDER BY ub.is_active DESC, b.rarity DESC, ub.obtained_at DESC
        ''', (ctx.author.id, ctx.guild.id))
    
        banners = cursor.fetchall()
    
        if not banners:
            embed = discord.Embed(
                title="🎨 Ваша коллекция баннеров",
                description="У вас пока нет баннеров.\nИспользуйте `/bannershop` для покупки или получите баннер через достижения!",
                color=0x808080
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
    
        embed = discord.Embed(
            title=f"🎨 Коллекция баннеров {ctx.author.display_name}",
            description=f"Всего баннеров: {len(banners)}",
            color=0x9b59b6
        )
    
        active_banner = None
        available_banners = []
        admin_given_banners = []
    
        for banner in banners:
            banner_id = banner[0]
            name = banner[1]
            image_url = banner[2]
            rarity = banner[3]
            is_exclusive = banner[4] if len(banner) > 4 else 0
            is_active = banner[5] if len(banner) > 5 else 0
            obtained_at = banner[6] if len(banner) > 6 else 0
        
            if is_active:
                active_banner = banner
                continue
            
            if obtained_at > 0:
                available_banners.append(banner)
            else:
                admin_given_banners.append(banner)
    
        # Показываем активный баннер
        if active_banner:
            banner_text = f"**Активный баннер:**\n"
            banner_text += f"🎯 **{active_banner[1]}** ({active_banner[3]})\n"
            banner_text += f"📌 ID: {active_banner[0]}\n"
        
            if active_banner[4]:
                banner_text += "🔴 Эксклюзивный\n"
        
            if active_banner[6] <= 0:
                banner_text += "👑 Установлен администратором\n"
       
            embed.add_field(name="🎯 Активный баннер", value=banner_text, inline=False)
    
        # Показываем доступные баннеры
        if available_banners:
            banners_text = ""
            for banner in available_banners[:5]:
                banners_text += f"**{banner[0]}** - {self.rarity_emojis.get(banner[3], '🟡')} {banner[1]}\n"
        
            if len(available_banners) > 5:
                banners_text += f"... и еще {len(available_banners) - 5} баннеров"
        
            if banners_text:
                embed.add_field(
                    name=f"📂 Доступные баннеры ({len(available_banners)})",
                    value=banners_text,
                    inline=False
                )
    
        # Показываем баннеры от админов
        if admin_given_banners:
            admin_text = ""
            for banner in admin_given_banners[:3]:
                admin_text += f"**{banner[0]}** - {self.rarity_emojis.get(banner[3], '🟡')} {banner[1]}\n"
                if banner[6] == -2:
                    admin_text += "  ⚠️ Установлен админом (нельзя изменить)\n"
                else:
                    admin_text += "  ⭐ Выдан админом\n"
        
            if len(admin_given_banners) > 3:
                admin_text += f"... и еще {len(admin_given_banners) - 3} баннеров"
        
            if admin_text:
                embed.add_field(
                    name=f"👑 Баннеры от администрации ({len(admin_given_banners)})",
                    value=admin_text,
                    inline=False
                )
    
        embed.set_footer(text="Используйте /setbanner [ID] для установки баннера")
    
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Achievements(bot))
    print("✅ Ког Achievements успешно загружен!")