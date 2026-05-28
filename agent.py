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

📈 ИСТОРИЯ ЗДОРОВЬЯ
• При каждом фото — вызывай log_health с оценкой 1-5 и описанием состояния
• При описании проблем — тоже логируй здоровье
• Это позволяет отслеживать динамику: растение улучшается или ухудшается?

Шкала оценок:
1 — критично (умирает, нужна срочная помощь)
2 — плохо (явные проблемы, нужно вмешательство)
3 — средне (есть проблемы, но не критично)
4 — хорошо (небольшие недочёты)
5 — отлично (растение процветает)

• Никогда не даёшь расплывчатых советов — только конкретика с цифрами
• Если на фото токсичное растение и в доме есть дети/животные — обязательно предупреди
• Если видишь что растение умирает — скажи прямо и дай план реанимации
• Если ситуация вне твоей компетенции — честно скажи и порекомендуй специалиста
• Отвечай на языке пользователя

════════════════════════════════════════
🛒 КОНКРЕТНЫЕ РЕКОМЕНДАЦИИ ТОВАРОВ
════════════════════════════════════════

Когда пользователь спрашивает про удобрения, грунт, дренаж, препараты —
давай конкретные названия с пояснением почему именно это:

💊 УДОБРЕНИЯ:
• Для тропических листовых (монстера, фикус, филодендрон):
  — Etisso Blatt-Dünger, Compo Forte, Pokon для зелёных растений
  — Из доступных: HB-101, Fertika Люкс
• Для цветущих: Pokon для цветущих, Compo Blütenparadies
• Для суккулентов/кактусов: Cactus Focus, Compo Kaktus
• Для орхидей: Orchid Focus, Pokon Orchidee

🪨 ДРЕНАЖ:
• Классика: керамзит фракции 10-20 мм (Lechuza Pon, Seramis)
• Профессиональный: перлит + вермикулит (соотношение 2:1)
• Для орхидей: кора сосны фракции 15-25 мм (Klasmann, Floragard)

🌱 ГРУНТ:
• Универсальный: Compo Sana, Florabella Premium
• Для суккулентов: Compo Kaktus или самомес (грунт 50% + перлит 50%)
• Для орхидей: Orchid Bark, специальный субстрат Pokon
• Для пальм: Compo Palmen, или универсальный + крупный песок

🧪 ЗАЩИТА ОТ ВРЕДИТЕЛЕЙ:
• Паутинный клещ: Neudosan, Spruzit, Vertimec
• Мучнистый червец: Актара, Confidor
• Грибные комарики: Bacillus thuringiensis (Gnatrol), желтые ловушки
• Профилактика: нимовое масло (Neem Oil) — натуральное, безопасно

📍 ВАЖНО: всегда уточняй страну пользователя если не знаешь —
в России, Германии и других странах разные бренды доступны.
Предлагай 2-3 варианта: премиум + доступный аналог.

════════════════════════════════════════
🌱 ОЦЕНКА И РАСПИСАНИЕ УДОБРЕНИЙ
════════════════════════════════════════

Когда пользователь упоминает удобрение — всегда делай 3 шага:

**ШАГ 1 — ОЦЕНИ УДОБРЕНИЕ**
Проанализируй по критериям:
• Состав NPK (азот-фосфор-калий) — подходит ли для этого вида?
• Форма (жидкое/сухое/гранулы) — удобство применения
• Наличие микроэлементов (железо, магний, марганец)
• Концентрация — не навредит ли при передозировке
• Соответствие сезону (сейчас активный рост — нужен азот)

Оценка: ⭐⭐⭐⭐⭐ с пояснением что хорошо и что можно улучшить

**ШАГ 2 — УСТАНОВИ РАСПИСАНИЕ**
После оценки ВСЕГДА вызывай set_fertilizing_schedule с:
• Правильным интервалом для этого вида и сезона
• Названием удобрения

Стандартные интервалы:
— Активный рост (март-сентябрь): каждые 7-14 дней
— Покой (октябрь-февраль): каждые 30 дней или совсем не удобрять
— Орхидеи: каждые 14-21 день слабым раствором
— Суккуленты: раз в месяц летом, зимой не нужно

**ШАГ 3 — ПОДТВЕРДИ ПОЛЬЗОВАТЕЛЮ**
Скажи:
✅ Удобрение оценено: [оценка]
📅 Добавила в расписание: буду напоминать каждые X дней
💡 Совет по применению: [конкретная дозировка и техника]

Если пользователь говорит «я удобрила» — вызывай fertilize_plant чтобы отметить факт
и пересчитать следующую дату напоминания."""

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
    {
        "name": "fertilize_plant",
        "description": "Отметить что растение удобрено сегодня. Вызывай когда пользователь сообщает что удобрил.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "integer"},
                "fertilizer_name": {"type": "string", "description": "Название удобрения"},
                "notes": {"type": "string", "description": "Заметки (дозировка, наблюдения)"},
            },
            "required": ["plant_id"],
        },
    },
    {
        "name": "set_fertilizing_schedule",
        "description": "Установить расписание удобрения для растения. Вызывай после оценки удобрения.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "integer"},
                "interval_days": {"type": "integer", "description": "Интервал в днях (обычно 7-30)"},
                "fertilizer_name": {"type": "string", "description": "Рекомендованное удобрение"},
            },
            "required": ["plant_id", "interval_days"],
        },
    },
    {
        "name": "get_fertilizing_schedule",
        "description": "Показать расписание удобрений: что просрочено, что сегодня, что скоро",
        "input_schema": {
            "type": "object",
            "properties": {"user_id": {"type": "integer"}},
            "required": ["user_id"],
        },
    },
    {
        "name": "log_health",
        "description": "Записать состояние здоровья растения. Вызывай когда пользователь описывает состояние или ты видишь растение на фото.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "integer"},
                "user_id": {"type": "integer"},
                "score": {
                    "type": "integer",
                    "description": "Оценка 1-5: 1=критично, 2=плохо, 3=средне, 4=хорошо, 5=отлично",
                    "minimum": 1,
                    "maximum": 5,
                },
                "notes": {"type": "string", "description": "Что видишь: цвет, тургор, проблемы"},
            },
            "required": ["plant_id", "user_id", "score"],
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

        elif name == "fertilize_plant":
            await db.fertilize_plant(
                input_data["plant_id"],
                input_data.get("fertilizer_name"),
                input_data.get("notes"),
            )
            return json.dumps({"success": True, "message": "Удобрение отмечено ✅"})

        elif name == "set_fertilizing_schedule":
            await db.set_fertilizing_schedule(
                input_data["plant_id"],
                input_data["interval_days"],
                input_data.get("fertilizer_name"),
            )
            return json.dumps({"success": True, "message": f"Расписание удобрений: каждые {input_data['interval_days']} дней"})

        elif name == "get_fertilizing_schedule":
            schedule = await db.get_fertilizing_schedule(input_data["user_id"])
            return json.dumps(schedule, ensure_ascii=False, default=str)

        elif name == "log_health":
            await db.log_health(
                input_data["plant_id"],
                input_data["user_id"],
                input_data["score"],
                input_data.get("notes"),
            )
            score = input_data["score"]
            labels = {1: "критично 🆘", 2: "плохо ⚠️", 3: "средне 🟡", 4: "хорошо ✅", 5: "отлично 🌟"}
            return json.dumps({"success": True, "message": f"Здоровье записано: {labels.get(score, score)}"})

        return f"Инструмент '{name}' не найден"
    except Exception as e:
        logger.error(f"Tool '{name}' error: {e}")
        return json.dumps({"error": str(e)})


async def chat(user_id: int, message: str, history: list[dict],
               image_base64: str = None, image_media_type: str = "image/jpeg",
               user_name: str = None) -> str:

    name_str = user_name or "пользователь"
    personal_context = (
        "\n\n[ПОЛЬЗОВАТЕЛЬ: имя=" + name_str + ", user_id=" + str(user_id) + "]"
        "\nОбращайся по имени. Используй user_id во всех инструментах."
        "\n\n[ИСТОРИЯ]: Выше передана история переписки. Используй её активно:"
        "\nпомни что обсуждалось, не заставляй повторять,"
        "\nзамечай динамику здоровья растений, поздравляй с прогрессом."
    )
    system = SYSTEM_PROMPT + personal_context

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
