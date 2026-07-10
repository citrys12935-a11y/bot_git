import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio
import random

class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        from utils.database import Database
        self.db = Database()
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    async def check_permissions(self, ctx):
        """Проверка прав через систему групп ролей"""
        cursor = self.db.conn.cursor()
        
        # Проверяем группы admin, high_admin, owner
        admin_roles = []
        for group in ['admin', 'high_admin', 'owner']:
            cursor.execute('SELECT role_id FROM role_assignments WHERE guild_id = ? AND role_group = ?', (ctx.guild.id, group))
            roles = cursor.fetchall()
            admin_roles.extend([role[0] for role in roles])
        
        # Проверяем есть ли у пользователя одна из этих ролей
        user_roles = [role.id for role in ctx.author.roles]
        has_permission = any(role_id in user_roles for role_id in admin_roles)
        
        # Если нет ролей через систему, проверяем стандартные права Discord
        if not has_permission:
            has_permission = ctx.author.guild_permissions.manage_guild
        
        return has_permission

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        try:
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT * FROM giveaways WHERE end_time <= ? AND ended = 0', (int(datetime.now().timestamp()),))
            giveaways = cursor.fetchall()
            
            for giveaway in giveaways:
                await self.end_giveaway(giveaway)
                
        except Exception as e:
            print(f"❌ Ошибка проверки розыгрышей: {e}")

    async def end_giveaway(self, giveaway):
        try:
            message_id, guild_id, channel_id, prize, winners_count, end_time, ended = giveaway
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
                
            channel = guild.get_channel(channel_id)
            if not channel:
                return
            
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT user_id FROM giveaway_entries WHERE message_id = ?', (message_id,))
            entries = [row[0] for row in cursor.fetchall()]
            
            if not entries:
                embed = discord.Embed(
                    title="🎉 Розыгрыш завершен!",
                    description=f"**Приз:** {prize}",
                    color=0xff0000
                )
                embed.add_field(name="🏆 Победители", value="❌ Не было участников", inline=False)
                embed.add_field(name="👥 Участников", value="0", inline=True)
                embed.set_footer(text="Розыгрыш завершен")
                
                try:
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
                except:
                    pass
                
                cursor.execute('UPDATE giveaways SET ended = 1 WHERE message_id = ?', (message_id,))
                self.db.conn.commit()
                return
            
            winners = []
            available_entries = entries.copy()
            
            for _ in range(min(winners_count, len(available_entries))):
                if not available_entries:
                    break
                winner_id = random.choice(available_entries)
                winners.append(winner_id)
                available_entries = [uid for uid in available_entries if uid != winner_id]
            
            winners_mentions = []
            for winner_id in winners:
                winner = guild.get_member(winner_id)
                if winner:
                    winners_mentions.append(winner.mention)
                else:
                    winners_mentions.append(f"<@{winner_id}>")
            
            embed = discord.Embed(
                title="🎉 Розыгрыш завершен!",
                description=f"**Приз:** {prize}",
                color=0x00ff00
            )
            
            if winners_mentions:
                embed.add_field(
                    name=f"🏆 Победители ({len(winners_mentions)}):", 
                    value="\n".join(winners_mentions), 
                    inline=False
                )
            else:
                embed.add_field(name="🏆 Победители", value="❌ Не удалось определить победителей", inline=False)
            
            embed.add_field(name="👥 Участников", value=str(len(entries)), inline=True)
            embed.set_footer(text="Розыгрыш завершен")
            
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
                
                if winners_mentions:
                    winners_text = " ".join(winners_mentions)
                    await channel.send(f"🎉 Поздравляем победителей! {winners_text}\n**Вы выиграли:** {prize}")
            except:
                pass
            
            cursor.execute('UPDATE giveaways SET ended = 1 WHERE message_id = ?', (message_id,))
            self.db.conn.commit()
            
        except Exception as e:
            print(f"❌ Ошибка завершения розыгрыша: {e}")

    @commands.hybrid_command(name='giveaway', aliases=['gstart'], description='Запустить розыгрыш')
    @app_commands.describe(
        duration="Длительность розыгрыша (10s, 5m, 1h, 7d)",
        winners="Количество победителей",
        prize="Приз розыгрыша"
    )
    async def giveaway_start(self, ctx, duration: str, winners: int, *, prize: str):
        """Запустить розыгрыш"""
        # Проверка прав
        if not await self.check_permissions(ctx):
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У вас недостаточно прав для запуска розыгрышей!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        if winners < 1:
            await ctx.send("❌ Количество победителей должно быть больше 0!")
            return
        
        if winners > 50:
            await ctx.send("❌ Слишком много победителей! Максимум 50.")
            return
        
        try:
            time_amount = int(duration[:-1])
            time_unit = duration[-1].lower()
            
            if time_unit == 's':
                delta = timedelta(seconds=time_amount)
                time_display = f"{time_amount} секунд"
            elif time_unit == 'm':
                delta = timedelta(minutes=time_amount)
                time_display = f"{time_amount} минут"
            elif time_unit == 'h':
                delta = timedelta(hours=time_amount)
                time_display = f"{time_amount} часов"
            elif time_unit == 'd':
                delta = timedelta(days=time_amount)
                time_display = f"{time_amount} дней"
            else:
                await ctx.send("❌ Неверный формат времени! Используйте: s, m, h, d")
                return
        except ValueError:
            await ctx.send("❌ Неверный формат времени! Пример: `10m`, `1h`, `7d`")
            return
        
        end_time = datetime.now() + delta
        end_timestamp = int(end_time.timestamp())
        
        embed = discord.Embed(
            title="🎉 РОЗЫГРЫШ!",
            description=f"**Приз:** {prize}",
            color=0x00ff00,
            timestamp=end_time
        )
        embed.add_field(name="🏆 Победителей", value=str(winners), inline=True)
        embed.add_field(name="⏰ Окончание", value=f"<t:{end_timestamp}:R>", inline=True)
        embed.add_field(name="🎫 Участвовать", value="Нажмите на кнопку ниже!", inline=False)
        embed.set_footer(text="Розыгрыш активен")
        
        view = discord.ui.View()
        button = discord.ui.Button(style=discord.ButtonStyle.primary, label="🎫 Участвовать", custom_id="giveaway_join")
        view.add_item(button)
        
        message = await ctx.send(embed=embed, view=view)
        
        cursor = self.db.conn.cursor()
        cursor.execute('''
            INSERT INTO giveaways (message_id, guild_id, channel_id, prize, winners_count, end_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (message.id, ctx.guild.id, ctx.channel.id, prize, winners, end_timestamp))
        self.db.conn.commit()
        
        await ctx.send(f"✅ Розыгрыш запущен! Он завершится {time_display}.")

    @commands.hybrid_command(name='greroll', description='Перевыбрать победителей розыгрыша')
    @app_commands.describe(
        message_id="ID сообщения розыгрыша"
    )
    async def giveaway_reroll(self, ctx, message_id: int):
        """Перевыбрать победителей розыгрыша"""
        # Проверка прав
        if not await self.check_permissions(ctx):
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У вас недостаточно прав для перевыбора победителей!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        try:
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT * FROM giveaways WHERE message_id = ?', (message_id,))
            giveaway = cursor.fetchone()
            
            if not giveaway:
                await ctx.send("❌ Розыгрыш не найден!")
                return
            
            message_id, guild_id, channel_id, prize, winners_count, end_time, ended = giveaway
            
            if not ended:
                await ctx.send("❌ Этот розыгрыш еще не завершен!")
                return
            
            cursor.execute('SELECT user_id FROM giveaway_entries WHERE message_id = ?', (message_id,))
            entries = [row[0] for row in cursor.fetchall()]
            
            if not entries:
                await ctx.send("❌ Не было участников для перевыбора!")
                return
            
            winners = []
            available_entries = entries.copy()
            
            for _ in range(min(winners_count, len(available_entries))):
                if not available_entries:
                    break
                winner_id = random.choice(available_entries)
                winners.append(winner_id)
                available_entries = [uid for uid in available_entries if uid != winner_id]
            
            winners_mentions = []
            for winner_id in winners:
                winner = ctx.guild.get_member(winner_id)
                if winner:
                    winners_mentions.append(winner.mention)
                else:
                    winners_mentions.append(f"<@{winner_id}>")
            
            if winners_mentions:
                winners_text = " ".join(winners_mentions)
                await ctx.send(f"🎉 Новые победители! {winners_text}\n**Вы выиграли:** {prize}")
            else:
                await ctx.send("❌ Не удалось определить новых победителей!")
                
        except Exception as e:
            await ctx.send(f"❌ Ошибка перевыбора: {e}")

    @commands.hybrid_command(name='gend', description='Досрочно завершить розыгрыш')
    @app_commands.describe(
        message_id="ID сообщения розыгрыша"
    )
    async def giveaway_end(self, ctx, message_id: int):
        """Досрочно завершить розыгрыш"""
        # Проверка прав
        if not await self.check_permissions(ctx):
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У вас недостаточно прав для завершения розыгрышей!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        try:
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT * FROM giveaways WHERE message_id = ?', (message_id,))
            giveaway = cursor.fetchone()
            
            if not giveaway:
                await ctx.send("❌ Розыгрыш не найден!")
                return
            
            if giveaway[6]:
                await ctx.send("❌ Этот розыгрыш уже завершен!")
                return
            
            cursor.execute('UPDATE giveaways SET end_time = ? WHERE message_id = ?', 
                         (int(datetime.now().timestamp()), message_id))
            self.db.conn.commit()
            
            await ctx.send("✅ Розыгрыш завершен досрочно! Результаты появятся через несколько секунд.")
            
        except Exception as e:
            await ctx.send(f"❌ Ошибка завершения: {e}")

    @commands.hybrid_command(name='glist', description='Показать активные розыгрыши')
    async def giveaway_list(self, ctx):
        """Показать активные розыгрыши"""
        # Эта команда доступна всем
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM giveaways WHERE guild_id = ? AND ended = 0 ORDER BY end_time ASC', (ctx.guild.id,))
        giveaways = cursor.fetchall()
        
        if not giveaways:
            embed = discord.Embed(
                title="🎉 Активные розыгрыши",
                description="Нет активных розыгрышей",
                color=0x3498db
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🎉 Активные розыгрыши",
            color=0x3498db
        )
        
        for giveaway in giveaways[:10]:
            message_id, guild_id, channel_id, prize, winners_count, end_time, ended = giveaway
            
            channel = ctx.guild.get_channel(channel_id)
            channel_name = channel.mention if channel else "Неизвестный канал"
            
            cursor.execute('SELECT COUNT(*) FROM giveaway_entries WHERE message_id = ?', (message_id,))
            participants_count = cursor.fetchone()[0]
            
            embed.add_field(
                name=f"🎁 {prize}",
                value=f"🏆 Победителей: {winners_count}\n👥 Участников: {participants_count}\n⏰ Окончание: <t:{end_time}:R>\n📺 Канал: {channel_name}",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        if not interaction.data or 'custom_id' not in interaction.data:
            return
        
        if interaction.data['custom_id'] == 'giveaway_join':
            await self.join_giveaway(interaction)

    async def join_giveaway(self, interaction):
        try:
            message_id = interaction.message.id
            
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT * FROM giveaways WHERE message_id = ? AND ended = 0', (message_id,))
            giveaway = cursor.fetchone()
            
            if not giveaway:
                await interaction.response.send_message("❌ Этот розыгрыш не активен!", ephemeral=True)
                return
            
            if datetime.now().timestamp() > giveaway[5]:
                await interaction.response.send_message("❌ Розыгрыш уже завершен!", ephemeral=True)
                return
            
            cursor.execute('SELECT 1 FROM giveaway_entries WHERE message_id = ? AND user_id = ?', 
                         (message_id, interaction.user.id))
            if cursor.fetchone():
                await interaction.response.send_message("❌ Вы уже участвуете в этом розыгрыше!", ephemeral=True)
                return
            
            cursor.execute('INSERT INTO giveaway_entries (message_id, user_id) VALUES (?, ?)', 
                         (message_id, interaction.user.id))
            self.db.conn.commit()
            
            await interaction.response.send_message("✅ Вы успешно присоединились к розыгрышу! 🎉", ephemeral=True)
            
        except Exception as e:
            print(f"❌ Ошибка участия в розыгрыше: {e}")
            await interaction.response.send_message("❌ Произошла ошибка при участии!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Giveaway(bot))