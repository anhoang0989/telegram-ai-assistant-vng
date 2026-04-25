# CLAUDE.md — Telegram AI Assistant (VNG)

> Đọc file này TRƯỚC khi code. Chứa flow làm việc + convention bắt buộc.
> User là solo dev VNG Games, dùng Vietnamese, tone "tại hạ/đại hiệp" trong bot.

## 0. Workflow bắt buộc khi user yêu cầu thêm/sửa feature

1. **Đọc code liên quan trước khi sửa** (Read tool, không đoán mò).
2. **Tự kiểm thử logic** trước khi push:
   - `py -c "import ast; ast.parse(open(f).read())"` cho mọi file `.py` đụng vào.
   - Nếu có DB schema thay đổi → thêm `ALTER TABLE ... IF NOT EXISTS` vào `init_db()` trong `src/main.py` (idempotent migration tay, KHÔNG dùng Alembic cho thay đổi nhỏ).
3. **Update CHANGELOG.md** — bump version, ghi rõ Added/Changed/Fixed/Security/Removed (Keep a Changelog format).
4. **Security review** — bất cứ khi nào đụng đến API key, log, hoặc input từ user:
   - Key phải mã hoá Fernet ở DB (đã có `src/db/repositories/user_keys.py`).
   - Log không được chứa plaintext key (đã có `_safe_log_text()` trong `src/bot/middleware.py`).
   - Tin nhắn chứa key phải `update.message.delete()` ngay sau khi save.
5. **Commit + push** — commit message tiếng Việt OK, có Co-Authored-By Claude. Dokploy auto-deploy khi push lên `main`.
6. **Báo cho user** số commit hash + tóm tắt thay đổi để user verify trên Dokploy.

## 1. Stack tech

- Python 3.12, python-telegram-bot v21 (async)
- google-genai SDK + groq SDK (BYOK per-call, Client cached `dict[api_key, Client]`)
- PostgreSQL + SQLAlchemy 2 async + asyncpg + psycopg2-binary
- Fernet encryption cho API keys at rest
- APScheduler (DB jobstore) cho reminders
- Dokploy + GitHub Autodeploy on push to `main`

## 2. Architecture

```
src/
├── main.py                    — entry, register handlers, post_init init_db + scheduler
├── config.py                  — pydantic settings (env vars)
├── ai/
│   ├── llm_router.py          — agentic loop, 7-tier fallback
│   ├── classifier.py          — complexity → start_tier
│   ├── quota_tracker.py       — RPM/RPD per (user_id, model), mark_exhausted on 429
│   ├── providers.py           — call_gemini, call_groq, gemini_web_search (grounding)
│   ├── prompts.py             — SYSTEM_PROMPT (tone + tool gating rules)
│   └── tools.py               — TOOLS list (function declarations)
├── bot/
│   ├── commands.py            — /start, /help, /setkey, /mykey, /status, /pending, /members, /schedules, /notes, /listmodels
│   ├── callbacks.py           — handle_callback dispatcher (inline buttons)
│   ├── handlers/chat.py       — text router (signup / key input / topic input / menu shortcuts / chat)
│   ├── middleware.py          — auth_middleware + _safe_log_text (redact key)
│   ├── tool_dispatcher.py     — execute tool calls
│   ├── drafts.py              — in-memory pending note/schedule drafts + topic hash
│   └── keyboards.py           — TẤT CẢ InlineKeyboard + ReplyKeyboard builders ở đây
├── db/
│   ├── models.py              — Base, UserApproval, UserApiKey, Note, Schedule, MeetingMinute, Conversation
│   │                            (KHÔNG có Task — user dùng bot task riêng)
│   ├── session.py             — async engine + AsyncSessionFactory
│   └── repositories/          — 1 file/model: get/list/create/delete
├── services/                  — note_service, schedule_service (business logic, gọi từ tool_dispatcher)
└── scheduler/
    └── reminder_runner.py     — APScheduler init + reminder dispatch
```

## 3. LLM 7-tier fallback (đừng tự đổi thứ tự khi chưa hỏi user)

```
1. gemini-3.1-flash-lite-preview  (15 RPM / 500 RPD)  ⭐ workhorse
2. gemini-2.5-flash-lite          (10 / 20)
3. gemini-3-flash-preview         (5 / 20)            — reasoning
4. gemini-2.5-flash               (5 / 20)
5. llama-3.3-70b-versatile        (Groq cross-provider)
6. gemini-3.1-pro-preview         (paid only)
7. gemini-2.5-pro                 (paid only)
```

- `quota_tracker.record()` gọi SAU khi call thành công (call fail không tốn quota local).
- `mark_exhausted()` khi API trả 429 → bỏ qua tier đó cả ngày.
- `web_search` grounding tool dùng riêng `gemini-2.5-flash` (fallback `flash-lite`), không nằm trong 7-tier function-calling pipeline.

## 4. Tool gating (CRITICAL — đọc kỹ)

User feedback: bot từng tự tạo note draft cho câu hỏi tin tức → annoying.
Quy tắc trong `src/ai/prompts.py` + `src/ai/tools.py`:

- `save_note` CHỈ khi user nói rõ: "ghi lại / lưu lại / note lại / save".
- `create_schedule` CHỈ khi user nói rõ: "nhắc / hẹn / đặt lịch / reminder".
- `web_search` BẮT BUỘC khi user hỏi tin tức / kết quả thể thao / số liệu real-time.
- KHÔNG bịa số liệu — luôn search trước khi không chắc.

Khi thêm tool mới: phải mô tả rõ "CHỈ gọi khi..." trong description, kèm ví dụ KHÔNG gọi.

## 5. UX patterns đã chốt

- **Persistent reply-keyboard** ở góc dưới: 📅 Lịch / 📝 Note / 🔑 Key / 📊 Status / 👑 Members (admin only) / /start /help. Build qua `keyboards.persistent_menu(is_admin=...)`.
- **Pagination 5/page** cho lịch + members (`PAGE_SIZE = 5` trong `keyboards.py`).
- **Confirm flow trước khi ghi DB** cho note + schedule:
  - Tool `save_note` / `create_schedule` chỉ tạo draft trong memory (`drafts.py`).
  - LLM trả response → chat handler check pending draft → render keyboard ✅/❌.
  - User bấm ✅ → callback insert DB. Bấm ❌ → drop draft.
- **Topic management cho note**:
  - LLM tự gen `suggested_topic` từ context.
  - User pick: gợi ý của LLM / topic có sẵn / nhập topic mới (flow `awaiting_note_topic`).
  - Topic name → uuid5 hash 10 char để fit Telegram callback_data 64-byte limit (`drafts.hash_topic`).
- **Markdown fallback**: dùng `_safe_edit()` trong callbacks.py — user content có `*`/`_` không cân bằng sẽ retry plain-text. Áp dụng cho mọi `edit_message_text` có Markdown.

## 6. Admin features

- `settings.admin_user_id` (env `ADMIN_USER_ID`) — bypass approval.
- `/pending` — list user chờ duyệt.
- `/members` — list user đã duyệt + stats (lịch/note/topic/meeting/message count).
- Revoke = set status=rejected, GIỮ data. Delete = cascade xoá hết.
- TUYỆT ĐỐI không cho xoá admin (`if target_id == settings.admin_user_id: refuse`).

## 7. DB conventions

- Mỗi table có `user_id` index để filter multi-tenant.
- Cascade delete viết tay trong `appr_repo.delete_user_data()` — order: Conversation → Note → Schedule → MeetingMinute → UserApiKey → UserApproval.
- Migration tay: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` trong `init_db()`. KHÔNG add Alembic migration cho cột nhỏ.
- Date grouping cho note: `func.to_char(Note.created_at, "YYYY-MM-DD")` (PostgreSQL only).

## 8. Security checklist

- [ ] Key mã hoá Fernet trước khi save (`keys_repo.set_keys` đã làm).
- [ ] Tin nhắn chứa key xoá ngay sau save (`update.message.delete()`).
- [ ] Log redact key (`middleware._safe_log_text` khi `awaiting_key`).
- [ ] Admin guard cho mọi callback admin-only (`_admin_only(update)`).
- [ ] Không log full LLM response chứa user data sensitive (chỉ log model_used).

## 9. Khi push

```bash
git add -A
git commit -m "feat(vX.Y.Z): tóm tắt ngắn

- bullet 1
- bullet 2"
git push
```

User check Dokploy redeploy log → verify bằng commit hash.

## 10. Khi user báo bug

1. Đọc log/screenshot kỹ — đoán file root cause.
2. Read file đó + file liên quan.
3. Fix + add fallback (try/except) cho user-facing path.
4. Update CHANGELOG dưới ### Fixed.
5. Push, báo commit hash.

## 11. Today's context

- Date hiện tại: lấy từ `<currentDate>` trong system reminder.
- User dùng PowerShell trên Windows — Bash tool work bình thường (Git Bash).
- Python: dùng `py` (Windows launcher), KHÔNG dùng `python` (alias Microsoft Store).
