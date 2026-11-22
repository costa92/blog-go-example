"""24 single-step requests. Each has exactly one correct tool, its expected arguments and
three hard neighbours: tools with a similar name or purpose that are always in the catalog.

Argument matchers (see grade.py):
  "X"              exact match after trimming and case folding
  ("dt", "...")    same date and time to the minute, any common format
  ("date", "...")  same date
  ("num", x)       numerically equal, strings like "46" accepted
  ("has", "...")   string containing this text
  ("any", [...])   one of these strings
"""

TODAY = "2026-11-20"
SYSTEM = ("你是一个办公与电商运营助手。今天是 2026-11-20，星期五，时间按北京时间。"
          "用户的请求需要用工具完成时，直接调用最合适的一个工具。")

REQUESTS = [
    ("r01", "取消订单 O-20417，客户说买重了",
     "cancel_order", {"order_id": "O-20417", "reason": ("has", "重")},
     ["create_refund", "get_order_status", "update_order_address"]),
    ("r02", "订单 O-20388 的快递现在到哪了",
     "track_shipment", {"order_id": "O-20388"},
     ["get_order", "get_order_status", "create_shipment"]),
    ("r03", "订单 O-20511 退 128.5 元给客户",
     "create_refund", {"order_id": "O-20511", "amount": ("num", 128.5)},
     ["cancel_order", "get_refund", "list_refunds"]),
    ("r04", "客户 C-3302 最近都下过哪些订单",
     "list_orders", {"customer_id": "C-3302"},
     ["search_orders", "get_customer", "get_order"]),
    ("r05", "发票 INV-7781 客户说没收到，再发一次",
     "resend_invoice", {"invoice_id": "INV-7781"},
     ["create_invoice", "send_email", "get_invoice"]),
    ("r06", "工单 TK-1205 已经处理好了，改成已解决",
     "update_ticket_status", {"ticket_id": "TK-1205", "status": "resolved"},
     ["update_ticket", "add_ticket_comment", "get_ticket"]),
    ("r07", "工单 TK-1219 转给 U-08 处理",
     "assign_ticket", {"ticket_id": "TK-1219", "assignee_id": "U-08"},
     ["update_ticket", "send_notification", "add_ticket_comment"]),
    ("r08", "SK-5530 这个商品还剩多少库存",
     "get_inventory", {"sku": "SK-5530"},
     ["get_product", "list_low_stock", "adjust_inventory"]),
    ("r09", "SK-5530 在上海仓入库 40 件",
     "adjust_inventory", {"sku": "SK-5530", "warehouse": "shanghai", "delta": ("num", 40)},
     ["transfer_inventory", "get_inventory", "create_shipment"]),
    ("r10", "明天下午三点到四点订一下 R-302 会议室开周会",
     "book_meeting_room", {"room_id": "R-302", "start": ("dt", "2026-11-21T15:00"), "end": ("dt", "2026-11-21T16:00")},
     ["create_calendar_event", "list_meeting_rooms", "invite_to_event"]),
    ("r11", "在我日历上加一个 11 月 25 日上午 10 点到 11 点的牙医预约",
     "create_calendar_event", {"title": ("has", "牙"), "start": ("dt", "2026-11-25T10:00"), "end": ("dt", "2026-11-25T11:00")},
     ["book_meeting_room", "create_reminder", "update_calendar_event"]),
    ("r12", "今晚 8 点提醒我交周报",
     "create_reminder", {"text": ("has", "周报"), "remind_at": ("dt", "2026-11-20T20:00")},
     ["create_calendar_event", "send_notification", "list_reminders"]),
    ("r13", "给 13800001111 发条短信：快递已放门卫室",
     "send_sms", {"phone": "13800001111", "content": ("has", "门卫室")},
     ["send_notification", "send_chat_message", "send_email"]),
    ("r14", "给 lisa@example.com 发封邮件，主题「报价单」，正文写「附件是本周报价」",
     "send_email", {"to": "lisa@example.com", "subject": ("has", "报价单"), "body": ("has", "本周报价")},
     ["reply_email", "send_notification", "list_emails"]),
    ("r15", "员工 U-15 的邮箱是多少",
     "get_employee", {"employee_id": "U-15"},
     ["search_employees", "get_manager", "get_customer"]),
    ("r16", "我要请 11 月 24 日到 26 日的年假",
     "create_leave_request", {"leave_type": "annual", "start_date": ("date", "2026-11-24"), "end_date": ("date", "2026-11-26")},
     ["get_leave_balance", "create_calendar_event", "cancel_leave_request"]),
    ("r17", "报销 11 月 18 日的打车费 46 元",
     "submit_expense", {"category": "transport", "amount": ("num", 46), "date": ("date", "2026-11-18")},
     ["list_expenses", "get_expense", "create_refund"]),
    ("r18", "北京明天会下雨吗",
     "get_weather_forecast", {"city": ("any", ["北京", "北京市"]), "date": ("date", "2026-11-21")},
     ["get_current_weather", "get_air_quality", "search_flights"]),
    ("r19", "查一下 CA1831 明天的航班状态",
     "get_flight_status", {"flight_no": "CA1831", "date": ("date", "2026-11-21")},
     ["search_flights", "book_flight", "list_calendar_events"]),
    ("r20", "100 美元换成人民币是多少钱",
     "convert_currency", {"amount": ("num", 100), "from_currency": "USD", "to_currency": "CNY"},
     ["get_exchange_rate", "create_refund", "get_shipping_rates"]),
    ("r21", "把 payment-api 回滚到上一个版本",
     "rollback_deployment", {"service": "payment-api"},
     ["deploy_service", "restart_service", "list_deployments"]),
    ("r22", "告警 AL-9031 先静默 2 小时",
     "silence_alert", {"alert_id": "AL-9031", "duration_minutes": ("num", 120)},
     ["ack_alert", "resolve_alert", "list_alerts"]),
    ("r23", "优惠券 SAVE20 现在还能用吗",
     "validate_coupon", {"code": "SAVE20"},
     ["get_coupon", "disable_coupon", "create_coupon"]),
    ("r24", "把共享盘里的「Q4预算.xlsx」分享给 U-07，只读",
     "share_file", {"path": ("has", "Q4预算.xlsx"), "user_id": "U-07", "permission": "view"},
     ["get_file_info", "send_notification", "move_file"]),
]
