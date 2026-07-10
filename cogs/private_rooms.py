import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput, Select
import asyncio
from datetime import datetime, timedelta
from utils.database import Database
from utils.checks import has_permission
import json

class PrivateRoomModal(Modal):
    """Модальное окно для настроек приватной комнаты"""
    def __init__(self, room_type, callback, current_name="", current_limit=0):
        super().__init__(title=f"Настройка {room_type} комнаты")
        self.room_type = room_type
        self.callback_func = callback
        
        self.room_name = TextInput(
            label="Название комнаты",
            placeholder="Введите название комнаты...",
            default=current_name,
            max_length=100
        )
        
        if room_type == "голосовой":
            self.user_limit = TextInput(
                label="Макс. участников (0 = без ограничений)",
                placeholder="Введите число от 0 до 99",
                default=str(current_limit),
                max_length=2
            )
        
        self.add_item(self.room_name)
        if room_type == "голосовой":
            self.add_item(self.user_limit)
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.callback_func(interaction, self.room_name.value, 
                               int(self.user_limit.value) if hasattr(self, 'user_limit') else 0)

class PrivateRoomView(View):
    """View для панели управления приватными комнатами"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = Database()
    
    @discord.ui.button(label="Создать голосовую", style=discord.ButtonStyle.green, emoji="🎤", custom_id="create_voice")
    async def create_voice_button(self, interaction: discord.Interaction, button: Button):
        await self.create_room(interaction, "voice")
    
    @discord.ui.button(label="Создать текстовую", style=discord.ButtonStyle.blurple, emoji="💬", custom_id="create_text")
    async def create_text_button(self, interaction: discord.Interaction, button: Button):
        await self.create_room(interaction, "text")
    
    @discord.ui.button(label="Настроить комнату", style=discord.ButtonStyle.gray, emoji="⚙️", custom_id="configure")
    async def configure_button(self, interaction: discord.Interaction, button: Button):
        await self.configure_room(interaction)
    
    @discord.ui.button(label="Выдать совладельца", style=discord.ButtonStyle.gray, emoji="👑", custom_id="add_coowner")
    async def add_coowner_button(self, interaction: discord.Interaction, button: Button):
        await self.add_coowner(interaction)
    
    @discord.ui.button(label="Передать владение", style=discord.ButtonStyle.gray, emoji="🔄", custom_id="transfer")
    async def transfer_button(self, interaction: discord.Interaction, button: Button):
        await self.transfer_ownership(interaction)
    
    @discord.ui.button(label="Добавить участника", style=discord.ButtonStyle.gray, emoji="➕", custom_id="add_member")
    async def add_member_button(self, interaction: discord.Interaction, button: Button):
        await self.add_member(interaction)
    
    @discord.ui.button(label="Удалить участника", style=discord.ButtonStyle.gray, emoji="➖", custom_id="remove_member")
    async def remove_member_button(self, interaction: discord.Interaction, button: Button):
        await self.remove_member(interaction)
    
    @discord.ui.button(label="Удалить комнату", style=discord.ButtonStyle.red, emoji="🗑️", custom_id="delete")
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        await self.delete_room(interaction)
    
    async def create_room(self, interaction: discord.Interaction, room_type: str):
        """Создание приватной комнаты"""
        guild = interaction.guild
        user = interaction.user
        
        # Проверяем, есть ли уже у пользователя комната
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM private_rooms WHERE owner_id = ? AND guild_id = ?', 
                      (user.id, guild.id))
        existing_room = cursor.fetchone()
        
        if existing_room:
            await interaction.response.send_message(
                "❌ У вас уже есть приватная комната! Сначала удалите существующую.",
                ephemeral=True
            )
            return
        
         # Определяем категорию для комнат
        try:
            category = await self.get_or_create_category(guild, room_type, interaction.channel)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
            return
        
        # Создаем комнату
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                connect=True if room_type == "voice" else None,
                send_messages=True if room_type == "text" else None,
                manage_channels=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                manage_channels=True,
                manage_roles=True
            )
        }
        
                # Получаем шаблон названия из настроек
        settings = self.db.get_server_settings(guild.id)
        default_name = settings[15] if settings[15] else "Комната {username}"
        room_name = default_name.format(username=user.name, user=user.name, member=user.name)
        
        if room_type == "voice":
            room = await guild.create_voice_channel(
                name=room_name,
                category=category,
                overwrites=overwrites
            )
            room_type_name = "голосовой"
        else:
            room = await guild.create_text_channel(
                name=room_name,
                category=category,
                overwrites=overwrites
            )
            room_type_name = "текстовой"
        
        # Сохраняем в базу данных
        cursor.execute('''
            INSERT INTO private_rooms 
            (guild_id, owner_id, channel_id, channel_type, name, user_limit, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (guild.id, user.id, room.id, room_type, room.name, 0, int(datetime.now().timestamp())))
        
        self.db.conn.commit()
        
        # Создаем embed с информацией
        embed = discord.Embed(
            title=f"✅ {room_type_name.capitalize()} комната создана!",
            description=f"Канал: {room.mention}",
            color=0x00ff00
        )
        embed.add_field(name="Владелец", value=user.mention, inline=True)
        embed.add_field(name="Тип", value=room_type_name, inline=True)
        embed.add_field(name="Управление", value="Используйте кнопки ниже или команды", inline=False)
        
        view = RoomManagementView(self.bot, room.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def configure_room(self, interaction: discord.Interaction):
        """Настройка существующей комнаты"""
        guild = interaction.guild
        user = interaction.user
        
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT * FROM private_rooms 
            WHERE (owner_id = ? OR co_owner_id = ?) AND guild_id = ?
        ''', (user.id, user.id, guild.id))
        
        room_data = cursor.fetchone()
        
        if not room_data:
            await interaction.response.send_message(
                "❌ У вас нет приватной комнаты для настройки!",
                ephemeral=True
            )
            return
        
        # Проверяем права (владелец или совладелец)
        if room_data[2] != user.id and room_data[3] != user.id:
            await interaction.response.send_message(
                "❌ Вы не имеете прав для настройки этой комнаты!",
                ephemeral=True
            )
            return
        
        room_type = "голосовой" if room_data[4] == "voice" else "текстовой"
        current_limit = room_data[6] if room_type == "голосовой" else 0
        
        modal = PrivateRoomModal(
            room_type=room_type,
            callback=self.save_room_configuration,
            current_name=room_data[5],
            current_limit=current_limit
        )
        
        await interaction.response.send_modal(modal)
    
    async def save_room_configuration(self, interaction: discord.Interaction, name: str, user_limit: int):
        """Сохранение настроек комнаты"""
        guild = interaction.guild
        user = interaction.user
        
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT * FROM private_rooms 
            WHERE (owner_id = ? OR co_owner_id = ?) AND guild_id = ?
        ''', (user.id, user.id, guild.id))
        
        room_data = cursor.fetchone()
        
        if not room_data:
            await interaction.response.send_message(
                "❌ Комната не найдена!",
                ephemeral=True
            )
            return
        
        channel_id = room_data[4]
        channel_type = room_data[5]
        current_name = room_data[6]
        current_limit = room_data[7]
        
        # Обновляем канал
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.edit(name=name)
                
                if channel_type == "voice" and isinstance(channel, discord.VoiceChannel):
                    await channel.edit(user_limit=user_limit if user_limit > 0 else None)
                
                # Обновляем в базе данных
                cursor.execute('''
                    UPDATE private_rooms 
                    SET name = ?, user_limit = ?
                    WHERE channel_id = ?
                ''', (name, user_limit, channel_id))
                
                self.db.conn.commit()
                
                await interaction.response.send_message(
                    f"✅ Настройки комнаты обновлены!\nНазвание: {name}" + 
                    (f"\nЛимит участников: {user_limit}" if user_limit > 0 else ""),
                    ephemeral=True
                )
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Ошибка при обновлении комнаты: {e}",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Канал не найден!",
                ephemeral=True
            )
    
    async def add_coowner(self, interaction: discord.Interaction):
        """Добавление совладельца комнаты"""
        await self.manage_member(interaction, "coowner", "добавить")
    
    async def transfer_ownership(self, interaction: discord.Interaction):
        """Передача владения комнатой"""
        await self.manage_member(interaction, "owner", "передать")
    
    async def add_member(self, interaction: discord.Interaction):
        """Добавление участника в комнату"""
        await self.manage_member(interaction, "member", "добавить")
    
    async def remove_member(self, interaction: discord.Interaction):
        """Удаление участника из комнаты"""
        await self.manage_member(interaction, "member", "удалить")
    
    async def manage_member(self, interaction: discord.Interaction, role_type: str, action: str):
        """Общий метод для управления участниками"""
        guild = interaction.guild
        user = interaction.user
        
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM private_rooms WHERE owner_id = ? AND guild_id = ?', 
                      (user.id, guild.id))
        
        room_data = cursor.fetchone()
        
        if not room_data:
            await interaction.response.send_message(
                "❌ У вас нет приватной комнаты!",
                ephemeral=True
            )
            return
        
        channel_id = room_data[4]
        channel = guild.get_channel(channel_id)
        
        if not channel:
            await interaction.response.send_message(
                "❌ Канал не найден!",
                ephemeral=True
            )
            return
        
        # Создаем модальное окно для выбора пользователя
        class MemberSelectModal(Modal):
            def __init__(self, callback):
                super().__init__(title=f"{action.capitalize()} участника")
                self.callback_func = callback
                
                self.user_id_input = TextInput(
                    label="ID пользователя или упоминание",
                    placeholder="@пользователь или ID",
                    max_length=100
                )
                self.add_item(self.user_id_input)
            
            async def on_submit(self, interaction: discord.Interaction):
                await self.callback_func(interaction, self.user_id_input.value)
        
        async def process_member(interaction: discord.Interaction, user_input: str):
            try:
                # Парсим ввод пользователя
                if user_input.startswith('<@') and user_input.endswith('>'):
                    member_id = int(user_input.strip('<@!>'))
                else:
                    member_id = int(user_input)
                
                member = guild.get_member(member_id)
                if not member:
                    member = await guild.fetch_member(member_id)
                
                if not member:
                    await interaction.response.send_message(
                        "❌ Пользователь не найден на сервере!",
                        ephemeral=True
                    )
                    return
                
                if member == user:
                    await interaction.response.send_message(
                        "❌ Нельзя выполнить это действие с самим собой!",
                        ephemeral=True
                    )
                    return
                
                # Обновляем права доступа
                overwrites = channel.overwrites
                
                if role_type == "coowner":
                    if action == "добавить":
                        overwrites[member] = discord.PermissionOverwrite(
                            view_channel=True,
                            connect=True if isinstance(channel, discord.VoiceChannel) else None,
                            send_messages=True if isinstance(channel, discord.TextChannel) else None,
                            manage_channels=True
                        )
                        # Обновляем в базе данных
                        cursor.execute('UPDATE private_rooms SET co_owner_id = ? WHERE channel_id = ?', 
                                     (member.id, channel_id))
                        self.db.conn.commit()
                        
                        await interaction.response.send_message(
                            f"✅ {member.mention} теперь совладелец комнаты!",
                            ephemeral=True
                        )
                    else:  # передача владения
                        # Старый владелец становится совладельцем
                        overwrites[user] = discord.PermissionOverwrite(
                            view_channel=True,
                            connect=True if isinstance(channel, discord.VoiceChannel) else None,
                            send_messages=True if isinstance(channel, discord.TextChannel) else None,
                            manage_channels=False
                        )
                        
                        # Новый владелец получает полные права
                        overwrites[member] = discord.PermissionOverwrite(
                            view_channel=True,
                            connect=True if isinstance(channel, discord.VoiceChannel) else None,
                            send_messages=True if isinstance(channel, discord.TextChannel) else None,
                            manage_channels=True
                        )
                        
                        # Обновляем в базе данных
                        cursor.execute('''
                            UPDATE private_rooms 
                            SET owner_id = ?, co_owner_id = ?
                            WHERE channel_id = ?
                        ''', (member.id, user.id, channel_id))
                        self.db.conn.commit()
                        
                        await interaction.response.send_message(
                            f"✅ Владение комнатой передано {member.mention}!",
                            ephemeral=True
                        )
                
                elif role_type == "member":
                    if action == "добавить":
                        overwrites[member] = discord.PermissionOverwrite(
                            view_channel=True,
                            connect=True if isinstance(channel, discord.VoiceChannel) else None,
                            send_messages=True if isinstance(channel, discord.TextChannel) else None
                        )
                        
                        await interaction.response.send_message(
                            f"✅ {member.mention} добавлен в комнату!",
                            ephemeral=True
                        )
                    else:  # удалить
                        if member in overwrites:
                            del overwrites[member]
                            
                            await interaction.response.send_message(
                                f"✅ {member.mention} удален из комнаты!",
                                ephemeral=True
                        )
                        else:
                            await interaction.response.send_message(
                                f"❌ {member.mention} не найден в списке участников комнаты!",
                                ephemeral=True
                            )
                            return
                
                # Применяем изменения прав
                await channel.edit(overwrites=overwrites)
                
            except ValueError:
                await interaction.response.send_message(
                    "❌ Неверный формат ID пользователя!",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Ошибка: {e}",
                    ephemeral=True
                )
        
        modal = MemberSelectModal(process_member)
        await interaction.response.send_modal(modal)
    
    async def delete_room(self, interaction: discord.Interaction):
        """Удаление приватной комнаты"""
        guild = interaction.guild
        user = interaction.user
        
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM private_rooms WHERE owner_id = ? AND guild_id = ?', 
                      (user.id, guild.id))
        
        room_data = cursor.fetchone()
        
        if not room_data:
            await interaction.response.send_message(
                "❌ У вас нет приватной комнаты для удаления!",
                ephemeral=True
            )
            return
        
        channel_id = room_data[4]
        room_id = room_data[0]
        
        class ConfirmView(View):
            def __init__(self, db, guild_id, channel_id):
                super().__init__(timeout=30)
                self.db = db
                self.guild_id = guild_id
                self.channel_id = channel_id
                self.confirmed = False
            
            @discord.ui.button(label="Да, удалить", style=discord.ButtonStyle.red, emoji="🗑️")
            async def confirm(self, interaction: discord.Interaction, button: Button):
                self.confirmed = True
                self.stop()
                
                # Удаляем канал
                channel = interaction.guild.get_channel(self.channel_id)
                if channel:
                    await channel.delete()
                
                # Удаляем из базы данных
                cursor = self.db.conn.cursor()
                cursor.execute('DELETE FROM private_rooms WHERE channel_id = ?', (self.channel_id,))
                self.db.conn.commit()
                
                await interaction.response.send_message(
                    "✅ Комната успешно удалена!",
                    ephemeral=True
                )
            
            @discord.ui.button(label="Отмена", style=discord.ButtonStyle.gray)
            async def cancel(self, interaction: discord.Interaction, button: Button):
                self.stop()
                await interaction.response.send_message(
                    "❌ Удаление комнаты отменено.",
                    ephemeral=True
                )
        
        confirm_view = ConfirmView(self.db, guild.id, channel_id)
        
        embed = discord.Embed(
            title="⚠️ Подтверждение удаления",
            description="Вы уверены, что хотите удалить свою приватную комнату? Это действие нельзя отменить!",
            color=0xff9900
        )
        
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
    
    async def get_or_create_category(self, guild, room_type, interaction_channel=None):
        """Получение или создание категории для приватных комнат"""
        try:
            settings = self.db.get_server_settings(guild.id)
            
            # Безопасное получение настроек (защита от IndexError)
            allow_voice = True
            allow_text = True
            voice_category_id = None
            text_category_id = None
            
            try:
                # Проверяем длину кортежа
                if len(settings) > 16:
                    if room_type == "voice":
                        allow_voice = settings[16] != 0
                    else:
                        allow_text = settings[17] != 0
                    voice_category_id = settings[11] if len(settings) > 11 else None
                    text_category_id = settings[12] if len(settings) > 12 else None
                else:
                    print(f"⚠️ Внимание: старая структура БД, используем настройки по умолчанию")
            except IndexError as e:
                print(f"⚠️ Ошибка при чтении настроек: {e}, используем значения по умолчанию")
            
            # Проверяем настройки
            if room_type == "voice":
                if not allow_voice:
                    raise ValueError("Создание голосовых комнат отключено администратором")
                category_id = voice_category_id
                default_name = "🔒 Голосовые комнаты"
            else:  # text
                if not allow_text:
                    raise ValueError("Создание текстовых комнат отключено администратором")
                category_id = text_category_id
                default_name = "💬 Текстовые комнаты"
            
            # Если категория задана в настройках
            if category_id:
                category = guild.get_channel(category_id)
                if category and isinstance(category, discord.CategoryChannel):
                    return category
            
            # Если передан канал взаимодействия, используем его категорию
            if interaction_channel and interaction_channel.category:
                return interaction_channel.category
            
            # Ищем существующую категорию с именем по умолчанию
            for category in guild.categories:
                if category.name == default_name:
                    return category
            
            # Создаем новую категорию
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    manage_channels=True,
                    manage_roles=True
                )
            }
            
            return await guild.create_category(name=default_name, overwrites=overwrites)
            
        except Exception as e:
            print(f"❌ Ошибка в get_or_create_category: {e}")
            # Возвращаемся к оригинальной логике как запасной вариант
            category_name = "🔒 Приватные комнаты"
            
            for category in guild.categories:
                if category.name == category_name:
                    return category
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    manage_channels=True,
                    manage_roles=True
                )
            }
            
            return await guild.create_category(name=category_name, overwrites=overwrites)

class RoomManagementView(View):
    """View для управления конкретной комнатой"""
    def __init__(self, bot, channel_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.channel_id = channel_id
        self.db = Database()

class PrivateRooms(commands.Cog):
    """Ког для управления приватными комнатами"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.create_tables()
        self.cleanup_task.start()
    
    def create_tables(self):
        """Создание таблиц для приватных комнат"""
        cursor = self.db.conn.cursor()
        
        # Таблица приватных комнат
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS private_rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                owner_id INTEGER,
                co_owner_id INTEGER DEFAULT NULL,
                channel_id INTEGER UNIQUE,
                channel_type TEXT,
                name TEXT,
                user_limit INTEGER DEFAULT 0,
                created_at INTEGER
            )
        ''')
        
        # Таблица участников приватных комнат (для расширенного управления)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS private_room_members (
                room_id INTEGER,
                user_id INTEGER,
                added_at INTEGER,
                FOREIGN KEY (room_id) REFERENCES private_rooms(id) ON DELETE CASCADE,
                PRIMARY KEY (room_id, user_id)
            )
        ''')
        
        self.db.conn.commit()
    
    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        """Задача для очистки пустых приватных комнат"""
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM private_rooms')
        rooms = cursor.fetchall()
        
        for room in rooms:
            guild_id, channel_id, channel_type = room[1], room[4], room[5]
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            
            channel = guild.get_channel(channel_id)
            if not channel:
                # Канал удален вручную - удаляем из базы
                cursor.execute('DELETE FROM private_rooms WHERE channel_id = ?', (channel_id,))
                continue
            
            # Для голосовых каналов: удаляем если пустые более 5 минут
            if channel_type == "voice" and isinstance(channel, discord.VoiceChannel):
                if len(channel.members) == 0:
                    # Проверяем, когда был создан канал
                    created_at = room[8]
                    current_time = int(datetime.now().timestamp())
                    
                    if current_time - created_at > 300:  # 5 минут
                        try:
                            await channel.delete()
                            cursor.execute('DELETE FROM private_rooms WHERE channel_id = ?', (channel_id,))
                        except:
                            pass
        
        self.db.conn.commit()
    
    @commands.hybrid_command(name='privateroom', aliases=['proom'], description='Настроить систему приватных комнат')
    @has_permission('admin', 'high_admin', 'owner')
    async def setup_private_room(self, ctx):
        """Настройка системы приватных комнат"""
        embed = discord.Embed(
            title="🔒 Управление приватными комнатами",
            description=(
                "**Добро пожаловать в систему приватных комнат!**\n\n"
                "📌 **Что это такое?**\n"
                "Система позволяет пользователям создавать свои собственные голосовые и текстовые комнаты с полным контролем.\n\n"
                "🎮 **Как использовать?**\n"
                "1. **Создать комнату** - нажмите кнопку ниже для создания голосовой или текстовой комнаты\n"
                "2. **Настроить комнату** - измените название, установите лимит участников\n"
                "3. **Управлять участниками** - добавляйте/удаляйте друзей\n"
                "4. **Назначить совладельца** - дайте права управления другому пользователю\n"
                "5. **Передать владение** - передайте комнату другому пользователю\n"
                "6. **Удалить комнату** - когда она больше не нужна\n\n"
                "⚙️ **Автоматическая очистка:**\n"
                "• Пустые голосовые комнаты удаляются через 5 минут\n"
                "• Текстовые комнаты удаляются только вручную\n\n"
                "👑 **Права владельца:**\n"
                "• Изменение названия и настроек\n"
                "• Управление участниками\n"
                "• Назначение совладельца\n"
                "• Удаление комнаты"
            ),
            color=0x7289da
        )
        
        embed.set_footer(text="Для подробной информации используйте /help privateroom")
        
        view = PrivateRoomView(self.bot)
        await ctx.send(embed=embed, view=view)
    
    @commands.hybrid_command(name='roominfo', description='Информация о вашей приватной комнате')
    async def room_info(self, ctx):
        """Показать информацию о приватной комнате пользователя"""
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT * FROM private_rooms 
            WHERE (owner_id = ? OR co_owner_id = ?) AND guild_id = ?
        ''', (ctx.author.id, ctx.author.id, ctx.guild.id))
        
        room_data = cursor.fetchone()
        
        if not room_data:
            await ctx.send("❌ У вас нет приватной комнаты!", ephemeral=True)
            return
        
        # Получаем информацию о комнате
        room_id, guild_id, owner_id, co_owner_id, channel_id, channel_type, name, user_limit, created_at = room_data
        
        channel = ctx.guild.get_channel(channel_id)
        owner = ctx.guild.get_member(owner_id)
        co_owner = ctx.guild.get_member(co_owner_id) if co_owner_id else None
        
        # Получаем список участников
        cursor.execute('SELECT user_id FROM private_room_members WHERE room_id = ?', (room_id,))
        member_ids = [row[0] for row in cursor.fetchall()]
        
        embed = discord.Embed(
            title=f"🔍 Информация о приватной комнате",
            color=0x7289da
        )
        
        embed.add_field(name="Канал", value=channel.mention if channel else "❌ Не найден", inline=True)
        embed.add_field(name="Тип", value="🎤 Голосовая" if channel_type == "voice" else "💬 Текстовая", inline=True)
        embed.add_field(name="Название", value=name, inline=True)
        
        embed.add_field(name="Владелец", value=owner.mention if owner else "❌ Не найден", inline=True)
        embed.add_field(name="Совладелец", value=co_owner.mention if co_owner else "❌ Нет", inline=True)
        
        if channel_type == "voice" and isinstance(channel, discord.VoiceChannel):
            embed.add_field(name="Участников", value=f"{len(channel.members)}/{user_limit if user_limit > 0 else '∞'}", inline=True)
        
        if member_ids:
            members_text = ""
            for member_id in member_ids[:10]:  # Показываем только первых 10
                member = ctx.guild.get_member(member_id)
                if member:
                    members_text += f"{member.mention}\n"
            
            if len(member_ids) > 10:
                members_text += f"... и еще {len(member_ids) - 10}"
            
            embed.add_field(name="Добавленные участники", value=members_text or "❌ Нет", inline=False)
        
        created_time = datetime.fromtimestamp(created_at)
        embed.add_field(name="Создана", value=f"<t:{created_at}:R>", inline=True)
        
        # Показываем кнопки управления
        view = RoomManagementView(self.bot, channel_id)
        await ctx.send(embed=embed, view=view, ephemeral=True)
    
    @commands.hybrid_command(name='forceroomdelete', description='Принудительно удалить приватную комнату (админ)')
    @has_permission('admin', 'high_admin', 'owner')
    @app_commands.describe(channel_id='ID канала для удаления')
    async def force_room_delete(self, ctx, channel_id: str):
        """Принудительное удаление приватной комнаты администратором"""
        try:
            channel_id_int = int(channel_id)
        except ValueError:
            await ctx.send("❌ Неверный формат ID канала!", ephemeral=True)
            return
        
        channel = ctx.guild.get_channel(channel_id_int)
        if not channel:
            await ctx.send("❌ Канал не найден!", ephemeral=True)
            return
        
        cursor = self.db.conn.cursor()
        cursor.execute('SELECT * FROM private_rooms WHERE channel_id = ?', (channel_id_int,))
        
        room_data = cursor.fetchone()
        
        if not room_data:
            await ctx.send("❌ Это не приватная комната или она не зарегистрирована в системе!", ephemeral=True)
            return
        
        # Удаляем канал
        try:
            await channel.delete()
            
            # Удаляем из базы данных
            cursor.execute('DELETE FROM private_rooms WHERE channel_id = ?', (channel_id_int,))
            cursor.execute('DELETE FROM private_room_members WHERE room_id = ?', (room_data[0],))
            self.db.conn.commit()
            
            await ctx.send(f"✅ Приватная комната {channel_id} успешно удалена администратором!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Ошибка при удалении комнаты: {e}", ephemeral=True)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Отслеживание активности в приватных голосовых комнатах"""
        if member.bot:
            return
        
        # Если пользователь покинул голосовой канал
        if before.channel and not after.channel:
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT * FROM private_rooms WHERE channel_id = ?', (before.channel.id,))
            
            room_data = cursor.fetchone()
            
            if room_data:
                # Это приватная комната, проверяем нужно ли ее удалить
                if len(before.channel.members) == 0:
                    # Проверяем время создания
                    created_at = room_data[8]
                    current_time = int(datetime.now().timestamp())
                
                    settings = self.db.get_server_settings(member.guild.id)
                    auto_delete_minutes = settings[14]  # room_auto_delete_minutes
                    
                    if auto_delete_minutes > 0:
                        try:
                            await asyncio.sleep(auto_delete_minutes * 60)
                            # Проверяем еще раз
                            if len(before.channel.members) == 0:
                                await before.channel.delete()
                                cursor.execute('DELETE FROM private_rooms WHERE channel_id = ?', (before.channel.id,))
                                self.db.conn.commit()
                        except:
                            pass
    
    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        """Ожидание готовности бота перед запуском задачи"""
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(PrivateRooms(bot))