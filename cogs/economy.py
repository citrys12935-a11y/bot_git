import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
from utils.database import Database
from datetime import datetime
from utils.checks import has_permission

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
    
    def get_safe_work_reward(self, settings):
        try:
            work_min = settings[1]
            work_max = settings[2]
            
            if work_min is None or work_max is None:
                return random.randint(10, 50)
                
            if work_min > work_max:
                work_min, work_max = work_max, work_min
            
            if work_min < 1:
                work_min = 1
            if work_max < work_min:
                work_max = work_min + 10
                
            return random.randint(work_min, work_max)
        except Exception as e:
            print(f"❌ Ошибка в get_safe_work_reward: {e}")
            return random.randint(10, 50)
    
    @commands.hybrid_command(name='work', description='Заработать монеты')
    async def work(self, ctx):
        try:
            user_id = ctx.author.id
            guild_id = ctx.guild.id
            
            settings = self.db.get_server_settings(guild_id)
            if not settings:
                await ctx.send("❌ Настройки сервера не найдены! Обратитесь к администратору.")
                return
                
            print(f"DEBUG: Настройки work - min: {settings[1]}, max: {settings[2]}, cooldown: {settings[3]}")
            
            cooldown = self.db.get_cooldown(user_id, guild_id, 'work')
            current_time = datetime.now().timestamp()
            
            work_cooldown = settings[3]
            if cooldown and (current_time - cooldown) < work_cooldown:
                remaining = int(work_cooldown - (current_time - cooldown))
                minutes = remaining // 60
                seconds = remaining % 60
                await ctx.send(f"⏰ Вы можете работать again через {minutes} минут {seconds} секунд!")
                return
            
            base_reward = self.get_safe_work_reward(settings)
            
            multiplier = 1.0
            multiplier_roles = []
            
            for role in ctx.author.roles:
                role_mult = self.db.get_role_multiplier(role.id)
                if role_mult and role_mult[0] > 1.0:
                    if role_mult[0] > multiplier:
                        multiplier = role_mult[0]
                    multiplier_roles.append(f"{role.name} (x{role_mult[0]})")
            
            final_reward = int(base_reward * multiplier)
            
            self.db.update_balance(user_id, guild_id, final_reward)
            
            # Проверяем достижения по работе
            achievements_cog = self.bot.get_cog('Achievements')
            if achievements_cog:
                cursor = self.db.conn.cursor()
                
                # Получаем текущее количество работ
                cursor.execute('''
                    SELECT COALESCE(SUM(progress), 0) FROM user_achievements ua
                    JOIN achievements a ON ua.achievement_id = a.achievement_id
                    WHERE ua.user_id = ? AND ua.guild_id = ? AND a.requirement_type = 'work_count'
                ''', (user_id, guild_id))
                
                result = cursor.fetchone()
                current_work_count = result[0] + 1 if result else 1
                
                # Обновляем прогресс во всех достижениях типа work_count
                cursor.execute('''
                    UPDATE user_achievements 
                    SET progress = progress + 1 
                    WHERE user_id = ? AND guild_id = ? AND achievement_id IN (
                        SELECT achievement_id FROM achievements 
                        WHERE guild_id = ? AND requirement_type = 'work_count'
                    )
                ''', (user_id, guild_id, guild_id))
                
                # Если нет записи о прогрессе, создаем для всех достижений work_count
                cursor.execute('''
                    SELECT achievement_id FROM achievements 
                    WHERE guild_id = ? AND requirement_type = 'work_count' 
                    AND achievement_id NOT IN (
                        SELECT achievement_id FROM user_achievements 
                        WHERE user_id = ? AND guild_id = ?
                    )
                ''', (guild_id, user_id, guild_id))
                
                new_achievements = cursor.fetchall()
                for ach in new_achievements:
                    cursor.execute('''
                        INSERT INTO user_achievements (user_id, guild_id, achievement_id, progress)
                        VALUES (?, ?, ?, 1)
                    ''', (user_id, guild_id, ach[0]))
                
                self.db.conn.commit()
                
                # Проверяем, выполнены ли достижения
                await achievements_cog.check_achievements(user_id, guild_id, 'work_count', current_work_count)
        
            self.db.set_cooldown(user_id, guild_id, 'work')
            
            embed = discord.Embed(
                title="💼 Работа",
                description=f"{ctx.author.mention} заработал **{final_reward}** монет!",
                color=0x00ff00
            )
            
            if multiplier > 1.0:
                embed.add_field(name="📊 Базовая награда", value=f"{base_reward} монет", inline=True)
                embed.add_field(name="✨ Множитель", value=f"x{multiplier}", inline=True)
                if multiplier_roles:
                    embed.add_field(name="🏷️ Роли с бонусом", value=", ".join(multiplier_roles), inline=False)
            else:
                embed.add_field(name="💡 Подсказка", value="Хотите больше? Получите специальные роли с множителями!", inline=False)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"❌ ERROR в work: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send("❌ Произошла ошибка при выполнении команды. Попробуйте позже.")
    
    @commands.hybrid_command(name='resetwork', description='Сбросить настройки работы к значениям по умолчанию')
    @has_permission('admin', 'high_admin', 'owner')
    async def reset_work(self, ctx):
        try:
            guild_id = ctx.guild.id
            self.db.update_server_settings(guild_id, 
                                         work_reward_min=10,
                                         work_reward_max=50,
                                         work_cooldown=3600)
            await ctx.send("✅ Настройки work сброшены к значениям по умолчанию: 10-50 монет, кулдаун 1 час")
        except Exception as e:
            await ctx.send(f"❌ Ошибка сброса: {e}")
    
    @commands.hybrid_command(name='slots', description='Играть в слот-машину')
    @app_commands.describe(bet='Сумма ставки')
    async def slots(self, ctx, bet: int):
        try:
            user_id = ctx.author.id
            guild_id = ctx.guild.id
            
            settings = self.db.get_server_settings(guild_id)
            if not settings:
                await ctx.send("❌ Настройки сервера не найдены!")
                return
                
            user_data = self.db.get_user(user_id, guild_id)
            if not user_data:
                await ctx.send("❌ Данные пользователя не найдены!")
                return
            
            min_bet = settings[6] if len(settings) > 6 else 10
            max_bet = settings[7] if len(settings) > 7 else 100
            
            if bet < min_bet or bet > max_bet:
                await ctx.send(f"❌ Ставка должна быть от {min_bet} до {max_bet} монет!")
                return
            
            if user_data[2] < bet:
                await ctx.send("❌ Недостаточно монет для ставки!")
                return
            
            symbols = ['🍒', '🍋', '🍊', '🍇', '🔔', '💎']
            result = [random.choice(symbols) for _ in range(3)]
            
            self.db.update_balance(user_id, guild_id, -bet)
            new_balance = user_data[2] - bet
            
            if result[0] == result[1] == result[2]:
                win = bet * 5
                self.db.update_balance(user_id, guild_id, win)
                new_balance += win
                embed = discord.Embed(
                    title="🎰 Слот-машина - ДЖЕКПОТ!",
                    description=f"**{result[0]} | {result[1]} | {result[2]}**",
                    color=0x00ff00
                )
                embed.add_field(name="💰 Выигрыш", value=f"{win} монет", inline=True)
                embed.add_field(name="💎 Баланс", value=f"{new_balance} монет", inline=True)
            elif result[0] == result[1] or result[1] == result[2]:
                win = bet * 2
                self.db.update_balance(user_id, guild_id, win)
                new_balance += win
                embed = discord.Embed(
                    title="🎰 Слот-машина - Победа!",
                    description=f"**{result[0]} | {result[1]} | {result[2]}**",
                    color=0x00ff00
                )
                embed.add_field(name="💰 Выигрыш", value=f"{win} монет", inline=True)
                embed.add_field(name="💎 Баланс", value=f"{new_balance} монет", inline=True)
            else:
                embed = discord.Embed(
                    title="🎰 Слот-машина - Проигрыш",
                    description=f"**{result[0]} | {result[1]} | {result[2]}**",
                    color=0xff0000
                )
                embed.add_field(name="💸 Проигрыш", value=f"{bet} монет", inline=True)
                embed.add_field(name="💎 Баланс", value=f"{new_balance} монет", inline=True)
            
            await ctx.send(embed=embed)
                
        except Exception as e:
            print(f"❌ ERROR в slots: {e}")
            await ctx.send("❌ Произошла ошибка при игре в слоты.")
    
    @commands.hybrid_command(name='balance', aliases=['bal'], description='Посмотреть баланс')
    @app_commands.describe(member='Пользователь, чей баланс нужно посмотреть (необязательно)')
    async def balance(self, ctx, member: discord.Member = None):
        try:
            member = member or ctx.author
            user_data = self.db.get_user(member.id, ctx.guild.id)
            
            if not user_data:
                await ctx.send(f"💰 Баланс {member.mention}: 0 монет (пользователь не найден в базе)")
                return
            
            embed = discord.Embed(
                title="💰 Баланс",
                description=f"{member.mention} имеет **{user_data[2]}** монет",
                color=0x00ff00
            )
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"❌ ERROR в balance: {e}")
            await ctx.send("❌ Ошибка при получении баланса.")
    
    @commands.hybrid_command(name='transfer', description='Перевести монеты другому пользователю')
    @app_commands.describe(
        member='Пользователь, которому перевести',
        amount='Сумма для перевода'
    )
    async def transfer(self, ctx, member: discord.Member, amount: int):
        try:
            if amount <= 0:
                await ctx.send("❌ Сумма должна быть положительной!")
                return
            
            if member == ctx.author:
                await ctx.send("❌ Нельзя переводить деньги самому себе!")
                return
            
            sender_id = ctx.author.id
            receiver_id = member.id
            guild_id = ctx.guild.id
            
            sender_data = self.db.get_user(sender_id, guild_id)
            if not sender_data:
                await ctx.send("❌ Ваши данные не найдены в базе!")
                return
            
            if sender_data[2] < amount:
                await ctx.send("❌ Недостаточно монет для перевода!")
                return
            
            self.db.update_balance(sender_id, guild_id, -amount)
            self.db.update_balance(receiver_id, guild_id, amount)
            
            embed = discord.Embed(
                title="✅ Перевод выполнен",
                description=f"{ctx.author.mention} перевел {amount} монет {member.mention}",
                color=0x00ff00
            )
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"❌ ERROR в transfer: {e}")
            await ctx.send("❌ Ошибка при переводе денег.")
    
    @commands.hybrid_command(name='leaderboardec', aliases=['lbec'], description='Топ сервера по балансу')
    async def leaderboard_ec(self, ctx):
        try:
            leaders = self.db.get_leaderboard_ec(ctx.guild.id)
            
            embed = discord.Embed(title="💰 Топ по балансу", color=0x00ff00)
            
            if not leaders:
                embed.description = "Пока нет данных о пользователях."
            else:
                for i, (user_id, balance) in enumerate(leaders[:10], 1):
                    user = self.bot.get_user(user_id)
                    username = user.name if user else f"Неизвестный ({user_id})"
                    embed.add_field(name=f"{i}. {username}", value=f"{balance} монет", inline=False)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"❌ ERROR в leaderboard: {e}")
            await ctx.send("❌ Ошибка при получении таблицы лидеров.")
    
    @commands.hybrid_command(name='addec', description='Выдать монеты пользователю')
    @app_commands.describe(
        member='Пользователь, которому выдать монеты',
        amount='Количество монет'
    )
    @has_permission('admin', 'high_admin', 'owner')
    async def add_ec(self, ctx, member: discord.Member, amount: int):
        try:
            if amount <= 0:
                await ctx.send("❌ Сумма должна быть положительной!")
                return
                
            self.db.update_balance(member.id, ctx.guild.id, amount)
            await ctx.send(f"✅ {member.mention} выдано {amount} монет")
        except Exception as e:
            await ctx.send(f"❌ Ошибка выдачи: {e}")
    
    @commands.hybrid_command(name='removeec', description='Забрать монеты у пользователя')
    @app_commands.describe(
        member='Пользователь, у которого забрать монеты',
        amount='Количество монет'
    )
    @has_permission('admin', 'high_admin', 'owner')
    async def remove_ec(self, ctx, member: discord.Member, amount: int):
        try:
            if amount <= 0:
                await ctx.send("❌ Сумма должна быть положительной!")
                return
                
            self.db.update_balance(member.id, ctx.guild.id, -amount)
            await ctx.send(f"✅ У {member.mention} забрано {amount} монет")
        except Exception as e:
            await ctx.send(f"❌ Ошибка изъятия: {e}")

    @commands.hybrid_command(name='robstats', description='Статистика ограблений')
    @app_commands.describe(member='Пользователь для просмотра статистики (необязательно)')
    async def rob_stats(self, ctx, member: discord.Member = None):
        """Показать статистику ограблений"""
        member = member or ctx.author
        
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT robbery_success, robbery_fail, robbery_profit, robbery_loss, last_robbery
            FROM users WHERE user_id = ? AND guild_id = ?
        ''', (member.id, ctx.guild.id))
        
        stats = cursor.fetchone()
        
        if not stats or (stats[0] == 0 and stats[1] == 0):
            embed = discord.Embed(
                title=f"📊 Статистика ограблений {member.display_name}",
                description="Ещё не участвовал в ограблениях.",
                color=0x808080
            )
            await ctx.send(embed=embed)
            return
        
        success, fail, profit, loss, last_rob = stats
        
        # Рассчитываем эффективность
        total_attempts = success + fail
        success_rate = (success / total_attempts * 100) if total_attempts > 0 else 0
        net_profit = profit - loss
        
        embed = discord.Embed(
            title=f"📊 Статистика ограблений {member.display_name}",
            color=0x3498db
        )
        
        embed.add_field(name="✅ Успешных ограблений", value=str(success), inline=True)
        embed.add_field(name="❌ Неудачных попыток", value=str(fail), inline=True)
        embed.add_field(name="📈 Эффективность", value=f"{success_rate:.1f}%", inline=True)
        embed.add_field(name="💰 Заработано награбленным", value=f"{profit} монет", inline=True)
        embed.add_field(name="💸 Потеряно при провалах", value=f"{loss} монет", inline=True)
        embed.add_field(name="📊 Чистая прибыль", value=f"{net_profit} монет", inline=True)
        
        if last_rob:
            last_time = datetime.fromtimestamp(last_rob)
            embed.add_field(name="🕐 Последняя попытка", value=f"<t:{int(last_rob)}:R>", inline=True)
        
        # Определяем звание вора
        if success >= 50:
            rank = "🔪 Мафиозный Босс"
        elif success >= 25:
            rank = "🦹‍♂️ Профессиональный Вор"
        elif success >= 10:
            rank = "👤 Опытный Карманник"
        elif success >= 5:
            rank = "👶 Начинающий Вор"
        else:
            rank = "🕵️‍♂️ Новичок в деле"
        
        embed.add_field(name="🎖️ Звание", value=rank, inline=True)
        
        # Кулдаун
        cursor.execute('SELECT cooldown_until FROM robbery_cooldowns WHERE user_id = ? AND guild_id = ?', 
                     (member.id, ctx.guild.id))
        cooldown = cursor.fetchone()
        
        current_time = datetime.now().timestamp()
        if cooldown and cooldown[0] > current_time:
            remaining = int(cooldown[0] - current_time)
            minutes = remaining // 60
            seconds = remaining % 60
            embed.add_field(name="⏰ До следующей попытки", value=f"{minutes}м {seconds}с", inline=True)
        else:
            embed.add_field(name="⏰ Статус", value="Можно грабить! 🚀", inline=True)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='robleaderboard', aliases=['roblb'], description='Топ воришек сервера')
    async def rob_leaderboard(self, ctx, sort_by: str = 'profit'):
        """Топ игроков по статистике ограблений"""
        valid_sorts = ['profit', 'success', 'net', 'rate']
        
        if sort_by not in valid_sorts:
            await ctx.send(f"❌ Неверный параметр сортировки! Доступные: {', '.join(valid_sorts)}", ephemeral=True)
            return
        
        cursor = self.db.conn.cursor()
        
        # Определяем сортировку
        if sort_by == 'profit':
            order = 'robbery_profit DESC'
            title = "💰 Топ по награбленному"
        elif sort_by == 'success':
            order = 'robbery_success DESC'
            title = "✅ Топ по успешным ограблениям"
        elif sort_by == 'net':
            order = '(robbery_profit - robbery_loss) DESC'
            title = "📊 Топ по чистой прибыли"
        else:  # rate
            order = 'CAST(robbery_success AS FLOAT) / (robbery_success + robbery_fail) DESC'
            title = "🎯 Топ по эффективности"
        
        cursor.execute(f'''
            SELECT user_id, robbery_success, robbery_fail, robbery_profit, robbery_loss
            FROM users 
            WHERE guild_id = ? AND (robbery_success > 0 OR robbery_fail > 0)
            ORDER BY {order}
            LIMIT 10
        ''', (ctx.guild.id,))
        
        leaders = cursor.fetchall()
        
        if not leaders:
            embed = discord.Embed(
                title="📊 Топ воришек",
                description="Пока никто не пытался грабить других игроков.",
                color=0x808080
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"{title}",
            color=0x3498db
        )
        
        for i, (user_id, success, fail, profit, loss) in enumerate(leaders, 1):
            user = self.bot.get_user(user_id)
            username = user.name if user else f"Неизвестный ({user_id})"
            
            net_profit = profit - loss
            total_attempts = success + fail
            success_rate = (success / total_attempts * 100) if total_attempts > 0 else 0
            
            if sort_by == 'profit':
                value = f"💰 {profit} монет"
            elif sort_by == 'success':
                value = f"✅ {success} успехов"
            elif sort_by == 'net':
                value = f"📊 {net_profit} монет"
            else:  # rate
                value = f"🎯 {success_rate:.1f}%"
            
            embed.add_field(
                name=f"{i}. {username}",
                value=f"{value}\nУспехов: {success} | Провалов: {fail}\nЧистая прибыль: {net_profit} монет",
                inline=False
            )
        
        embed.set_footer(text=f"Сортировка: {sort_by} | Используйте /robstats для своей статистики")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='rob', description='Попытаться ограбить другого пользователя')
    @app_commands.describe(
        victim='Жертва ограбления',
        amount='Сумма для ограбления (необязательно, если не указано - случайная)'
    )
    async def rob(self, ctx, victim: discord.Member, amount: int = 0):
        """Попытка ограбления другого пользователя"""
        try:
            # Проверяем базовые условия
            if victim.bot:
                await ctx.send("❌ Нельзя грабить ботов!", ephemeral=True)
                return
            
            if victim.id == ctx.author.id:
                await ctx.send("❌ Нельзя грабить самого себя!", ephemeral=True)
                return
            
            # Получаем настройки ограблений
            settings = self.db.get_server_settings(ctx.guild.id)
            
            # Используем настройки вместо хардкода
            RICH_BAL = settings[18] if len(settings) > 18 else 25  # rob_rich_bal
            POOR_BAL = settings[19] if len(settings) > 19 else 7   # rob_poor_bal
            PARTS = settings[20] if len(settings) > 20 else 3      # rob_parts
            THRESHOLD = settings[21] if len(settings) > 21 else 10000  # rob_threshold
            MIN_VICTIM_BALANCE = settings[22] if len(settings) > 22 else 100  # rob_min_victim_balance
            MIN_ROB_AMOUNT = settings[23] if len(settings) > 23 else 50  # rob_min_amount
            MAX_ROB_AMOUNT = settings[24] if len(settings) > 24 else 5000  # rob_max_amount
            robbery_cooldown = settings[25] if len(settings) > 25 else 3600  # rob_cooldown
            success_chance = settings[26] if len(settings) > 26 else 0.5  # rob_base_chance
            level_penalty = settings[27] if len(settings) > 27 else 0.05  # rob_level_penalty
            
            # Проверяем кулдаун
            cursor = self.db.conn.cursor()
            cursor.execute('''
                SELECT cooldown_until FROM robbery_cooldowns 
                WHERE user_id = ? AND guild_id = ?
            ''', (ctx.author.id, ctx.guild.id))
            
            cooldown_data = cursor.fetchone()
            current_time = datetime.now().timestamp()
            
            if cooldown_data and cooldown_data[0] > current_time:
                remaining = int(cooldown_data[0] - current_time)
                minutes = remaining // 60
                seconds = remaining % 60
                await ctx.send(f"⏰ Вы можете ограбить кого-то снова через {minutes} минут {seconds} секунд!", ephemeral=True)
                return
            
            # Получаем данные грабителя и жертвы
            robber_data = self.db.get_user(ctx.author.id, ctx.guild.id)
            victim_data = self.db.get_user(victim.id, ctx.guild.id)
            
            # Проверяем минимальный баланс жертвы
            if victim_data[2] < MIN_VICTIM_BALANCE:
                await ctx.send(f"❌ У {victim.mention} меньше {MIN_VICTIM_BALANCE} монет, нечего грабить!", ephemeral=True)
                return
            
            # Определяем баланс для формулы
            # Для удачного ограбления - баланс жертвы
            # Для неудачного - баланс грабителя
            balance_for_formula = victim_data[2] if amount == 0 else min(amount, victim_data[2])
            
            # Определяем коэффициент деления
            div_coeff = RICH_BAL if balance_for_formula > THRESHOLD else POOR_BAL
            
            # Вычисляем базовую сумму
            base_amount = balance_for_formula / div_coeff
            calculated_amount = int(base_amount / PARTS)
            
            # Гарантируем минимальную и максимальную сумму
            calculated_amount = max(MIN_ROB_AMOUNT, min(calculated_amount, MAX_ROB_AMOUNT))
            
            # Если указана сумма, проверяем её
            if amount > 0:
                if amount > victim_data[2]:
                    await ctx.send(f"❌ У {victim.mention} недостаточно монет для ограбления на {amount}!", ephemeral=True)
                    return
                if amount > robber_data[2] * 2:  # При неудаче может потерять в 2 раза больше
                    await ctx.send(f"❌ У вас недостаточно монет для риска! При неудаче вы можете потерять до {amount * 2} монет.", ephemeral=True)
                    return
                calculated_amount = min(amount, calculated_amount)
            
            # Определяем шанс успеха (берём из настроек)
            success_chance = settings[26] if len(settings) > 26 else 0.5  # rob_base_chance
            
            # Добавляем фактор уровня (если у жертвы выше уровень, шанс меньше)
            robber_level = robber_data[4]
            victim_level = victim_data[4]
            
            if victim_level > robber_level:
                level_diff = victim_level - robber_level
                success_chance -= level_diff * level_penalty  # -5% за каждый уровень разницы
                success_chance = max(0.1, success_chance)  # Минимум 10% шанс
            
            # Случайный исход
            is_success = random.random() < success_chance
            
            # Фразы для ограбления
            success_phrases = [
                f"Вы ловко выхватили кошелёк у {victim.mention} и сбежали с **{calculated_amount}** монет! 🏃‍♂️💰",
                f"Пока {victim.mention} отвлёкся, вы стащили у него **{calculated_amount}** монет! 👀👋",
                f"Быстрая и чистая работа! Вы ограбили {victim.mention} на **{calculated_amount}** монет! 🦹‍♂️💵",
                f"В темном переулке вы успешно обобрали {victim.mention} и забрали **{calculated_amount}** монет! 🌃👊",
                f"Мастерство вора не подводит! {victim.mention} потерял **{calculated_amount}** монет из-за вас! 🎩✨"
            ]
            
            fail_phrases = [
                f"Вас поймала стража при попытке ограбить {victim.mention}! Штраф: **{calculated_amount * 2}** монет! 👮‍♂️🚔",
                f"{victim.mention} оказался сильнее и отобрал у вас **{calculated_amount * 2}** монет в качестве компенсации! 💪😡",
                f"Ограбление провалилось! Вы заплатили {victim.mention} **{calculated_amount}** монет и потеряли ещё **{calculated_amount}** в качестве штрафа! 😭💸",
                f"Полиция задержала вас! Штраф: **{calculated_amount * 2}** монет, из которых {victim.mention} получает **{calculated_amount}**! 🚨👮",
                f"Неудачная попытка! {victim.mention} защитил свой кошелёк, а вы потеряли **{calculated_amount * 2}** монет! 🛡️❌"
            ]
            
            embed = discord.Embed(color=0x00ff00 if is_success else 0xff0000)
            
            if is_success:
                # Успешное ограбление
                phrase = random.choice(success_phrases)
                embed.title = "✅ Ограбление удалось!"
                embed.description = phrase
                
                # Переводим деньги от жертвы к грабителю
                self.db.update_balance(victim.id, ctx.guild.id, -calculated_amount)
                self.db.update_balance(ctx.author.id, ctx.guild.id, calculated_amount)
                
                # Обновляем статистику
                cursor.execute('''
                    UPDATE users 
                    SET robbery_success = robbery_success + 1,
                        robbery_profit = robbery_profit + ?,
                        last_robbery = ?
                    WHERE user_id = ? AND guild_id = ?
                ''', (calculated_amount, int(current_time), ctx.author.id, ctx.guild.id))
                
                cursor.execute('''
                    UPDATE users 
                    SET robbery_loss = robbery_loss + ?
                    WHERE user_id = ? AND guild_id = ?
                ''', (calculated_amount, victim.id, ctx.guild.id))
                
                # Проверяем достижения
                achievements_cog = self.bot.get_cog('Achievements')
                if achievements_cog:
                    cursor.execute('''
                        SELECT robbery_success FROM users 
                        WHERE user_id = ? AND guild_id = ?
                    ''', (ctx.author.id, ctx.guild.id))
                    result = cursor.fetchone()
                    robber_success_count = result[0] if result else 0
                    await achievements_cog.check_achievements(ctx.author.id, ctx.guild.id, 'robbery_success', robber_success_count)
            
            else:
                # Неудачное ограбление
                phrase = random.choice(fail_phrases)
                embed.title = "❌ Ограбление провалилось!"
                embed.description = phrase
                
                # Проверяем, что у грабителя достаточно денег
                if robber_data[2] < calculated_amount * 2:
                    # Если нет, берём максимум что есть
                    max_loss = robber_data[2]
                    victim_gain = int(max_loss / 2)
                    calculated_amount = victim_gain
                    
                    embed.description = f"У вас было недостаточно денег для полного штрафа! Вы потеряли все свои {max_loss} монет, {victim.mention} получает {victim_gain} монет! 💸😢"
                
                # Грабитель теряет calculated_amount * 2
                loss_amount = calculated_amount * 2
                self.db.update_balance(ctx.author.id, ctx.guild.id, -loss_amount)
                
                # Жертва получает calculated_amount
                self.db.update_balance(victim.id, ctx.guild.id, calculated_amount)
                
                # Обновляем статистику
                cursor.execute('''
                    UPDATE users 
                    SET robbery_fail = robbery_fail + 1,
                        robbery_loss = robbery_loss + ?,
                        last_robbery = ?
                    WHERE user_id = ? AND guild_id = ?
                ''', (loss_amount, int(current_time), ctx.author.id, ctx.guild.id))
                
                cursor.execute('''
                    UPDATE users 
                    SET robbery_profit = robbery_profit + ?
                    WHERE user_id = ? AND guild_id = ?
                ''', (calculated_amount, victim.id, ctx.guild.id))
                
                # Проверяем достижения
                achievements_cog = self.bot.get_cog('Achievements')
                if achievements_cog:
                    cursor.execute('''
                        SELECT robbery_fail FROM users 
                        WHERE user_id = ? AND guild_id = ?
                    ''', (ctx.author.id, ctx.guild.id))
                    result = cursor.fetchone()
                    robber_fail_count = result[0] if result else 0
                    await achievements_cog.check_achievements(ctx.author.id, ctx.guild.id, 'robbery_fail', robber_fail_count)
            
            # Устанавливаем кулдаун
            cursor.execute('''
                INSERT OR REPLACE INTO robbery_cooldowns (user_id, guild_id, last_robbery, cooldown_until)
                VALUES (?, ?, ?, ?)
            ''', (ctx.author.id, ctx.guild.id, int(current_time), int(current_time + robbery_cooldown)))
            
            # Добавляем информацию в embed
            if is_success:
                embed.add_field(name="💰 Украдено", value=f"{calculated_amount} монет", inline=True)
                embed.add_field(name="🎯 Шанс успеха", value=f"{int(success_chance * 100)}%", inline=True)
            else:
                embed.add_field(name="💸 Потеряно", value=f"{calculated_amount * 2} монет", inline=True)
                embed.add_field(name="🎁 Компенсация жертве", value=f"{calculated_amount} монет", inline=True)
                embed.add_field(name="🎯 Шанс успеха был", value=f"{int(success_chance * 100)}%", inline=True)
            
            # Показываем новые балансы
            cursor.execute('SELECT balance FROM users WHERE user_id = ? AND guild_id = ?', 
                         (ctx.author.id, ctx.guild.id))
            robber_new_bal = cursor.fetchone()
            robber_new_bal_value = robber_new_bal[0] if robber_new_bal else 0
            
            cursor.execute('SELECT balance FROM users WHERE user_id = ? AND guild_id = ?', 
                         (victim.id, ctx.guild.id))
            victim_new_bal = cursor.fetchone()
            victim_new_bal_value = victim_new_bal[0] if victim_new_bal else 0
            
            embed.add_field(name="📊 Ваш новый баланс", value=f"{robber_new_bal_value} монет", inline=True)
            embed.add_field(name="📊 Баланс жертвы", value=f"{victim_new_bal_value} монет", inline=True)
            
            # Показываем использованные настройки
            embed.add_field(
                name="⚙️ Использованные настройки", 
                value=f"Делитель: {div_coeff} ({'богатый' if div_coeff == RICH_BAL else 'бедный'})\nЧастей: {PARTS}\nПорог: {THRESHOLD} монет", 
                inline=False
            )
            
            self.db.conn.commit()
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"❌ Ошибка в команде rob: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send("❌ Произошла ошибка при попытке ограбления. Попробуйте позже.", ephemeral=True)
    
    @commands.hybrid_command(name='setbalance', description='Установить баланс пользователя')
    @app_commands.describe(
        member='Пользователь, которому установить баланс',
        amount='Новое значение баланса'
    )
    @has_permission('admin', 'high_admin', 'owner')
    async def set_balance(self, ctx, member: discord.Member, amount: int):
        try:
            if amount < 0:
                await ctx.send("❌ Баланс не может быть отрицательным!")
                return
                
            self.db.set_balance(member.id, ctx.guild.id, amount)
            await ctx.send(f"✅ Баланс {member.mention} установлен на {amount} монет")
        except Exception as e:
            await ctx.send(f"❌ Ошибка установки баланса: {e}")

async def setup(bot):
    await bot.add_cog(Economy(bot))