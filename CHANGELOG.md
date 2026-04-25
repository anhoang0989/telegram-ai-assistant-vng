# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [Unreleased]

## [0.7.0] - 2026-04-25
### Added — Tasks, Daily digest, Smart/Snooze reminders
- **Bảng `tasks`** — tách action items thành rows riêng có deadline + done flag.
  - Field: `id, user_id, title, description, owner, deadline, done, source_meeting_id`.
  - `save_meeting_summary` giờ **auto-create Task rows** từ mỗi action_item có deadline.
- **Tools mới**:
  - `list_tasks(filter)` — filter: `pending` (default) / `overdue` / `today` / `done` / `all`
  - `mark_task_done(task_id)`
  - `create_offset_reminder(reference_schedule_id, minutes_before, label?)` —
    cho phép user nói "nhắc tao 30 phút trước cuộc họp X"; LLM dùng `list_schedules`
    để tìm reference rồi gọi tool này, tự tính `scheduled_at - offset`.
- **`/tasks` command** — list overdue + pending, mỗi task có button ✅ Done.
- **Snooze reminder** — message reminder kèm 3 nút `⏸ 10p / 30p / 1h`.
  Bấm → tạo Schedule mới offset N phút từ now, fire lại sau.
- **Daily digest 8:00 sáng** — APScheduler cron, gửi tất cả approved user:
  lịch hôm nay + task có deadline hôm nay + task quá hạn. Skip nếu không có gì.
- Admin `/members` stats giờ kèm `task_pending` count.
- Cascade delete user data bao gồm cả `tasks` table.

### Changed
- `MeetingMinute.action_items` (JSONB) vẫn giữ làm raw record, nhưng nguồn truth
  cho UI/listing giờ là bảng `tasks`.

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
