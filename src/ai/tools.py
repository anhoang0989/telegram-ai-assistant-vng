"""
Tool definitions — unified schema, converted per-provider in providers.py.
AI gọi tool nào là do AI tự quyết, user chỉ chat tự nhiên.
"""

TOOLS = [
    # ========== NOTES ==========
    {
        "name": "save_note",
        "description": (
            "Lưu ghi chú khi user muốn ghi lại thông tin. "
            "Dùng khi user nói 'ghi lại', 'note lại', 'lưu lại', hoặc liệt kê thông tin cần nhớ."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Tiêu đề ngắn gọn (<80 ký tự)"},
                "content": {"type": "string", "description": "Nội dung chi tiết ghi chú"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags phân loại (vd: kpi, meeting, idea, game, vn)",
                },
            },
            "required": ["title", "content"],
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
            "Tạo lịch/nhắc nhở. Dùng khi user nói 'nhắc tao...', 'đặt lịch...', 'hẹn...'. "
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
            "Lưu meeting minutes sau khi mày đã tóm tắt. "
            "Dùng sau khi user cung cấp nội dung meeting và yêu cầu tổng hợp. "
            "Mày phải tự tóm tắt → action items → recommendations → counterarguments trước, rồi gọi tool này."
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
