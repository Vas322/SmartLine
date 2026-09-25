# Smartline

Автоматизация учёта активности игроков клана Lineage 2 на фортовых сражениях.

Игроки пишут сообщения в Telegram-группу в привычном виде, бот собирает их,
парсер разбирает активность, а через веб-интерфейс командир клана (КЛ) видит
статистику, проверяет ошибки и выгружает данные в Excel.

Поток данных:

Telegram-группа → Telegram Bot (long polling) → Parser → Validation →
Service → Django ORM (PostgreSQL) → Web-интерфейс → статистика / выплаты / Excel.

## Требования

- Python 3.14 или новее
- PostgreSQL 16 (для продакшена; для локальной разработки можно использовать SQLite)
- Доступ к Telegram Bot API (токен бота, полученный у @BotFather)
- pip и виртуальное окружение (рекомендуется)

Зависимости указаны в `requirements.txt`:
Django, psycopg (бинарный), python-dotenv, openpyxl, requests, gunicorn,
whitenoise, yadisk.

Dev-зависимости указаны в `requirements-dev.txt` (в прод-образ не устанавливаются):
ruff (линтер и форматтер).

## Установка

```bash
git clone <repo-url> Smartline
cd Smartline
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # только для разработки (ruff)
cp .env.example .env             # отредактируйте значения (см. ниже)
```

## Переменные окружения

Все секреты и настройки хранятся в файле `.env` (он не коммитится в git).
Список переменных (шаблон — в `.env.example`):

| Переменная | Назначение |
|---|---|
| `DJANGO_SECRET_KEY` | Секретный ключ Django. Обязателен в продакшене (рекомендуется не короче 50 символов). |
| `DEBUG` | `True`/`False`. В продакшене — `False`. |
| `ALLOWED_HOSTS` | Через запятую, например `localhost,127.0.0.1`. |
| `DATABASE_ENGINE` | `postgresql` (по умолчанию) или `sqlite` для локальной разработки без Postgres. |
| `POSTGRES_DB` | Имя базы PostgreSQL. |
| `POSTGRES_USER` | Пользователь PostgreSQL. |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL. |
| `POSTGRES_HOST` | Хост БД (`localhost` локально, `smartline-db` в docker-compose). |
| `POSTGRES_PORT` | Порт БД (обычно `5432`). |
| `STATIC_ROOT` | Каталог собранной статики (по умолчанию `staticfiles`). |
| `CSRF_COOKIE_SECURE` | `True`/`False`. Secure-cookie для CSRF (в продакшене за HTTPS — `True`). |
| `SESSION_COOKIE_SECURE` | `True`/`False`. Secure-cookie для сессий. |
| `CSRF_TRUSTED_ORIGINS` | Через запятую, доверенные origins (например `https://smartline-clan.ru`). |
| `SECURE_SSL_REDIRECT` | `True`/`False`. Принудительный редирект на HTTPS (в продакшене за HTTPS — `True`). |
| `SECURE_HSTS_SECONDS` | Число секунд HSTS (в продакшене — например `31536000`; `0` — выключено). |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True`/`False`. Включать ли поддомены в HSTS. |
| `SECURE_HSTS_PRELOAD` | `True`/`False`. HSTS preload. |
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather. |
| `ADMIN_TELEGRAM_CHAT_IDS` | chat_id администраторов/КЛ через запятую (для уведомлений об ошибках). |
| `SCHEDULE_SOURCE_CHAT_ID` | ID канала-источника расписания (где бот альянса публикует расписание). |
| `ALLIANCE_BOT_USERNAME` | username бота альянса, чьи сообщения зеркалируем (без `@`). |
| `CLAN_CHAT_ID` | ID основной группы клана (опционально; если пусто — берётся из последнего обработанного сообщения). |
| `SCHEDULE_MIRROR_IGNORE_PREFIXES` | Префиксы для игнорирования при зеркалировании расписания (через запятую). |
| `SCHEDULE_MIRROR_TARGET_THREAD_ID` | ID темы (message_thread_id) в целевой группе для зеркала расписания (опционально). |
| `EMAIL_HOST` | SMTP-хост (например `smtp.yandex.ru`). |
| `EMAIL_PORT` | Порт SMTP (по умолчанию `465`). |
| `EMAIL_HOST_USER` | Пользователь SMTP. |
| `EMAIL_HOST_PASSWORD` | Пароль/пароль приложения SMTP. |
| `EMAIL_USE_SSL` | `True`/`False`. Использовать SSL для SMTP. |
| `DEFAULT_FROM_EMAIL` | Адрес отправителя писем. |
| `YANDEX_DISK_TOKEN` | Токен Яндекс.Диска для бэкапов. |
| `YANDEX_DISK_BACKUP_DIR` | Каталог на Яндекс.Диске для бэкапов. |
| `BACKUP_ENCRYPTION_PASSPHRASE` | Парольная фраза для шифрования бэкапов. |
| `BOSS_RESPAWN_SOURCE_URL` | URL источника расписания респа РБ (например `https://craft-calc.ru/bosses-respawn`). |
| `BOSS_RESPAWN_PARSE_INTERVAL_MINUTES` | Частота парсинга респов РБ (минуты). |
| `PUBLIC_SITE_URL` | Публичный базовый URL (для `{url}` в уведомлениях об Эпик РБ). |

> Никогда не коммитьте `.env` с реальными секретами. Используйте `.env.example` как шаблон.

## Запуск локально

### База данных

Вариант А — PostgreSQL через docker-compose:

```bash
docker-compose up -d smartline-db
```

Вариант Б — SQLite (без Postgres): добавьте в `.env` строку `DATABASE_ENGINE=sqlite`.

### Миграции и суперпользователь

```bash
python manage.py migrate
python manage.py createsuperuser
```

### Одна команда для локальной разработки

```bash
python manage.py dev
```

`dev` запускает в одном процессе Django-сервер (http://localhost:8000/),
Telegram-бота (long polling), проверку расписаний (scheduler, каждые 60 секунд),
парсер респаунов РБ (каждые 30 минут) и проверку уведомлений об Эпик РБ (каждые
5 минут) — всё, что нужно для локальной разработки, одной командой.

Войдите под суперпользователем и откройте http://localhost:8000/.

### Отдельные фоновые команды (только прод)

На проде фоновые задачи выполняются docker-сервисами (см. раздел «Docker»),
поэтому локально их вручную запускать не нужно. Основные management-команды:

- `send_scheduled_messages` — отправка сообщений по расписанию.
- `send_epic_boss_notifications` — отправка уведомлений об Эпик РБ.
- `cleanup_old_messages` — очистка старых сообщений.
- `parse_boss_respawns` — парсинг респаунов РБ с craft-calc.ru.
- `backup` — резервное копирование (с шифрованием и загрузкой на Яндекс.Диск).

### Telegram Bot (вручную)

Бот работает в режиме long polling (отдельный процесс), публичный URL не нужен.
В локальной разработке он запускается командой `dev`; отдельно можно запустить:

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
+ЧЧ.ММ | ТИП | НИК | ВРЕМЯ_НАЧАЛА_ВОЛНЫ | ОПИСАНИЕ
```

Порядок полей строгий: количество, затем тип, затем ник (один), затем время начала
волны, затем описание. Перепутанный порядок считается ошибкой.

- `<ЧЧ.ММ>` — количество часов: `1`, `2`, `0,5`, `0.5`, `0,3` (через запятую или точку; используется Decimal).
- `<ТИП>` — `деф`/`def` (оплачивается), `фарм`/`farm` (только статистика), `каст`/`cast`/`перекаст`/`recast` (оплачивается по CastRate). Регистр не важен. Допустимы комбинации `деф+каст`/`def+cast` и `фарм каст`/`farm cast`. `DEF+FARM` в одном сообщении — ошибка.
- `<НИК>` — один ник, только буквы (рус/англ) и цифры. Каждый пишет только за себя; мультиник не поддерживается (ошибка invalid_nickname).
- `<ВРЕМЯ_НАЧАЛА_ВОЛНЫ>` — обязательное поле. Допускаются разделители `.` и `:`
  (`11.56` и `11:56` — одно и то же время). Если время не указано или указано
  неверно, сообщение считается ошибочным.
- `<ОПИСАНИЕ>` — необязательно. Допускается сообщение из четырёх частей (без описания).
- Разделители: `|`, `-`, `–` (en dash), `—` (em dash), с пробелами или без.
- Обычные сообщения без `+` не учитываются.

Примеры:

```
+1 | деф | Swettka | 11.56 | Первая волна
+0,5 | фарм | Vas | 23.10 | прокачка
+1 | ДЕФ | Swettka | 11:56 | Вторая волна
+2 | фарм | Ostin | 23.10
```

Если сообщение не разбирается, создаётся запись об ошибке, а бот отвечает
в группе под исходным сообщением. Исправить можно, отредактировав сообщение:
если оно было в ошибке — пересчитается; если уже учтено — правка игнорируется.

## Оплата

Оплачивается DEF и CAST (по отдельным таблицам ставок `Rate` и `CastRate`).
FARM учитывается в статистике, но не оплачивается. Комбинация `деф+каст` —
сумма оплат DEF и CAST (без множителей).

Размер оплаты зависит от времени суток и настраивается на странице Settings
веб-интерфейса, а не через переменные окружения и не в коде.

Ставки DEF по умолчанию (кк = миллионы адены):

- `00:01–08:00` → 100 кк/ч
- `08:01–16:00` → 75 кк/ч
- `16:01–00:00` → 50 кк/ч

## Запуск тестов

```bash
python manage.py test
```

## Создание администратора

```bash
python manage.py createsuperuser
```

## Docker

Продакшен запускается через Docker Compose (см. `docker-compose.yml`). Сервисы:

- `smartline-db` — PostgreSQL 16 (volume `smartline_db_data`).
- `smartline-web` — Django (Gunicorn на :8000, `collectstatic` при старте), подключён
  к внешней сети `caddy_net` (имя `app_default`) для проксирования через Caddy.
- `smartline-bot` — Telegram long polling (`manage.py poll`).
- `smartline-scheduler` — фоновые задачи: `send_scheduled_messages` и
  `send_epic_boss_notifications`, каждые 300 секунд.
- `smartline-cleanup` — очистка старых сообщений (`cleanup_old_messages`), раз в сутки.
- `smartline-boss-respawn` — парсинг респаунов РБ (`parse_boss_respawns`), каждые 1800 секунд.
- `smartline-backup` — сервис из profile `tools` (postgres:16, вспомогательный для
  pg_dump). Основной бэкап выполняется командой
  `docker compose exec smartline-web python manage.py backup` — шифрованный (GPG)
  дамп БД + git-бандл с загрузкой на Яндекс.Диск.

Собрать и запустить все сервисы (кроме `tools`):

```bash
docker compose up -d --build
```

### Порядок обновления на сервере

1. `cd /opt/smartline`
2. `git pull origin main`
3. `docker compose up -d --build smartline-web smartline-bot smartline-scheduler smartline-cleanup smartline-boss-respawn`
4. `docker compose exec smartline-web python manage.py migrate`
5. `docker compose restart smartline-scheduler smartline-cleanup smartline-boss-respawn`
6. Проверка: `docker compose ps` и `docker compose logs --tail=50 smartline-boss-respawn`

**КРИТИЧНО:** миграции выполняются **только после** пересборки контейнеров
(шаг 4 после шага 3). Если выполнить `migrate` в старом контейнере до
`up -d --build`, он не увидит новые миграции («No migrations to apply»), а после
пересборки новые сервисы упадут на отсутствии таблиц.

## Структура проекта

- `core/` — доменная логика (пакет):
  - `core/views/` — тонкие views: `dashboard`, `players`, `activities`,
    `messages`, `settings`, `instructions`, `auth`, `common`, `boss_respawn`.
  - `core/models/` — модели: `base`, `telegram`, `activity`, `registration`,
    `instructions`, `welcome`, `settings_bonus`, `boss_respawn`.
  - `core/forms/` — формы: `players`, `activity`, `rates`, `instructions`,
    `scheduled_messages`, `settings`, `auth`.
  - `core/services/` — бизнес-логика: `activity_service`, `messaging_service`,
    `scheduling_service`, `welcome_service`, `stats`, `rates`,
    `schedule_mirror_service`, `summoner_bonus_service`, `boss_respawn_service`,
    `boss_notification_service`, `notification_service`.
  - `core/tests/web/` — тесты веб-интерфейса.
  - `core/templatetags/` — template-фильтры (`instruction_tags`, `error_extras`, `math_tags`).
  - `core/parsers.py` — детерминированный парсер сообщений.
  - `core/error_messages.py` — тексты ошибок.
- `telegram_bot/` — клиент Telegram (long polling на `requests`), обработка update,
  команды `manage.py poll` и `manage.py dev`.
- `reports/` — экспорт в Excel (openpyxl).
- `config/` — настройки Django.

### Основные функции

- Учёт активности игроков из Telegram-сообщений (DEF/FARM/CAST, время волны, Decimal).
- Отправка сообщений из веб-интерфейса в Telegram (ответ и новое сообщение, аудит
  через `OutgoingMessage`).
- Регулярные сообщения по расписанию (`ScheduledMessage`, темы Telegram).
- Приветствие новичков и авто-создание `Player` по входу в группу (welcome).
- Публичная страница респаунов РБ (`/rb/`, парсинг craft-calc.ru) и уведомления
  об Эпик РБ.
- Надбавка за суммонеров (`SummonerBonusSettings`, `summoner_count` у игрока).
- Рендер инструкций с мини-разметкой (заголовки `##`, блоки `>`, списки, заметки).

## Примечания по безопасности

- Секреты только в `.env`; `.env` в `.gitignore`.
- Токен бота не попадает в логи (маскируется централизованно).
- CSRF и autoescape Django включены.
- HTTPS-hardening (Фаза 4) управляется переменными окружения:
  `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`,
  `SECURE_HSTS_PRELOAD`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_SECURE`,
  `CSRF_TRUSTED_ORIGINS`. На сервере за HTTPS включите редирект и HSTS (см. `.env.example`).
