# Telegram AI Assistant Bot

Trợ lý AI cá nhân trên Telegram — đưa AI vào tay mày để hỏi nhanh, ghi chú, đặt lịch, tổng hợp meeting. Không cần mở web AI nữa.

## Triết lý
- **Chat tự nhiên, không commands** — cứ nói, AI tự hiểu
- **Multi-tier free LLM** — ưu tiên model rẻ/free, fallback tự động khi hết quota
- **Solo user** — whitelist theo Telegram user_id

## Tính năng (qua chat tự nhiên)
| Ví dụ mày nói | AI làm gì |
|---|---|
| "trend mobile game VN 2026 như nào?" | Trả lời trực tiếp |
| "nhắc tao 3h chiều mai họp product" | Tạo lịch + APScheduler push reminder đúng giờ |
| "ghi lại: KPI Q1 đạt 85%" | Lưu note + auto-tag |
| "tao có note gì về Q1?" | Search notes, tóm tắt kết quả |
| "lịch tuần này có gì?" | List schedules 7 ngày tới |
| "tổng hợp meeting này: [paste]" | Tự tóm tắt + action items + phản biện + lưu DB |

## LLM Tier Chain

```
Tier 0 → Gemini 2.5 Flash Lite   (simple)
Tier 1 → Gemini 2.5 Flash        (medium)
Tier 2 → Gemini 2.5 Pro          (complex)
Tier 3 → Groq Llama 3.3 70B      (fallback)
```

- Classifier regex phân loại query → chọn tier bắt đầu
- Mỗi tier có quota tracker (RPM + RPD) — hết quota tự động rớt xuống tier kế
- Quota in-memory (reset khi restart bot)

## Yêu cầu
- Python 3.12+
- Docker + Docker Compose
- Telegram Bot Token (@BotFather)
- Gemini API Key ([aistudio.google.com](https://aistudio.google.com))
- Groq API Key ([console.groq.com](https://console.groq.com))

## Cài đặt nhanh (VPS Ubuntu 22.04)

```bash
git clone <repo-url>
cd telegram-ai-assistant
cp .env.example .env
# Điền: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, GROQ_API_KEY, ALLOWED_USER_IDS
make deploy
make migrate
```

Lấy Telegram user_id: chat với [@userinfobot](https://t.me/userinfobot).

## Cấu hình `.env`

| Biến | Mô tả |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token từ @BotFather |
| `ALLOWED_USER_IDS` | Telegram user_id được dùng (comma-separated) |
| `GEMINI_API_KEY` | Key từ aistudio.google.com |
| `GROQ_API_KEY` | Key từ console.groq.com |
| `DATABASE_URL` | PostgreSQL URL (docker-compose đã set) |
| `BOT_MODE` | `polling` (dev) hoặc `webhook` (prod) |
| `SCHEDULER_TIMEZONE` | Mặc định `Asia/Ho_Chi_Minh` |
| `MODEL_TIER1..4` | Override tên model nếu cần |

## Development

```bash
pip install -r requirements-dev.txt
cp .env.example .env
docker-compose -f docker/docker-compose.yml up -d db
make migrate
make dev
```

## Testing

```bash
make test
```

## Lệnh bot (chỉ 3 lệnh)

| Lệnh | Mô tả |
|---|---|
| `/start` | Chào + hướng dẫn nhanh |
| `/help` | Ví dụ cách dùng |
| `/status` | Xem quota RPM/RPD của các tier |

**Còn lại: cứ chat tự nhiên bằng tiếng Việt.**

## Security
- Whitelist user_id: `ALLOWED_USER_IDS`
- Rate limit 30 msg/phút/user
- Secrets trong `.env`, không commit
- SQLAlchemy ORM, không raw SQL
- Input truncate trước khi gửi LLM

## Makefile

| Command | Mô tả |
|---|---|
| `make dev` | Chạy local (polling) |
| `make test` | pytest |
| `make deploy` | Build + start Docker |
| `make stop` | Dừng containers |
| `make logs` | Logs realtime |
| `make migrate` | Alembic upgrade head |
| `make backup-db` | Dump PostgreSQL |
