# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [Unreleased]

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
