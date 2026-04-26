"""
Tool definitions — unified schema, converted per-provider in providers.py.
AI gọi tool nào là do AI tự quyết, user chỉ chat tự nhiên.
"""

TOOLS = [
    # ========== WEB SEARCH ==========
    {
        "name": "web_search",
        "description": (
            "Tìm kiếm web real-time qua Google Search grounding. "
            "ĐÂY LÀ TOOL FALLBACK MẶC ĐỊNH cho mọi câu hỏi factual mà bạn KHÔNG CÓ CÂU TRẢ LỜI CHÍNH XÁC, CHẮC CHẮN từ training data. "
            "Quy tắc bắt buộc:\n"
            "1. Trước khi định trả lời 'không biết / không có khả năng / không có chức năng / không có dữ liệu' → DỪNG, gọi web_search.\n"
            "2. Trước khi định bịa số / ngày / tên / sự kiện → DỪNG, gọi web_search.\n"
            "3. Câu hỏi phụ thuộc 'hôm nay / bây giờ / now / mới / cập nhật / hiện tại' → MẶC ĐỊNH search, không cần phân loại.\n"
            "4. Phân vân giữa 'biết chắc' và 'không chắc' → cứ search, an toàn hơn bịa.\n"
            "5. Trả 0 result → nói 'tại hạ search nhưng không tìm thấy thông tin', KHÔNG nói 'không có khả năng tra cứu'.\n"
            "Examples (chỉ illustrative, KHÔNG giới hạn): thời tiết, giao thông, tin tức, giá cả, "
            "thể thao, lịch chiếu, sự kiện, số liệu ngành, đối thủ ra game gì mới, ai vừa thắng giải, v.v."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Câu truy vấn tự nhiên kèm context cần thiết (location/time/scope). "
                        "Nếu user hỏi mơ hồ → tự thêm context phù hợp (vd: city Hà Nội, time hôm nay). "
                        "Vd: 'thời tiết Hà Nội hôm nay', 'doanh thu game mobile VN Q1 2026'."
                    ),
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
            "BẮT BUỘC tham khảo BỐI CẢNH THỜI GIAN ở đầu system prompt để tính 'mai', '2 tiếng nữa', "
            "'thứ 6 tuần sau' chính xác — KHÔNG được tự đoán giờ."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Tên việc/sự kiện"},
                "description": {"type": "string", "description": "Mô tả thêm (không bắt buộc)"},
                "scheduled_at": {
                    "type": "string",
                    "description": (
                        "ISO 8601 BẮT BUỘC kèm `+07:00` (timezone Asia/Ho_Chi_Minh). "
                        "Vd: `2026-04-26T17:30:00+07:00`. "
                        "Tính từ thời điểm hiện tại VN ở system prompt — vd 'now=15:30, +2h' → '17:30'. "
                        "TUYỆT ĐỐI không trả UTC hoặc thiếu timezone offset."
                    ),
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

    # ========== HTML REPORT EXPORT ==========
    {
        "name": "export_html_report",
        "description": (
            "Tạo báo cáo HTML đầy đủ + gửi file qua Telegram. CHỈ gọi khi user nói RÕ: "
            "'báo cáo', 'report', 'xuất report', 'phân tích đầy đủ', 'tổng hợp full', 'export file'. "
            "TUYỆT ĐỐI KHÔNG dùng cho chat thường / câu hỏi nhanh / phân tích ngắn (→ trả lời inline). "
            "TRƯỚC KHI GỌI: tự viết nội dung CHẤT LƯỢNG CAO theo từng section bằng markdown đầy đủ. "
            "TIP: nếu đại hiệp có Claude key, đề nghị pin /model Claude Sonnet 4.6 trước khi yêu cầu report — "
            "Claude viết long-form chất lượng cao nhất."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Tiêu đề báo cáo (vd: 'Phân tích retention JX1 Q1 2026')",
                },
                "summary": {
                    "type": "string",
                    "description": "Tóm tắt 1-2 câu, dùng làm caption khi gửi file Telegram",
                },
                "audience": {
                    "type": "string",
                    "description": "Đối tượng đọc (vd: 'team ops', 'leadership', 'self review'). Optional.",
                },
                "sections": {
                    "type": "array",
                    "description": (
                        "Danh sách section của báo cáo, theo thứ tự render. Ưu tiên cấu trúc: "
                        "📊 Bối cảnh/Data → 🔍 Phân tích → ⚠️ Cảnh báo/Phản biện → 💡 Khuyến nghị vận hành → 📝 Kết luận. "
                        "Mỗi section nội dung markdown đầy đủ (heading, list, table, bold, blockquote, code...) — KHÔNG được rỗng."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string", "description": "Tiêu đề section"},
                            "content_markdown": {
                                "type": "string",
                                "description": "Nội dung markdown của section, đầy đủ insight + số liệu nếu có",
                            },
                        },
                        "required": ["heading", "content_markdown"],
                    },
                    "minItems": 2,
                },
            },
            "required": ["title", "sections"],
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
