# Smartline

Автоматизация учёта активности игроков клана Lineage 2 на фортовых сражениях.

Игроки пишут сообщения в Telegram-группу в привычном виде, бот собирает их,
парсер разбирает активность, а через веб-интерфейс командир клана (КЛ) видит
статистику, проверяет ошибки и выгружает данные в Excel.

Поток данных:

Telegram-группа → Telegram Bot (long polling) → Parser → Validation →
Service → Django ORM (PostgreSQL) → Web-интерфейс → статистика / выплаты / Excel.

## Требования

- Python 3.11 или новее
- PostgreSQL 17 (для продакшена; для локальной разработки можно использовать SQLite)
- Доступ к Telegram Bot API (токен бота, полученный у @BotFather)
- pip и виртуальное окружение (рекомендуется)

Зависимости указаны в `requirements.txt`:
Django, psycopg (бинарный), python-dotenv, openpyxl, requests.

## Установка

```bash
git clone <repo-url> Smartline
cd Smartline
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # отредактируйте значения (см. ниже)
```

## Переменные окружения

Все секреты и настройки хранятся в файле `.env` (он не коммитится в git).
Список переменных (шаблон — в `.env.example`):

| Переменная | Назначение |
|---|---|
| `DJANGO_SECRET_KEY` | Секретный ключ Django. Обязателен в продакшене. |
| `DEBUG` | `True`/`False`. В продакшене — `False`. |
| `ALLOWED_HOSTS` | Через запятую, например `localhost,127.0.0.1`. |
| `POSTGRES_DB` | Имя базы PostgreSQL. |
| `POSTGRES_USER` | Пользователь PostgreSQL. |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL. |
| `POSTGRES_HOST` | Хост БД (`localhost` локально, `db` в docker-compose). |
| `POSTGRES_PORT` | Порт БД (обычно `5432`). |
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather. |
| `ADMIN_TELEGRAM_CHAT_IDS` | chat_id администраторов/КЛ через запятую (для уведомлений об ошибках). |
| `DEF_HOURLY_RATE` | Почасовая ставка для DEF-активности (Decimal, например `10`). |
| `DATABASE_ENGINE` | `postgresql` (по умолчанию) или `sqlite` для локальной разработки без Postgres. |

> Никогда не коммитьте `.env` с реальными секретами. Используйте `.env.example` как шаблон.

## Запуск локально

### База данных

Вариант А — PostgreSQL через docker-compose:

```bash
docker-compose up -d db
```

Вариант Б — SQLite (без Postgres): добавьте в `.env` строку `DATABASE_ENGINE=sqlite`.

### Миграции и суперпользователь

```bash
python manage.py migrate
python manage.py createsuperuser
```

### Веб-интерфейс (Django)

```bash
python manage.py runserver
```

Откройте http://localhost:8000/ и войдите под суперпользователем.

### Telegram Bot

Бот работает в режиме long polling (отдельный процесс), публичный URL не нужен.

```bash
python manage.py poll
```

Важно:
- Запускайте ровно **один** инстанс `poll`. Два и более вызовут `HTTP 409 Conflict`
  (Telegram не отдаёт обновления двум процессам одновременно).
- Чтобы бот читал сообщения группы, в @BotFather выполните `/setprivacy` и
  выберите **Disable** (борд приватности должен быть выключен). Иначе бот видит
  только команды, а не обычные сообщения.

## Формат сообщений активности

Сообщение должно начинаться с `+`. Общий вид:

```
+<часы> | <тип> | <ник> | <описание>
```

- `<часы>` — `1`, `2`, `0,5`, `0.5`, `0,3` (через запятую или точку; используется Decimal).
- `<тип>` — `деф`/`def` (оплачивается) или `фарм`/`farm` (только статистика). Регистр не важен.
- Разделители: `|`, `-`, `–` (en dash), `—` (em dash), с пробелами или без.
- `<ник>` — один ник. Несколько ников через запятую: `Swettka, Vas, Dimas`
  (создаёт активность для каждого; такая «сводка волны» не привязывается к отправителю).
- Обычные сообщения без `+` не учитываются.

Примеры:

```
+1 | деф | Swettka | Первая волна
+0,5 | фарм | Vas | прокачка
+1 | ДЕФ | Swettka, Vas, Dimas | Вторая волна
```

Если сообщение не разбирается, создаётся запись об ошибке, а бот отвечает
в группе под исходным сообщением. Исправить можно, отредактировав сообщение:
если оно было в ошибке — пересчитается; если уже учтено — правка игнорируется.

## Запуск тестов

```bash
python manage.py test
```

## Создание администратора

```bash
python manage.py createsuperuser
```

## Docker (опционально)

Поднимает PostgreSQL, веб и бота одновременно:

```bash
docker-compose up --build
```

Сервисы: `web` (runserver :8000) и `telegram_bot` (`manage.py poll`).

## Структура проекта

- `core/` — доменная логика: модели (`Player`, `Activity`, `TelegramMessage`,
  `ProcessingError`), парсер сообщений, сервисы обработки.
- `telegram_bot/` — клиент Telegram (long polling на `requests`), обработка update,
  команда `manage.py poll`.
- `reports/` — статистика и экспорт в Excel (openpyxl).
- `config/` — настройки Django.

## Примечания по безопасности

- Секреты только в `.env`; `.env` в `.gitignore`.
- Токен бота не попадает в логи (маскируется централизованно).
- CSRF и autoescape Django включены.
