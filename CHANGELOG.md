# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [Unreleased]

## [0.9.0] - 2026-04-25
### Added — Personal Knowledge Base (text, BYO via chat)
- **Bảng `knowledge_entries`** mới: id, user_id (indexed), category (indexed),
  title, content, source, tags, timestamps. Auto-create qua `Base.metadata.create_all`.
- **Categories**: `game_data | design | user_behavior | market | meeting_log | other`.
  Helper `normalize_category()` chống typo / case mismatch.
- **Repo `knowledge.py`**: create / search (ILIKE title+content) / list_by_category /
  list_categories (group count) / get / delete / delete_all_for_user.
- **3 tools mới** trong `tools.py`:
  - `save_knowledge(category, title, content, tags?)` — gating CỨNG: chỉ save
    khi user nói rõ "lưu data/knowledge/design/insight" hoặc paste >200 chars
    + yêu cầu lưu. Phân biệt rõ với `save_note` (idea/todo) trong description.
  - `search_knowledge(query, category?, limit=5)` — BẮT BUỘC gọi trước khi
    trả lời câu hỏi về data/design/behavior/market RIÊNG của user.
  - `list_knowledge(category?, limit=10)` — kèm `categories_overview` để LLM
    biết cấu trúc kho.
- **SYSTEM_PROMPT** thêm section "KHO TRI THỨC CÁ NHÂN" — phân biệt note vs
  knowledge, ví dụ NÊN/KHÔNG GỌI cho cả 2.
- **Cascade delete**: `delete_user_data()` xoá thêm `KnowledgeEntry`.
- **Stats admin** (`user_stats`): thêm `knowledge_count`. Member detail view
  hiển thị "Knowledge: N".
- **Help text** thêm 2 ví dụ chat (save data + phân tích).

### Notes
- v0.9.0 KHÔNG có draft/confirm flow cho knowledge — tool save trực tiếp
  insert DB. Tin cậy SYSTEM_PROMPT + tool description để tránh over-trigger.
  Nếu thấy bot tự lưu sai → siết description thêm hoặc thêm confirm flow ở v0.9.1.
- Search dùng ILIKE, đủ cho ~vài trăm entries. Upgrade tsvector / pgvector
  khi corpus lớn (>1000 entries) hoặc cần semantic search.

## [0.8.1] - 2026-04-25
### Added — Model selector (`/model`)
- **Lệnh `/model`** — keyboard cho user chọn model AI:
  - 🤖 *Auto* (mặc định) — smart 9-tier fallback như cũ
  - Pin model cụ thể (4 Gemini free + 1 Groq + 2 Gemini Pro paid + 2 Claude paid)
  - Marker `•` cạnh option đang chọn
- **Cột `preferred_model`** trong `user_approvals` (default `'auto'`,
  String(80)). Migration `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- **Repo helpers** `get_preferred_model` / `set_preferred_model` trong
  `approvals.py`.
- **Logic pin trong `llm_router`** — nếu `preferred_model != 'auto'`:
  - Gọi đúng model đó, KHÔNG fallback sang tier khác (kể cả cùng provider)
  - Hết quota / thiếu key → trả message yêu cầu user đổi model qua `/model`
  - Pinned model_id phải nằm trong whitelist `tier1..tier9` để chống abuse
- Bot menu thêm entry "Chọn model AI", help text mention `/model`.

### Notes
- Pin = pin cứng. User chọn để test chất lượng từng model phải tự switch
  về Auto khi muốn fallback. Đây là chủ ý design (đại hiệp đã chốt).
- Callback `noop` (separator buttons trong picker) được handle silent.

## [0.8.0] - 2026-04-25
### Added — Claude (Anthropic) provider + 3-key BYOK
- **Claude provider** trong `src/ai/providers.py` (`call_claude`) dùng
  `anthropic` SDK async. Convert message format sang Anthropic schema
  (text/tool_use blocks, tool_result trong user turn). Cache `AsyncAnthropic`
  client theo api_key giống Gemini/Groq.
- **2 tier mới** ưu tiên cuối cùng (paid only, chỉ dùng khi user nhập key):
  - Tier 8: `claude-haiku-4-5-20251001`
  - Tier 9: `claude-sonnet-4-6`
- **`/setkey` hỗ trợ 3 provider** — keyboard có thêm nút "🔑 Claude (paid)".
  Link console: https://console.anthropic.com/settings/keys
- **Cột `claude_key_encrypted`** trong `user_api_keys` (Fernet). Migration
  idempotent `ALTER TABLE ... IF NOT EXISTS` trong `init_db()`.
- **`get_decrypted_keys` trả 3 keys** `(gemini, groq, claude)`. Mọi call site
  đã update unpacking.
- **`/mykey` hiển thị 3 keys** với label rõ "bắt buộc / optional".
- **`chat()` nhận `claude_key`** + `keys: dict` — tier với provider thiếu
  key được skip tự động trong fallback loop.

### Changed
- **Gemini là key BẮT BUỘC** (workhorse free tier). Groq + Claude optional.
  Trước: yêu cầu cả Gemini + Groq mới cho chat.
- **Help text + bot menu desc** cập nhật mention cả 3 provider.
- **Post-init log** liệt kê 9 tier (trước 7).

## [0.7.1] - 2026-04-25
### Removed — Bỏ Task entity
- User đã có bot task riêng → bỏ feature `tasks` cho gọn:
  - Xoá model `Task` + repo `tasks.py`
  - Xoá tools `list_tasks`, `mark_task_done`
  - Xoá `/tasks` command + `td:` callback + `task_done_keyboard`
  - `save_meeting_summary` không còn auto-create Task rows
    (action_items vẫn lưu trong `MeetingMinute.action_items` JSONB như cũ)
  - Daily digest chỉ liệt kê lịch hôm nay, không còn section task

### Fixed
- Suppress pip root-user warning trong Docker build (`--root-user-action=ignore`)

## [0.7.0] - 2026-04-25
### Added — Daily digest, Smart/Snooze reminders
- **`create_offset_reminder` tool** — cho phép user nói "nhắc tao 30 phút trước
  cuộc họp X"; LLM dùng `list_schedules` để tìm reference rồi gọi tool này,
  tự tính `scheduled_at - offset`.
- **Snooze reminder** — message reminder kèm 3 nút `⏸ 10p / 30p / 1h`.
  Bấm → tạo Schedule mới offset N phút từ now, fire lại sau.
- **Daily digest 8:00 sáng** — APScheduler cron, gửi tất cả approved user
  tóm tắt lịch hôm nay. Skip nếu không có lịch.

## [0.6.0] - 2026-04-25
### Added — Web search (Gemini grounding) + tighter tool gating
- **`web_search` tool** — dùng Gemini `GoogleSearch` grounding builtin (không cần API thứ 3).
  LLM tự gọi khi user hỏi tin tức / kết quả thể thao / số liệu real-time.
  Trả về text tổng hợp + nguồn (top 5 URL).
- Default search model: `gemini-2.5-flash`, fallback `gemini-2.5-flash-lite` khi quota hết.

### Fixed
- **Tool over-trigger**: trước đây bot tạo note draft cho cả câu hỏi tra cứu
  (vd "kết quả U17 hôm qua?" → tạo note rồi trả "không truy cập được").
  Siết SYSTEM_PROMPT + tool descriptions:
  - `save_note` CHỈ khi user nói rõ "ghi lại / lưu lại / note lại"
  - `create_schedule` CHỈ khi user nói rõ "nhắc / hẹn / đặt lịch"
  - Câu hỏi tra cứu → bắt buộc `web_search` thay vì bịa hoặc note
- `_safe_edit()` helper trong callbacks.py — fallback plain-text khi user
  content có `*`/`_` không cân bằng (Markdown parse error)

## [0.5.0] - 2026-04-25
### Added — Admin members management
- `/members` — list user đã duyệt (paginate 5/page)
- View detail member: stats count (lịch sắp tới, note, topic, meeting, message)
- **Revoke** (set status=rejected, giữ data) — user không chat được
- **Xoá user + data** (cascade: approval + keys + notes + schedules + meetings + conversations)
  → confirm 2 bước, không thể xoá admin
- Persistent menu của admin có thêm nút 👑 Members
- `/listmodels` — admin tra tên Gemini model API thực tế

### Fixed
- Gemini API model IDs chính xác từ `client.models.list()`:
  `gemini-3.1-flash-lite-preview` (workhorse), `gemini-3-flash-preview`,
  `gemini-3.1-pro-preview`. Tên cũ `gemini-3-flash-lite` không tồn tại.
- Markdown parse fallback khi LLM trả response có `*`/`_` không cân bằng

## [0.4.0] - 2026-04-25
### Added — UX & CRUD cho lịch + note
- **Persistent menu** ở góc dưới: 📅 Lịch / 📝 Note / 🔑 Key / 📊 Status
- **Confirm flow trước khi tạo**: tool `save_note` / `create_schedule` không insert ngay,
  tạo draft trong memory → user duyệt qua nút ✅/❌ rồi mới ghi DB
- **Note có chủ đề (topic)**: thêm cột `Note.topic` (auto-migrate ALTER TABLE),
  LLM tự suy luận topic từ context, user pick từ topic gợi ý / topic có sẵn / nhập mới
- `/schedules` — list lịch sắp tới, paginate 5/page, click view → xoá
- `/notes` — xem theo chủ đề hoặc theo ngày, xoá từng note hoặc xoá cả topic
- New module `src/bot/keyboards.py` — gom tất cả keyboard builders
- New module `src/bot/drafts.py` — in-memory draft store + topic hash mapping

### Changed — Performance & fallback
- **Bỏ Pro khỏi start tier** — free tier Gemini Pro = 0, classifier complex giờ start tại
  `gemini-3-flash` (tier 2) thay vì Pro (tránh fail call đầu tiên)
- **7-tier fallback** mới (workhorse → backup → cross-provider → paid):
  1. gemini-3-flash-lite (15 RPM / 500 RPD) ⭐ workhorse
  2. gemini-2.5-flash-lite (10/20)
  3. gemini-3-flash (5/20) — reasoning
  4. gemini-2.5-flash (5/20)
  5. llama-3.3-70b (Groq cross-provider)
  6. gemini-3-pro (paid only)
  7. gemini-2.5-pro (paid only)
- **Cache LLM clients** theo api_key (`_GEMINI_CLIENTS`, `_GROQ_CLIENTS`) — bỏ tạo
  Client mới mỗi request, giảm latency 200-500ms/call
- **Move `quota_tracker.record()` xuống sau call thành công** — call fail không
  còn tốn quota counter local
- **`mark_exhausted()` khi API trả 429** — đánh dấu model hết quota cho session
  hiện tại, bỏ qua hẳn ở các call sau thay vì retry 1-by-1
- **Quota limits đồng bộ Google AI Studio (2026-04)** — số liệu thực tế thay vì ước lượng
- **Groq tool hallucination handling**: khi llama gọi tool không có trong list
  (vd: `brave_search`) → 400 → tự retry không kèm tools thay vì fail tier

### Security
- **Redact API key trong log** — middleware không còn log plaintext khi user
  paste key qua flow `/setkey`. Log thay bằng `<redacted API key, len=N>`
- Tool message chứa key vẫn bị xoá ngay sau khi save (như cũ)

### Fixed
- Tier fallback giờ thực sự bắt đầu từ flash-lite (trước đây complex query
  nhảy thẳng Pro → free=0 → fail → groq → hallucinate → "all exhausted" mà
  chưa từng thử flash-lite)

## [0.3.0] - 2026-04-24
### Added
- Admin approval workflow + button-based setkey
- "Đại hiệp / tại hạ" tone
- VNG Domain (mã nhân viên) thay cho email

## [0.2.0] - 2026-04-24
### Changed
- **Chuyển sang Gemini + Groq** (bỏ Claude) để tận dụng free tier
- **Multi-tier LLM routing** với classifier + quota-based fallback:
  - Tier 0: Gemini 2.5 Flash Lite (simple queries)
  - Tier 1: Gemini 2.5 Flash (medium)
  - Tier 2: Gemini 2.5 Pro (complex, vd: meeting minutes)
  - Tier 3: Groq Llama 3.3 70B (fallback cuối)
- **Chat-only UX** — bỏ toàn bộ commands trừ `/start`, `/help`, `/status`
- **Agentic loop** — AI tự gọi tools đa bước, bot chỉ là ống dẫn
- Tool definitions mở rộng: thêm `list_notes`, `list_schedules`, `delete_schedule`, `save_meeting_summary`, `list_meetings`
- `/status` command mới — xem quota RPM/RPD realtime của từng tier

### Removed
- `anthropic` SDK
- Command handlers: `/note`, `/notes`, `/search`, `/export`, `/schedule`, `/schedules`, `/delschedule`, `/meeting`, `/meetings`
- `meeting_service.py` (AI tự tóm tắt qua tool)
- Menu keyboard (không cần nữa)

## [0.1.0] - 2026-04-24
### Added
- Khởi tạo project — bot skeleton, auth, Docker, Postgres, Alembic, APScheduler
- Modules: notes, schedule, meeting minutes
- Tests unit + integration
