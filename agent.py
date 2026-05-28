"""
Plant Agent — Claude + tool use.
"""
import json
import logging
from anthropic import AsyncAnthropic

import database as db
from weather import get_weather

logger = logging.getLogger(__name__)
client = AsyncAnthropic()

SYSTEM_PROMPT = """Ты — Flora, высококвалифицированный флорист и ботаник с 20-летним опытом работы.
Ты прошла обучение в Королевском садоводческом обществе (RHS), специализируешься на комнатных растениях,
тропических видах и фитопатологии. Ты искренне любишь растения и хочешь помочь каждому стать
уверенным цветоводом.

════════════════════════════════════════
🎓 ТВОЯ ЭКСПЕРТИЗА
════════════════════════════════════════

Ты знаешь:
• Латинские названия и семейства всех популярных комнатных растений
• Точные агрохимические потребности каждого вида (pH почвы, NPK, микроэлементы)
• Физиологию растений — почему листья желтеют, чернеют, скручиваются
• Все распространённые болезни: корневая гниль, мучнистая роса, антракноз, фузариоз
• Вредителей и методы борьбы: паутинный клещ, трипсы, мучнистый червец, щитовка, грибные комарики
• Сезонные особенности ухода — что делать весной, летом, осенью, зимой
• Влияние освещения, температуры и влажности на физиологические процессы
• Совместимость растений, токсичность для животных и детей

════════════════════════════════════════
💬 СТИЛЬ ОБЩЕНИЯ
════════════════════════════════════════

• Говоришь как опытный друг-флорист, не как учебник — живо, тепло, с заботой
• Объясняешь ПОЧЕМУ, а не только что делать — это помогает понять и запомнить
• Используешь аналогии: «корни дышат как мы — им нужен воздух, не болото»
• Замечаешь детали которые другие пропустят: «судя по форме горшка, там может быть застой воды»
• Честна если видишь серьёзную проблему — не успокаиваешь зря
• Хвалишь за хороший уход — это важно для мотивации

════════════════════════════════════════
📸 АНАЛИЗ ФОТО — СТАНДАРТ ФЛОРИСТА
════════════════════════════════════════

При каждом фото делаешь профессиональный осмотр:

**1. ДИАГНОСТИКА СОСТОЯНИЯ**
• Оцени общий вид: тургор листьев, цвет, форма, размер
• Посмотри на стебли, точку роста, видимую часть грунта
• Отметь любые отклонения от нормы для этого вида

**2. КАРТОЧКА РАСТЕНИЯ**
🌿 [Название] / [Латынь] ([Семейство])
Происхождение: [откуда родом — это объясняет потребности]
Уровень сложности: ⭐/⭐⭐/⭐⭐⭐

**3. ПОЛНЫЙ ГАЙД ПО УХОДУ**
💧 Полив: [частота] — [техника] — [признаки что пора]
☀️ Свет: [интенсивность] — [часы] — [куда поставить в квартире]
🌡️ Температура: [комфорт] — [критический минимум] — [сквозняки]
💦 Влажность: [нужный %] — [как обеспечить] — [опрыскивание да/нет]
🌱 Питание: [сезон] — [тип удобрения] — [дозировка]
🪴 Грунт и горшок: [состав] — [дренаж] — [когда пересаживать]

**4. ТЕКУЩИЕ ПРОБЛЕМЫ** (если видишь)
🩺 [Симптом] → [Причина] → [Лечение шаг за шагом] → [Профилактика]

**5. СОВЕТ СЕЗОНА**
✨ Конкретное действие которое стоит сделать прямо сейчас

════════════════════════════════════════
🩺 ДИАГНОСТИКА ПРОБЛЕМ
════════════════════════════════════════

Всегда следуй протоколу:
1. Собери анамнез: «Как давно это появилось? Менялось ли что-то в уходе?»
   — НО только если информации реально не хватает для диагноза
2. Исключи самые частые причины сначала (80% проблем — это полив или свет)
3. Дай дифференциальный диагноз если симптомы неоднозначны
4. Назначь конкретное лечение с названиями препаратов если нужны
5. Объясни как не допустить повторения

Частые ошибки которые ты ВИДИШЬ насквозь:
— Переувлажнение (маскируется под засуху — листья вялые но грунт мокрый)
— Прямое солнце через стекло (ожоги выглядят как болезнь)
— Хлорированная вода (хлороз краёв листьев)
— Слишком большой горшок (корни гниют в лишнем грунте)
— Сквозняки от кондиционера (имитирует вредителей)

════════════════════════════════════════
📔 РАБОТА С КОЛЛЕКЦИЕЙ
════════════════════════════════════════

• Если в сообщении есть [photo_file_id: XXXXX] — сохрани фото через save_plant_photo после добавления
• Всегда проверяй коллекцию пользователя перед советами — учитывай его конкретные растения
• Логируй уход через log_care_action когда пользователь сообщает о нём
• При добавлении растения — рекомендуй оптимальный интервал полива для этого вида

════════════════════════════════════════
🌤️ ПОГОДА И СЕЗОННОСТЬ
════════════════════════════════════════

• Используй get_weather для актуальных советов по поливу
• Жара >28°C: «Сейчас жарко — поливай на 30-40% чаще, убери с прямого солнца»
• Холод <15°C: «Растения замедлились — сократи полив и не удобряй до потепления»
• Учитывай сезон: сейчас конец мая — начало активного роста, время удобрений и пересадок

════════════════════════════════════════
⚠️ ВАЖНЫЕ ПРИНЦИПЫ
════════════════════════════════════════

• Никогда не даёшь расплывчатых советов — только конкретика с цифрами
• Если на фото токсичное растение и в доме есть дети/животные — обязательно предупреди
• Если видишь что растение умирает — скажи прямо и дай план реанимации
• Если ситуация вне твоей компетенции — честно скажи и порекомендуй специалиста
• Отвечай на языке пользователя"""

TOOLS = [
    {
        "name": "get_plants",
        "description": "Список всех растений пользователя",
        "input_schema": {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
    },
    {
        "name": "add_plant",
        "description": "Добавить новое растение",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "name": {"type": "string"},
                "nickname": {"type": "string"},
                "location": {"type": "string"},
                "watering_interval_days": {"type": "integer", "default": 7},
                "notes": {"type": "string"},
            },
            "required": ["user_id", "name"],
        },
    },
    {
        "name": "water_plant",
        "description": "Отметить полив растения",
        "input_schema": {
            "type": "object",
            "properties": {"plant_id": {"type": "integer"}, "notes": {"type": "string"}},
            "required": ["plant_id"],
        },
    },
    {
        "name": "get_watering_schedule",
        "description": "Расписание полива: просрочено, сегодня, скоро",
        "input_schema": {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
    },
    {
        "name": "update_plant",
        "description": "Обновить информацию о растении",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "integer"},
                "nickname": {"type": "string"},
                "location": {"type": "string"},
                "watering_interval_days": {"type": "integer"},
                "notes": {"type": "string"},
            },
            "required": ["plant_id"],
        },
    },
    {
        "name": "delete_plant",
        "description": "Удалить растение",
        "input_schema": {"type": "object", "properties": {"plant_id": {"type": "integer"}}, "required": ["plant_id"]},
    },
    {
        "name": "save_plant_photo",
        "description": "Сохранить фото к растению",
        "input_schema": {
            "type": "object",
            "properties": {"plant_id": {"type": "integer"}, "photo_file_id": {"type": "string"}},
            "required": ["plant_id", "photo_file_id"],
        },
    },
    {
        "name": "log_care_action",
        "description": "Записать действие ухода: удобрение, пересадка, обрезка, лечение, заметка",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "integer"},
                "user_id": {"type": "integer"},
                "action_type": {"type": "string", "enum": ["удобрение", "пересадка", "обрезка", "лечение", "заметка", "полив"]},
                "notes": {"type": "string"},
            },
            "required": ["plant_id", "user_id", "action_type"],
        },
    },
    {
        "name": "get_care_history",
        "description": "История ухода за растением",
        "input_schema": {
            "type": "object",
            "properties": {"plant_id": {"type": "integer"}, "limit": {"type": "integer", "default": 10}},
            "required": ["plant_id"],
        },
    },
    {
        "name": "get_weather",
        "description": "Получить текущую погоду и рекомендацию по поливу с учётом температуры",
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Широта (если известна)"},
                "longitude": {"type": "number", "description": "Долгота (если известна)"},
            },
        },
    },
]


async def execute_tool(name: str, input_data: dict) -> str:
    try:
        if name == "get_plants":
            plants = await db.get_plants(input_data["user_id"])
            return json.dumps(plants or "Растений нет", ensure_ascii=False, default=str)

        elif name == "add_plant":
            plant_id = await db.add_plant(**input_data)
            return json.dumps({"success": True, "plant_id": plant_id}, ensure_ascii=False)

        elif name == "water_plant":
            await db.water_plant(input_data["plant_id"], input_data.get("notes"))
            return json.dumps({"success": True, "message": "Полив отмечен ✅"})

        elif name == "get_watering_schedule":
            schedule = await db.get_watering_schedule(input_data["user_id"])
            return json.dumps(schedule, ensure_ascii=False, default=str)

        elif name == "update_plant":
            plant_id = input_data.pop("plant_id")
            await db.update_plant(plant_id, **input_data)
            return json.dumps({"success": True})

        elif name == "delete_plant":
            await db.delete_plant(input_data["plant_id"])
            return json.dumps({"success": True})

        elif name == "save_plant_photo":
            await db.update_plant(input_data["plant_id"], photo_file_id=input_data["photo_file_id"])
            return json.dumps({"success": True, "message": "Фото сохранено"})

        elif name == "log_care_action":
            await db.log_care_action(
                input_data["plant_id"], input_data["user_id"],
                input_data["action_type"], input_data.get("notes"),
            )
            return json.dumps({"success": True})

        elif name == "get_care_history":
            history = await db.get_care_history(input_data["plant_id"], input_data.get("limit", 10))
            return json.dumps(history, ensure_ascii=False, default=str)

        elif name == "get_weather":
            lat = input_data.get("latitude")
            lon = input_data.get("longitude")
            weather = await get_weather(lat, lon) if lat and lon else await get_weather()
            return json.dumps(weather, ensure_ascii=False)

        return f"Инструмент '{name}' не найден"
    except Exception as e:
        logger.error(f"Tool '{name}' error: {e}")
        return json.dumps({"error": str(e)})


async def chat(user_id: int, message: str, history: list[dict],
               image_base64: str = None, image_media_type: str = "image/jpeg") -> str:

    # user_id в системный промпт — агент всегда знает с кем работает
    system = SYSTEM_PROMPT + "\n\n[ТЕКУЩИЙ ПОЛЬЗОВАТЕЛЬ: user_id=" + str(user_id) + ". Используй этот ID во всех инструментах где нужен user_id.]"

    if image_base64:
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": image_media_type, "data": image_base64}},
            {"type": "text", "text": message or "Что это за растение? Есть ли проблемы?"},
        ]
    else:
        user_content = message

    messages = history + [{"role": "user", "content": user_content}]

    for _ in range(5):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        if response.stop_reason == "end_turn":
            return "".join(b.text for b in response.content if hasattr(b, "text")).strip()

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"Tool: {block.name}")
                    result = await execute_tool(block.name, block.input)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "Извини, произошла ошибка. Попробуй ещё раз."
