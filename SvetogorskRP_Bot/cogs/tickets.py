import discord
from discord.ext import commands
from utils.database import Database
import asyncio

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    async def check_permissions(self, ctx):
        cursor = self.db.conn.cursor()
        
        admin_roles = []
        for group in ['admin', 'high_admin', 'owner']:
            cursor.execute('SELECT role_id FROM role_assignments WHERE guild_id = ? AND role_group = ?', (ctx.guild.id, group))
            roles = cursor.fetchall()
            admin_roles.extend([role[0] for role in roles])
        
        user_roles = [role.id for role in ctx.author.roles]
        has_permission = any(role_id in user_roles for role_id in admin_roles)
        
        if not has_permission:
            has_permission = ctx.author.guild_permissions.manage_guild
        
        return has_permission

    async def get_log_channel(self, guild_id):
        settings = self.db.get_server_settings(guild_id)
        if not settings[9]:
            return None
        
        channel_id = settings[10]
        if not channel_id:
            return None
        
        return self.bot.get_channel(channel_id)

    async def send_ticket_log(self, guild, embed):
        channel = await self.get_log_channel(guild.id)
        if channel:
            try:
                await channel.send(embed=embed)
            except:
                pass

    async def get_tickets_category(self, guild):
        """Получает или создает категорию для тикетов"""
        # Ищем существующую категорию "ТИКЕТЫ"
        category = discord.utils.get(guild.categories, name="ТИКЕТЫ")
        
        if not category:
            # Создаем новую категорию
            try:
                category = await guild.create_category_channel(
                    name="ТИКЕТЫ",
                    position=0  # Помещаем вверх списка
                )
                
                # Настраиваем права доступа для категории
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
                }
                
                await category.edit(overwrites=overwrites)
                
            except Exception as e:
                print(f"❌ Ошибка создания категории ТИКЕТЫ: {e}")
                return None
        
        return category

    @commands.group(name='ticket', invoke_without_command=True)
    async def ticket(self, ctx):
        """Система тикетов"""
        await ctx.send_help(ctx.command)

    @ticket.command(name='create')
    async def create_ticket(self, ctx, ticket_type: str, *, description: str):
        """Создать тикет
        
        Типы тикетов:
        - помощь - для получения помощи
        - жалоба - для жалоб на пользователей
        """
        ticket_type = ticket_type.lower()
        
        if ticket_type not in ['помощь', 'жалоба']:
            await ctx.send("❌ Неверный тип тикета! Используйте: `помощь` или `жалоба`")
            return
        
        if len(description) < 10:
            await ctx.send("❌ Описание проблемы должно содержать минимум 10 символов!")
            return
        
        # Проверяем есть ли уже активные тикеты у пользователя
        user_tickets = self.db.get_user_tickets(ctx.author.id, ctx.guild.id)
        if user_tickets:
            embed = discord.Embed(
                title="❌ У вас уже есть активный тикет!",
                description="Пожалуйста, закройте существующий тикет перед созданием нового.",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        # Получаем роль для этого типа тикетов
        support_role_id = self.db.get_ticket_group(ctx.guild.id, ticket_type)
        if not support_role_id:
            embed = discord.Embed(
                title="❌ Система тикетов не настроена!",
                description=f"Администратор должен настроить роль для тикетов типа '{ticket_type}' с помощью команды:\n`!settings ticket group {ticket_type} @роль`",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        support_role = ctx.guild.get_role(support_role_id)
        if not support_role:
            embed = discord.Embed(
                title="❌ Роль поддержки не найдена!",
                description="Роль для этого типа тикетов была удалена. Обратитесь к администратору.",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        # Получаем или создаем категорию для тикетов
        category = await self.get_tickets_category(ctx.guild)
        if not category:
            embed = discord.Embed(
                title="❌ Ошибка создания тикета!",
                description="Не удалось создать категорию для тикетов. Проверьте права бота.",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        # Создаем канал для тикета в категории ТИКЕТЫ
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            support_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        }
        
        try:
            # Создаем уникальное имя канала
            ticket_number = len(self.db.get_all_tickets(ctx.guild.id)) + 1
            channel_name = f"{ticket_type}-{ctx.author.name}-{ticket_number}"
            
            # Ограничиваем длину имени канала (максимум 100 символов)
            if len(channel_name) > 100:
                channel_name = channel_name[:100]
            
            ticket_channel = await ctx.guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=category
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Ошибка создания тикета!",
                description=f"Не удалось создать канал для тикета: {str(e)}",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        # Сохраняем тикет в базу
        self.db.create_ticket(ticket_channel.id, ctx.guild.id, ctx.author.id, ticket_type)
        
        # Отправляем приветственное сообщение в тикет
        embed = discord.Embed(
            title=f"🎫 Тикет {ticket_type}",
            description=f"Тикет создан пользователем {ctx.author.mention}",
            color=0x00ff00
        )
        
        embed.add_field(name="📝 Описание проблемы", value=description, inline=False)
        embed.add_field(name="⚙️ Команды", value="`!ticket close` - закрыть тикет\n`!ticket add @user` - добавить пользователя\n`!ticket remove @user` - удалить пользователя", inline=False)
        embed.add_field(name="💡 Подсказка", value="Для быстрого закрытия тикета используйте кнопку ниже ⬇️", inline=False)
        
        # Создаем кнопку для закрытия тикета
        class CloseTicketView(discord.ui.View):
            def __init__(self, cog):
                super().__init__(timeout=None)
                self.cog = cog
            
            @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, emoji="🔒")
            async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                ticket = self.cog.db.get_ticket(interaction.channel.id)
                if not ticket:
                    await interaction.response.send_message("❌ Этот канал не является тикетом!", ephemeral=True)
                    return
                
                channel_id, guild_id, user_id, ticket_type, created_at = ticket
                
                # Проверяем права
                is_author = interaction.user.id == user_id
                has_permission = await self.cog.check_permissions(interaction)
                
                if not is_author and not has_permission:
                    await interaction.response.send_message("❌ Только автор тикета или администратор может закрыть тикет!", ephemeral=True)
                    return
                
                # Закрываем тикет
                await interaction.response.send_message("🔒 Закрытие тикета...")
                
                # Удаляем тикет из базы
                self.cog.db.delete_ticket(interaction.channel.id)
                
                # Удаляем канал
                await interaction.channel.delete()
        
        view = CloseTicketView(self)
        
        await ticket_channel.send(f"{support_role.mention} {ctx.author.mention}", embed=embed, view=view)
        
        # Подтверждение создания тикета
        embed = discord.Embed(
            title="✅ Тикет создан!",
            description=f"Ваш тикет создан: {ticket_channel.mention}\nКатегория: {category.mention}",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        
        # Логирование
        log_embed = discord.Embed(
            title="🎫 Создан новый тикет",
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="👤 Пользователь", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="📋 Тип", value=ticket_type, inline=True)
        log_embed.add_field(name="🔢 Номер", value=ticket_number, inline=True)
        log_embed.add_field(name="📁 Категория", value=category.mention, inline=True)
        log_embed.add_field(name="📝 Описание", value=description, inline=False)
        await self.send_ticket_log(ctx.guild, log_embed)

    @ticket.command(name='close')
    async def close_ticket(self, ctx):
        """Закрыть тикет"""
        # Проверяем что команда вызвана в канале тикета
        ticket = self.db.get_ticket(ctx.channel.id)
        if not ticket:
            embed = discord.Embed(
                title="❌ Эта команда работает только в каналах тикетов!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        channel_id, guild_id, user_id, ticket_type, created_at = ticket
        
        # Проверяем права
        is_author = ctx.author.id == user_id
        has_permission = await self.check_permissions(ctx)
        
        if not is_author and not has_permission:
            embed = discord.Embed(
                title="❌ Недостаточно прав!",
                description="Закрывать тикет может только автор тикета или администратор.",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        # Получаем информацию о тикете
        user = ctx.guild.get_member(user_id)
        username = user.display_name if user else "Неизвестный пользователь"
        
        # Создаем лог перед удалением
        messages = []
        async for message in ctx.channel.history(limit=100, oldest_first=True):
            if message.content and not message.author.bot:
                messages.append(f"{message.author.display_name}: {message.content}")
        
        log_content = "\n".join(messages[-20:])  # Последние 20 сообщений
        
        # Отправляем подтверждение закрытия
        embed = discord.Embed(
            title="🔒 Закрытие тикета",
            description="Тикет будет закрыт через 5 секунд...",
            color=0xffa500
        )
        await ctx.send(embed=embed)
        
        await asyncio.sleep(5)
        
        # Удаляем тикет из базы
        self.db.delete_ticket(ctx.channel.id)
        
        # Удаляем канал
        await ctx.channel.delete()
        
        # Логирование закрытия тикета
        log_embed = discord.Embed(
            title="🎫 Тикет закрыт",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="👤 Пользователь", value=user.mention if user else "Неизвестный", inline=True)
        log_embed.add_field(name="📋 Тип", value=ticket_type, inline=True)
        log_embed.add_field(name="🔒 Закрыл", value=ctx.author.mention, inline=True)
        
        if len(log_content) > 0:
            if len(log_content) > 1000:
                log_content = log_content[:1000] + "..."
            log_embed.add_field(name="💬 Последние сообщения", value=f"```{log_content}```", inline=False)
        
        await self.send_ticket_log(ctx.guild, log_embed)

    @ticket.command(name='add')
    async def add_user(self, ctx, member: discord.Member):
        """Добавить пользователя в тикет"""
        ticket = self.db.get_ticket(ctx.channel.id)
        if not ticket:
            embed = discord.Embed(
                title="❌ Эта команда работает только в каналах тикетов!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        channel_id, guild_id, user_id, ticket_type, created_at = ticket
        
        # Проверяем права
        is_author = ctx.author.id == user_id
        has_permission = await self.check_permissions(ctx)
        
        if not is_author and not has_permission:
            embed = discord.Embed(
                title="❌ Недостаточно прав!",
                description="Добавлять пользователей может только автор тикета или администратор.",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        # Добавляем права доступа
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        
        embed = discord.Embed(
            title="✅ Пользователь добавлен",
            description=f"{member.mention} был добавлен в тикет",
            color=0x00ff00
        )
        await ctx.send(embed=embed)

    @ticket.command(name='remove')
    async def remove_user(self, ctx, member: discord.Member):
        """Удалить пользователя из тикета"""
        ticket = self.db.get_ticket(ctx.channel.id)
        if not ticket:
            embed = discord.Embed(
                title="❌ Эта команда работает только в каналах тикетов!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        channel_id, guild_id, user_id, ticket_type, created_at = ticket
        
        # Проверяем права
        has_permission = await self.check_permissions(ctx)
        
        if not has_permission:
            embed = discord.Embed(
                title="❌ Недостаточно прав!",
                description="Удалять пользователей может только администратор.",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        # Не позволяем удалить автора тикета
        if member.id == user_id:
            embed = discord.Embed(
                title="❌ Ошибка!",
                description="Нельзя удалить автора тикета.",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        # Убираем права доступа
        await ctx.channel.set_permissions(member, overwrite=None)
        
        embed = discord.Embed(
            title="✅ Пользователь удален",
            description=f"{member.mention} был удален из тикета",
            color=0x00ff00
        )
        await ctx.send(embed=embed)

    @ticket.command(name='list')
    @commands.has_permissions(administrator=True)
    async def list_tickets(self, ctx):
        """Список активных тикетов (админ)"""
        tickets = self.db.get_all_tickets(ctx.guild.id)
        
        if not tickets:
            embed = discord.Embed(
                title="🎫 Активные тикеты",
                description="Активных тикетов нет",
                color=0x3498db
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🎫 Активные тикеты",
            color=0x3498db
        )
        
        for ticket in tickets:
            channel_id, guild_id, user_id, ticket_type, created_at = ticket
            
            user = ctx.guild.get_member(user_id)
            username = user.display_name if user else "Неизвестный"
            channel = ctx.guild.get_channel(channel_id)
            
            if channel:
                embed.add_field(
                    name=f"{ticket_type} - {username}",
                    value=f"Канал: {channel.mention}\nСоздан: <t:{created_at}:R>",
                    inline=False
                )
        
        await ctx.send(embed=embed)

    @ticket.command(name='cleanup')
    @commands.has_permissions(administrator=True)
    async def cleanup_tickets(self, ctx):
        """Очистка несуществующих тикетов из базы данных (админ)"""
        tickets = self.db.get_all_tickets(ctx.guild.id)
        deleted_count = 0
        
        for ticket in tickets:
            channel_id, guild_id, user_id, ticket_type, created_at = ticket
            
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                # Канал не существует, удаляем из базы
                self.db.delete_ticket(channel_id)
                deleted_count += 1
        
        embed = discord.Embed(
            title="🧹 Очистка тикетов",
            description=f"Удалено {deleted_count} несуществующих тикетов из базы данных",
            color=0x00ff00
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Удаление тикета из базы при удалении канала"""
        if not isinstance(channel, discord.TextChannel):
            return
        
        ticket = self.db.get_ticket(channel.id)
        if ticket:
            self.db.delete_ticket(channel.id)

async def setup(bot):
    await bot.add_cog(Tickets(bot))