import discord
from discord.ext import commands
import random
from utils.database import Database
from datetime import datetime

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
    
    @commands.command(name='work')
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
    
    @commands.command(name='resetwork')
    @commands.has_permissions(administrator=True)
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
    
    @commands.command(name='slots')
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
    
    @commands.command(name='balance')
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
    
    @commands.command(name='transfer')
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
    
    @commands.command(name='leaderboardec', aliases=['lbec'])
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
    
    @commands.command(name='addec')
    @commands.has_permissions(administrator=True)
    async def add_ec(self, ctx, member: discord.Member, amount: int):
        try:
            if amount <= 0:
                await ctx.send("❌ Сумма должна быть положительной!")
                return
                
            self.db.update_balance(member.id, ctx.guild.id, amount)
            await ctx.send(f"✅ {member.mention} выдано {amount} монет")
        except Exception as e:
            await ctx.send(f"❌ Ошибка выдачи: {e}")
    
    @commands.command(name='removeec')
    @commands.has_permissions(administrator=True)
    async def remove_ec(self, ctx, member: discord.Member, amount: int):
        try:
            if amount <= 0:
                await ctx.send("❌ Сумма должна быть положительной!")
                return
                
            self.db.update_balance(member.id, ctx.guild.id, -amount)
            await ctx.send(f"✅ У {member.mention} забрано {amount} монет")
        except Exception as e:
            await ctx.send(f"❌ Ошибка изъятия: {e}")
    
    @commands.command(name='setbalance')
    @commands.has_permissions(administrator=True)
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