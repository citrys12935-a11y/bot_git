import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        from utils.database import Database
        self.db = Database()
        self.check_expired_items.start()

    def cog_unload(self):
        self.check_expired_items.cancel()

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

    async def send_shop_log(self, guild, embed):
        channel = await self.get_log_channel(guild.id)
        if channel:
            try:
                await channel.send(embed=embed)
            except:
                pass

    @tasks.loop(minutes=5)
    async def check_expired_items(self):
        try:
            expired_items = self.db.get_expired_items()
            for item in expired_items:
                user_id, guild_id, item_id, purchase_time, expires_at = item
                
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                    
                user = guild.get_member(user_id)
                if not user:
                    continue
                
                item_info = self.db.get_shop_item(item_id)
                if not item_info:
                    continue
                
                if item_info[5] == 'role' and item_info[6]:
                    role = guild.get_role(item_info[6])
                    if role and role in user.roles:
                        try:
                            await user.remove_roles(role)
                        except:
                            pass
                
                self.db.remove_inventory_item(user_id, guild_id, item_id)
                
                try:
                    embed = discord.Embed(
                        title="⏰ Срок действия предмета истек",
                        description=f"Предмет **{item_info[2]}** был удален из вашего инвентаря",
                        color=0xffa500
                    )
                    await user.send(embed=embed)
                except:
                    pass
                    
        except Exception as e:
            print(f"❌ Ошибка проверки просроченных предметов: {e}")

    @commands.command(name='shop')
    async def shop(self, ctx, page: int = 1):
        items = self.db.get_shop_items(ctx.guild.id)
        
        if not items:
            embed = discord.Embed(
                title="🛍️ Магазин",
                description="В магазине пока нет предметов!\nИспользуйте `!additem` чтобы добавить предмет (админ)",
                color=0x3498db
            )
            await ctx.send(embed=embed)
            return
        
        items_per_page = 5
        total_pages = (len(items) + items_per_page - 1) // items_per_page
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_items = items[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"🛍️ Магазин (Страница {page}/{total_pages})",
            description=f"Используйте `{ctx.prefix}buy <ID>` для покупки предмета\n`{ctx.prefix}shop <страница>` для навигации",
            color=0x3498db
        )
        
        for item in page_items:
            item_id, guild_id, name, description, price, item_type, role_id, duration, max_purchases, created_at = item
            
            item_info = f"**Цена:** {price} монет\n"
            item_info += f"**Тип:** {self.get_item_type_name(item_type)}\n"
            item_info += f"**ID:** {item_id}\n"
            
            if role_id:
                role = ctx.guild.get_role(role_id)
                if role:
                    item_info += f"**Роль:** {role.mention}\n"
            
            if duration > 0:
                days = duration // 86400
                item_info += f"**Длительность:** {days} дней\n"
            else:
                item_info += "**Длительность:** Бессрочно\n"
            
            if max_purchases != -1:
                item_info += f"**Лимит покупок:** {max_purchases}\n"
            
            item_info += f"**Описание:** {description}"
            
            embed.add_field(
                name=f"{name}",
                value=item_info,
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.command(name='buy')
    async def buy(self, ctx, item_id: int):
        items = self.db.get_shop_items(ctx.guild.id)
        
        if not items:
            await ctx.send("❌ В магазине нет предметов!")
            return
        
        item = self.db.get_shop_item(item_id)
        if not item:
            await ctx.send("❌ Предмет с таким ID не найден!")
            return
        
        success, message = self.db.purchase_item(ctx.author.id, ctx.guild.id, item_id)
        
        if success:
            embed = discord.Embed(
                title="✅ Покупка успешна!",
                description=f"Вы купили **{item[2]}** за {item[4]} монет",
                color=0x00ff00
            )
            
            if item[5] == 'role' and item[6]:
                role = ctx.guild.get_role(item[6])
                if role:
                    try:
                        await ctx.author.add_roles(role)
                        embed.add_field(name="🎁 Полученная роль", value=role.mention, inline=True)
                        
                        if item[7] > 0:
                            days = item[7] // 86400
                            embed.add_field(name="⏰ Длительность", value=f"{days} дней", inline=True)
                    except discord.Forbidden:
                        embed.add_field(name="⚠️ Внимание", value="Бот не может выдать эту роль", inline=True)
                    except Exception as e:
                        embed.add_field(name="⚠️ Ошибка", value="Не удалось выдать роль", inline=True)
            
            await ctx.send(embed=embed)
            
            log_embed = discord.Embed(
                title="🛍️ Покупка в магазине",
                color=0x00ff00,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Покупатель", value=ctx.author.mention, inline=True)
            log_embed.add_field(name="Предмет", value=item[2], inline=True)
            log_embed.add_field(name="Цена", value=f"{item[4]} монет", inline=True)
            await self.send_shop_log(ctx.guild, log_embed)
            
        else:
            embed = discord.Embed(
                title="❌ Ошибка покупки",
                description=message,
                color=0xff0000
            )
            await ctx.send(embed=embed)

    @commands.command(name='inventory', aliases=['inv'])
    async def inventory(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        inventory = self.db.get_user_inventory(member.id, ctx.guild.id)
        
        if not inventory:
            embed = discord.Embed(
                title="🎒 Инвентарь",
                description="Инвентарь пуст" if member == ctx.author else f"Инвентарь {member.display_name} пуст",
                color=0x3498db
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"🎒 Инвентарь {member.display_name}",
            color=0x3498db
        )
        
        for item in inventory:
            user_id, guild_id, item_id, purchase_time, expires_at, name, description, item_type, role_id, duration = item
            
            item_info = f"**Тип:** {self.get_item_type_name(item_type)}\n"
            item_info += f"**Куплен:** <t:{purchase_time}:R>\n"
            item_info += f"**ID:** {item_id}\n"
            
            if expires_at:
                item_info += f"**Истекает:** <t:{expires_at}:R>\n"
            else:
                item_info += "**Длительность:** Бессрочно\n"
            
            if role_id:
                role = ctx.guild.get_role(role_id)
                if role:
                    item_info += f"**Роль:** {role.mention}\n"
            
            item_info += f"**Описание:** {description}"
            
            embed.add_field(
                name=name,
                value=item_info,
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.command(name='additem')
    async def add_shop_item(self, ctx, name: str, price: int, item_type: str, max_purchases: int = -1, *, description: str):
        if not await self.check_permissions(ctx):
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У вас недостаточно прав для управления магазином!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        valid_types = ['role', 'cosmetic', 'boost', 'other']
        if item_type.lower() not in valid_types:
            await ctx.send(f"❌ Неверный тип предмета! Доступные: {', '.join(valid_types)}")
            return
        
        if price < 0:
            await ctx.send("❌ Цена не может быть отрицательной!")
            return
        
        if max_purchases < -1:
            await ctx.send("❌ Лимит покупок не может быть меньше -1!")
            return
        
        item_id = self.db.add_shop_item(ctx.guild.id, name, description, price, item_type.lower(), max_purchases=max_purchases)
        
        embed = discord.Embed(
            title="✅ Предмет добавлен в магазин!",
            description=f"**{name}** добавлен за {price} монет",
            color=0x00ff00
        )
        embed.add_field(name="ID предмета", value=item_id, inline=True)
        embed.add_field(name="Тип", value=item_type, inline=True)
        embed.add_field(name="Лимит покупок", value="Безлимитно" if max_purchases == -1 else max_purchases, inline=True)
        embed.add_field(name="Описание", value=description, inline=False)
        
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🛍️ Добавлен новый предмет в магазин",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Администратор", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Предмет", value=name, inline=True)
        log_embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        log_embed.add_field(name="Тип", value=item_type, inline=True)
        log_embed.add_field(name="ID", value=item_id, inline=True)
        await self.send_shop_log(ctx.guild, log_embed)

    @commands.command(name='addroleitem')
    async def add_role_item(self, ctx, name: str, price: int, role: discord.Role, duration: str = "0", max_purchases: int = -1, *, description: str):
        if not await self.check_permissions(ctx):
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У вас недостаточно прав для управления магазином!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        duration_seconds = 0
        if duration != "0":
            try:
                time_amount = int(duration[:-1])
                time_unit = duration[-1].lower()
                
                if time_unit == 'h':
                    duration_seconds = time_amount * 3600
                elif time_unit == 'd':
                    duration_seconds = time_amount * 86400
                elif time_unit == 'm':
                    duration_seconds = time_amount * 2592000
                else:
                    await ctx.send("❌ Неверный формат времени! Используйте: h (часы), d (дни), m (месяцы)")
                    return
            except ValueError:
                await ctx.send("❌ Неверный формат времени! Пример: `24h`, `7d`, `1m`")
                return
        
        if price < 0:
            await ctx.send("❌ Цена не может быть отрицательной!")
            return
        
        if max_purchases < -1:
            await ctx.send("❌ Лимит покупок не может быть меньше -1!")
            return
        
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("❌ Я не могу управлять этой ролью! Роль находится выше моей в иерархии.")
            return
        
        item_id = self.db.add_shop_item(
            ctx.guild.id, name, description, price, 'role', 
            role_id=role.id, duration=duration_seconds, max_purchases=max_purchases
        )
        
        embed = discord.Embed(
            title="✅ Роль добавлена в магазин!",
            description=f"**{name}** добавлена за {price} монет",
            color=0x00ff00
        )
        embed.add_field(name="ID предмета", value=item_id, inline=True)
        embed.add_field(name="Роль", value=role.mention, inline=True)
        embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        
        if duration_seconds > 0:
            days = duration_seconds // 86400
            embed.add_field(name="Длительность", value=f"{days} дней", inline=True)
        else:
            embed.add_field(name="Длительность", value="Бессрочно", inline=True)
        
        embed.add_field(name="Лимит покупок", value="Безлимитно" if max_purchases == -1 else max_purchases, inline=True)
        embed.add_field(name="Описание", value=description, inline=False)
        
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🛍️ Добавлена новая роль в магазин",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Администратор", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Роль", value=role.mention, inline=True)
        log_embed.add_field(name="Название", value=name, inline=True)
        log_embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        log_embed.add_field(name="ID", value=item_id, inline=True)
        await self.send_shop_log(ctx.guild, log_embed)

    @commands.command(name='deleteitem')
    async def delete_shop_item(self, ctx, item_id: int):
        if not await self.check_permissions(ctx):
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У вас недостаточно прав для управления магазином!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        item = self.db.get_shop_item(item_id)
        if not item:
            await ctx.send("❌ Предмет с таким ID не найден!")
            return
        
        self.db.delete_shop_item(item_id)
        
        embed = discord.Embed(
            title="✅ Предмет удален",
            description=f"Предмет **{item[2]}** (ID: {item_id}) удален из магазина",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🛍️ Предмет удален из магазина",
            color=0xff0000,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Администратор", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Предмет", value=item[2], inline=True)
        log_embed.add_field(name="ID", value=item_id, inline=True)
        await self.send_shop_log(ctx.guild, log_embed)

    @commands.command(name='clearinventory')
    async def clear_inventory(self, ctx, member: discord.Member):
        if not await self.check_permissions(ctx):
            embed = discord.Embed(
                title="❌ Ошибка",
                description="У вас недостаточно прав для этой команды!",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        inventory = self.db.get_user_inventory(member.id, ctx.guild.id)
        for item in inventory:
            if item[7] == 'role' and item[8]:
                role = ctx.guild.get_role(item[8])
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role)
                    except:
                        pass
        
        for item in inventory:
            self.db.remove_inventory_item(member.id, ctx.guild.id, item[2])
        
        embed = discord.Embed(
            title="✅ Инвентарь очищен",
            description=f"Инвентарь {member.mention} был полностью очищен",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🛍️ Инвентарь очищен",
            color=0xff0000,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Администратор", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Пользователь", value=member.mention, inline=True)
        await self.send_shop_log(ctx.guild, log_embed)

    @commands.command(name='iteminfo')
    async def item_info(self, ctx, item_id: int):
        item = self.db.get_shop_item(item_id)
        
        if not item:
            await ctx.send("❌ Предмет с таким ID не найден!")
            return
        
        item_id, guild_id, name, description, price, item_type, role_id, duration, max_purchases, created_at = item
        
        embed = discord.Embed(
            title=f"📋 Информация о предмете: {name}",
            color=0x3498db
        )
        
        embed.add_field(name="ID", value=item_id, inline=True)
        embed.add_field(name="Тип", value=self.get_item_type_name(item_type), inline=True)
        embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        
        if role_id:
            role = ctx.guild.get_role(role_id)
            if role:
                embed.add_field(name="Роль", value=role.mention, inline=True)
        
        if duration > 0:
            days = duration // 86400
            embed.add_field(name="Длительность", value=f"{days} дней", inline=True)
        else:
            embed.add_field(name="Длительность", value="Бессрочно", inline=True)
        
        embed.add_field(name="Лимит покупок", value="Безлимитно" if max_purchases == -1 else max_purchases, inline=True)
        embed.add_field(name="Создан", value=f"<t:{created_at}:R>", inline=True)
        embed.add_field(name="Описание", value=description, inline=False)
        
        await ctx.send(embed=embed)

    @commands.group(name='market', invoke_without_command=True)
    async def market(self, ctx, page: int = 1):
        listings = self.db.get_market_listings(ctx.guild.id)
        
        if not listings:
            embed = discord.Embed(
                title="🏪 Торговая площадка",
                description="На площадке пока нет предложений!\nИспользуйте `!market sell <ID_предмета> <цена>` чтобы выставить предмет",
                color=0x3498db
            )
            await ctx.send(embed=embed)
            return
        
        listings_per_page = 5
        total_pages = (len(listings) + listings_per_page - 1) // listings_per_page
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * listings_per_page
        end_idx = start_idx + listings_per_page
        page_listings = listings[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"🏪 Торговая площадка (Страница {page}/{total_pages})",
            description=f"Используйте `{ctx.prefix}market buy <ID>` для покупки\n`{ctx.prefix}market <страница>` для навигации",
            color=0x3498db
        )
        
        for listing in page_listings:
            listing_id, seller_id, guild_id, item_id, price, created_at, status, name, description, item_type, seller_balance = listing
            
            seller = ctx.guild.get_member(seller_id)
            seller_name = seller.display_name if seller else "Неизвестный"
            
            listing_info = f"**Цена:** {price} монет\n"
            listing_info += f"**Продавец:** {seller_name}\n"
            listing_info += f"**Тип:** {self.get_item_type_name(item_type)}\n"
            listing_info += f"**Выставлен:** <t:{created_at}:R>\n"
            listing_info += f"**Описание:** {description}"
            
            embed.add_field(
                name=f"#{listing_id} {name}",
                value=listing_info,
                inline=False
            )
        
        await ctx.send(embed=embed)

    @market.command(name='sell')
    async def market_sell(self, ctx, item_id: int, price: int):
        inventory = self.db.get_user_inventory(ctx.author.id, ctx.guild.id)
        
        item_in_inventory = any(item[2] == item_id for item in inventory)
        if not item_in_inventory:
            await ctx.send("❌ У вас нет этого предмета в инвентаре!")
            return
        
        if price <= 0:
            await ctx.send("❌ Цена должна быть положительной!")
            return
        
        item_info = self.db.get_shop_item(item_id)
        if not item_info:
            await ctx.send("❌ Предмет не найден в магазине!")
            return
        
        listing_id = self.db.add_market_listing(ctx.author.id, ctx.guild.id, item_id, price)
        
        embed = discord.Embed(
            title="✅ Предмет выставлен на продажу!",
            description=f"**{item_info[2]}** выставлен за {price} монет",
            color=0x00ff00
        )
        embed.add_field(name="ID предложения", value=listing_id, inline=True)
        embed.add_field(name="ID предмета", value=item_id, inline=True)
        embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🏪 Предмет выставлен на площадку",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Продавец", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Предмет", value=item_info[2], inline=True)
        log_embed.add_field(name="Цена", value=f"{price} монет", inline=True)
        log_embed.add_field(name="ID предложения", value=listing_id, inline=True)
        await self.send_shop_log(ctx.guild, log_embed)

    @market.command(name='buy')
    async def market_buy(self, ctx, listing_id: int):
        success, message = self.db.purchase_market_item(ctx.author.id, ctx.guild.id, listing_id)
        
        if success:
            listing = self.db.get_market_listing(listing_id)
            item_info = self.db.get_shop_item(listing[3])
            
            embed = discord.Embed(
                title="✅ Покупка успешна!",
                description=f"Вы купили **{item_info[2]}** за {listing[4]} монет",
                color=0x00ff00
            )
            
            seller = ctx.guild.get_member(listing[1])
            if seller:
                embed.add_field(name="Продавец", value=seller.mention, inline=True)
            
            await ctx.send(embed=embed)
            
            log_embed = discord.Embed(
                title="🏪 Покупка на торговой площадке",
                color=0x00ff00,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Покупатель", value=ctx.author.mention, inline=True)
            log_embed.add_field(name="Продавец", value=seller.mention if seller else "Неизвестный", inline=True)
            log_embed.add_field(name="Предмет", value=item_info[2], inline=True)
            log_embed.add_field(name="Цена", value=f"{listing[4]} монет", inline=True)
            await self.send_shop_log(ctx.guild, log_embed)
            
        else:
            embed = discord.Embed(
                title="❌ Ошибка покупки",
                description=message,
                color=0xff0000
            )
            await ctx.send(embed=embed)

    @market.command(name='my')
    async def market_my(self, ctx):
        listings = self.db.get_user_market_listings(ctx.author.id, ctx.guild.id)
        
        if not listings:
            embed = discord.Embed(
                title="🏪 Мои предложения",
                description="У вас нет активных предложений на торговой площадке",
                color=0x3498db
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🏪 Мои предложения на площадке",
            color=0x3498db
        )
        
        for listing in listings:
            listing_id, seller_id, guild_id, item_id, price, created_at, status, name, description, item_type = listing
            
            listing_info = f"**Цена:** {price} монет\n"
            listing_info += f"**Тип:** {self.get_item_type_name(item_type)}\n"
            listing_info += f"**Выставлен:** <t:{created_at}:R>\n"
            listing_info += f"**Статус:** {status}\n"
            listing_info += f"**Описание:** {description}"
            
            embed.add_field(
                name=f"#{listing_id} {name}",
                value=listing_info,
                inline=False
            )
        
        await ctx.send(embed=embed)

    @market.command(name='remove')
    async def market_remove(self, ctx, listing_id: int):
        listing = self.db.get_market_listing(listing_id)
        
        if not listing:
            await ctx.send("❌ Предложение не найдено!")
            return
        
        if listing[1] != ctx.author.id and not await self.check_permissions(ctx):
            await ctx.send("❌ Вы можете убирать только свои предложения!")
            return
        
        self.db.remove_market_listing(listing_id)
        
        embed = discord.Embed(
            title="✅ Предложение убрано с площадки",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        
        log_embed = discord.Embed(
            title="🏪 Предложение убрано с площадки",
            color=0xff0000,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="Пользователь", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="ID предложения", value=listing_id, inline=True)
        await self.send_shop_log(ctx.guild, log_embed)

    @commands.command(name='transactions', aliases=['trans'])
    async def transactions(self, ctx, limit: int = 10):
        transactions = self.db.get_user_transactions(ctx.author.id, ctx.guild.id, limit)
        
        if not transactions:
            embed = discord.Embed(
                title="📊 История транзакций",
                description="У вас пока нет транзакций",
                color=0x3498db
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"📊 История транзакций ({len(transactions)} последних)",
            color=0x3498db
        )
        
        for trans in transactions:
            trans_id, from_user_id, to_user_id, guild_id, item_id, amount, trans_type, created_at = trans
            
            item_info = self.db.get_shop_item(item_id)
            item_name = item_info[2] if item_info else "Неизвестный предмет"
            
            trans_info = f"**Тип:** {self.get_transaction_type_name(trans_type)}\n"
            trans_info += f"**Сумма:** {amount} монет\n"
            trans_info += f"**Время:** <t:{created_at}:R>\n"
            
            if trans_type == 'market_sale':
                if from_user_id == ctx.author.id:
                    trans_info += f"**Детали:** Вы продали {item_name}"
                else:
                    trans_info += f"**Детали:** Вы купили {item_name}"
            else:
                trans_info += f"**Предмет:** {item_name}"
            
            embed.add_field(
                name=f"Транзакция #{trans_id}",
                value=trans_info,
                inline=False
            )
        
        await ctx.send(embed=embed)

    def get_item_type_name(self, item_type):
        type_names = {
            'role': '🎭 Роль',
            'cosmetic': '🎨 Косметика', 
            'boost': '⚡ Буст',
            'other': '📦 Другое'
        }
        return type_names.get(item_type, '📦 Другое')

    def get_transaction_type_name(self, trans_type):
        type_names = {
            'market_sale': '🏪 Торговая площадка',
            'shop_purchase': '🛍️ Покупка в магазине',
            'transfer': '🔄 Перевод'
        }
        return type_names.get(trans_type, '📊 Другое')

async def setup(bot):
    await bot.add_cog(Shop(bot))