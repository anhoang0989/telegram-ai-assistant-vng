"""
Tool definitions — unified schema, converted per-provider in providers.py.
AI gọi tool nào là do AI tự quyết, user chỉ chat tự nhiên.
"""

TOOLS = [
    # ========== WEB SEARCH ==========
    {
        "name": "web_search",
        "description": (
            "Tìm kiếm thông tin real-time qua Google Search grounding. "
            "BẮT BUỘC dùng khi user hỏi: tin tức, sự kiện, kết quả thể thao, giá cả, "
            "số liệu mới, báo cáo ngành, hoặc bất kỳ thông tin nào có thể đã thay đổi sau training. "
            "KHÔNG bịa khi không chắc — luôn search trước rồi trả lời."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu truy vấn tìm kiếm, viết rõ ràng tự nhiên (vd: 'kết quả U17 Việt Nam vs Malaysia 24/04/2026')",
                },
            },
            "required": ["query"],
        },
    },

    # ========== NOTES ==========
    {
        "name": "save_note",
        "description": (
            "Lưu ghi chú vào DB cá nhân của user. "
            "CHỈ gọi khi user nói RÕ RÀNG muốn ghi: 'ghi lại', 'note lại', 'lưu lại', 'save cái này'. "
            "TUYỆT ĐỐI KHÔNG gọi cho câu hỏi tra cứu, chat, hỏi tin tức, hỏi ý kiến. "
            "Phải tự suy luận 1 'topic' phù hợp từ context hội thoại để nhóm note "
            "(vd: 'Họp QC 25/04', 'Idea LiveOps', 'Research Genshin'). "
            "Topic là gợi ý — user vẫn có quyền chọn topic khác qua nút."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Tiêu đề ngắn gọn của note (<80 ký tự)"},
                "content": {"type": "string", "description": "Nội dung chi tiết ghi chú"},
                "topic": {
                    "type": "string",
                    "description": "Chủ đề gợi ý để nhóm note, suy ra từ context (vd: 'Họp QC 25/04', 'Idea LiveOps')",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags phân loại (vd: kpi, meeting, idea, game, vn)",
                },
            },
            "required": ["title", "content", "topic"],
        },
    },
    {
        "name": "search_notes",
        "description": "Tìm kiếm ghi chú đã lưu theo từ khoá. Dùng khi user hỏi 'tao có note gì về...', 'tìm note...'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Từ khoá tìm kiếm"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_notes",
        "description": "Liệt kê ghi chú gần đây. Dùng khi user hỏi 'có note gì?', 'xem tất cả notes', 'notes gần đây'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Số lượng note muốn xem (mặc định 10)"},
            },
        },
    },

    # ========== SCHEDULES ==========
    {
        "name": "create_schedule",
        "description": (
            "Tạo lịch/nhắc nhở. CHỈ gọi khi user nói RÕ RÀNG: 'nhắc tao...', 'đặt lịch...', "
            "'hẹn...', 'reminder...', 'set lịch...'. KHÔNG tự đoán từ chat thông thường. "
            "Parse ngôn ngữ tự nhiên để xác định thời gian (vd: '3h chiều mai', 'thứ 6 tuần sau 9h')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Tên việc/sự kiện"},
                "description": {"type": "string", "description": "Mô tả thêm (không bắt buộc)"},
                "scheduled_at": {
                    "type": "string",
                    "description": "Thời gian ISO 8601, timezone Asia/Ho_Chi_Minh (vd: 2026-04-25T15:00:00+07:00)",
                },
                "recurrence": {
                    "type": "string",
                    "enum": ["none", "daily", "weekly"],
                    "description": "Lặp lại: none (1 lần), daily, weekly",
                },
            },
            "required": ["title", "scheduled_at"],
        },
    },
    {
        "name": "list_schedules",
        "description": "Liệt kê lịch sắp tới. Dùng khi user hỏi 'lịch tuần này', 'có gì sắp tới?', 'xem lịch'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "description": "Số ngày muốn xem (mặc định 7)"},
            },
        },
    },
    {
        "name": "create_offset_reminder",
        "description": (
            "Tạo reminder OFFSET trước/sau một lịch đã có. "
            "Dùng khi user nói 'nhắc tao 30 phút trước cuộc họp X', '15p trước lịch Y'. "
            "Workflow: trước tiên gọi list_schedules để tìm reference_schedule_id, "
            "sau đó gọi tool này với offset (mặc định trước = âm). "
            "Tool tự tính scheduled_at = reference.scheduled_at - offset_minutes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference_schedule_id": {
                    "type": "integer",
                    "description": "ID của lịch gốc (lấy từ list_schedules)",
                },
                "minutes_before": {
                    "type": "integer",
                    "description": "Số phút TRƯỚC reference (vd: 30 = nhắc trước 30 phút). Dương = trước, âm = sau.",
                },
                "label": {
                    "type": "string",
                    "description": "Mô tả ngắn (vd: 'Chuẩn bị slide họp QC'). Optional.",
                },
            },
            "required": ["reference_schedule_id", "minutes_before"],
        },
    },
    {
        "name": "delete_schedule",
        "description": "Xoá lịch đã đặt. Dùng khi user nói 'xoá lịch...', 'huỷ reminder...'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "schedule_id": {"type": "integer", "description": "ID của lịch cần xoá"},
            },
            "required": ["schedule_id"],
        },
    },

    # ========== MEETINGS ==========
    {
        "name": "save_meeting_summary",
        "description": (
            "Lưu meeting minutes sau khi đã tóm tắt. "
            "Dùng sau khi user cung cấp nội dung meeting và yêu cầu tổng hợp. "
            "Tự tóm tắt → action items → recommendations → counterarguments trước, rồi gọi tool này. "
            "Mỗi action_item nên có owner + deadline (ISO 8601) nếu có thể parse từ context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Tên meeting"},
                "raw_input": {"type": "string", "description": "Nội dung gốc user cung cấp"},
                "summary": {"type": "string", "description": "Tóm tắt chính của meeting"},
                "action_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string"},
                            "owner": {"type": "string"},
                            "deadline": {"type": "string"},
                        },
                    },
                    "description": "Danh sách action items",
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Khuyến nghị của mày",
                },
                "counterarguments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Điểm phản biện, rủi ro mày thấy",
                },
            },
            "required": ["title", "raw_input", "summary"],
        },
    },
    {
        "name": "list_meetings",
        "description": "Liệt kê meeting minutes đã lưu. Dùng khi user hỏi 'meeting nào đã họp?', 'xem lại meeting...'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Số lượng meeting muốn xem (mặc định 10)"},
            },
        },
    },
]
