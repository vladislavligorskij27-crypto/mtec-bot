import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

class AntiSpamMiddleware(BaseMiddleware):
    def __init__(
        self, 
        limit: float = 0.8,         
        base_penalty: float = 2.0,  
        max_penalty: float = 30.0,  
        penalty_step: float = 2.0,  
        reset_timeout: float = 30.0 
    ):
        self.limit = limit
        self.base_penalty = base_penalty
        self.max_penalty = max_penalty
        self.penalty_step = penalty_step
        self.reset_timeout = reset_timeout
        
        self.users: Dict[int, Dict[str, Any]] = {}
        self.max_cache_size = 1000 
        
        self.restricted_actions = [
            "📅 На сегодня",
            "⏭️ На завтра",
            "➡️ На понедельник",
            
            ": Сегодня",
            ": Завтра",
            ": Пн",
            
            "🔍 Свободные кабинеты",
            "🔍 Где препод?",
            "📖 Электронный журнал",
            "📂 Архив расписания",
            "🔔 Звонки",
            "📝 Обратная связь",
            "ℹ️ Инфо",
            "⚙️ Настройки",
            "👨‍🏫 Меню куратора",
            
            "📢 Сообщение группе",
            "⬅️ Назад в меню",
            "⬅️ Назад",
            
            "/"
        ]

        self.safe_callbacks = [
            "role_", "pref_", "let_", "set_std_", "set_tch_", "curpref_", 
            "set_cur_", "is_curator_", "back_to", "srch_", "toggle_notif", 
            "reset_setup", "journal_", "bc_"
        ]

    def _cleanup_cache(self, now: float):
        self.users = {
            uid: data 
            for uid, data in self.users.items() 
            if now < data.get("penalty_until", 0) + self.reset_timeout or (now - data.get("last_time", 0) < self.limit)
        }

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        user_id = None
        action_text = None

        if isinstance(event, Message):
            user_id = event.from_user.id
            action_text = event.text or event.caption
        elif isinstance(event, CallbackQuery) and event.data:
            user_id = event.from_user.id
            action_text = event.data
            
        if user_id and action_text:
            
            is_heavy_request = False
            
            if isinstance(event, CallbackQuery):
                if not any(action_text.startswith(safe) for safe in self.safe_callbacks):
                    is_heavy_request = True 
            elif isinstance(event, Message):
                if any(trigger in action_text for trigger in self.restricted_actions):
                    is_heavy_request = True
            
            if is_heavy_request:
                now = time.time()
                
                if len(self.users) > self.max_cache_size:
                    self._cleanup_cache(now)

                user_data = self.users.get(user_id, {
                    "last_time": 0, 
                    "penalty_until": 0, 
                    "current_penalty": 0,
                    "warned_during_penalty": False 
                })

                if now < user_data["penalty_until"]:
                    time_left = int(user_data["penalty_until"] - now) + 1
                    
                    if isinstance(event, CallbackQuery):
                        await event.answer(f"⚠️ Спам-блок! Подождите еще {time_left} сек.", show_alert=False)
                    elif isinstance(event, Message):
                        if not user_data.get("warned_during_penalty"):
                            await event.answer(f"⏳ Вы всё ещё заблокированы за спам. Осталось: {time_left} сек.")
                            user_data["warned_during_penalty"] = True
                            self.users[user_id] = user_data
                    return 
                
                if now - user_data["last_time"] < self.limit:
                    
                    if now - user_data["penalty_until"] > self.reset_timeout:
                        user_data["current_penalty"] = self.base_penalty
                    else:
                        user_data["current_penalty"] = min(user_data["current_penalty"] + self.penalty_step, self.max_penalty)
                        if user_data["current_penalty"] < self.base_penalty:
                            user_data["current_penalty"] = self.base_penalty

                    user_data["penalty_until"] = now + user_data["current_penalty"]
                    user_data["warned_during_penalty"] = False 
                    self.users[user_id] = user_data
                    
                    penalty_int = int(user_data["current_penalty"])
                    
                    if isinstance(event, CallbackQuery):
                        await event.answer(f"⚠️ За вами замечен спам! Блокировка: {penalty_int} сек.", show_alert=False)
                    elif isinstance(event, Message):
                        await event.answer(f"⚠️ **За вами замечен спам!**\nСлишком частые запросы. Функции бота заблокированы для вас на {penalty_int} секунд.")
                    
                    return 
                
                user_data["last_time"] = now
                user_data["warned_during_penalty"] = False
                self.users[user_id] = user_data

        return await handler(event, data)