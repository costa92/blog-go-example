"""100 tools of an office / e-commerce assistant, each with three description levels.

Every tool is (name, short, detail, params, required). params maps a parameter name to
(type, description, enum). render(tool, level) turns it into an Ollama tool definition:

  name  - no tool description, parameters carry only their type
  short - one-line tool description, parameters carry only their type
  full  - short + detail, parameter descriptions with formats, and enums
  enum  - short, plus enums on the parameters that have them, nothing else

The backend contract (types, required, enums) is the full schema whatever the model saw;
grade.py validates arguments against it.
"""

S, N, I = "string", "number", "integer"
DT = "时间，格式 YYYY-MM-DDTHH:MM，北京时间"
DATE = "日期，格式 YYYY-MM-DD"


def p(t, d, enum=None):
    return (t, d, enum)


TOOLS = [
    # orders
    ("get_order", "查询订单详情", "返回商品、金额、收货地址和下单时间。只查订单本身；物流轨迹用 track_shipment，退款用 get_refund。",
     {"order_id": p(S, "订单号，形如 O-00000")}, ["order_id"]),
    ("get_order_status", "查询订单的处理状态", "只返回待付款、待发货、已发货、已完成、已取消这几种状态之一，不含物流轨迹。",
     {"order_id": p(S, "订单号，形如 O-00000")}, ["order_id"]),
    ("list_orders", "列出某个客户的订单", "按下单时间倒序返回该客户的订单列表，可按状态过滤。",
     {"customer_id": p(S, "客户编号，形如 C-0000"),
      "status": p(S, "只返回这个状态的订单，不传返回全部", ["pending", "shipped", "done", "cancelled"])}, ["customer_id"]),
    ("search_orders", "按关键词搜索订单", "在商品名和收货人姓名里做模糊搜索，适合不知道订单号的场景。",
     {"keyword": p(S, "搜索关键词")}, ["keyword"]),
    ("cancel_order", "取消订单", "只能取消未发货的订单，取消后库存自动回补。已付款的订单取消后需要另外调用 create_refund 退款。",
     {"order_id": p(S, "订单号，形如 O-00000"), "reason": p(S, "取消原因，会展示给客服")}, ["order_id", "reason"]),
    ("update_order_address", "修改订单收货地址", "只能修改未发货订单的地址。",
     {"order_id": p(S, "订单号，形如 O-00000"), "address": p(S, "完整的新收货地址")}, ["order_id", "address"]),
    ("create_order", "代客户下单", "为客户创建新订单，库存不足时返回错误。",
     {"customer_id": p(S, "客户编号，形如 C-0000"), "sku": p(S, "商品 SKU，形如 SK-0000"),
      "quantity": p(I, "购买数量，正整数")}, ["customer_id", "sku", "quantity"]),
    # shipments
    ("track_shipment", "查询订单的物流轨迹", "返回快递公司、运单号和每一个物流节点，用于回答「快递到哪了」。",
     {"order_id": p(S, "订单号，形如 O-00000")}, ["order_id"]),
    ("create_shipment", "为订单创建发货单", "仓库打包后调用，生成运单号。",
     {"order_id": p(S, "订单号，形如 O-00000"), "carrier": p(S, "快递公司", ["sf", "jd", "zto", "yto"])}, ["order_id", "carrier"]),
    ("get_shipping_rates", "查询运费报价", "按重量和目的城市返回各快递公司的运费。",
     {"city": p(S, "目的城市，中文名"), "weight_kg": p(N, "包裹重量，单位千克")}, ["city", "weight_kg"]),
    ("schedule_pickup", "预约快递上门取件", "用于退货或寄件，返回预约单号。",
     {"address": p(S, "取件地址"), "pickup_time": p(S, "上门" + DT)}, ["address", "pickup_time"]),
    # refunds
    ("create_refund", "为订单发起退款", "按指定金额原路退回，金额不能超过实付金额。不会取消订单；要取消订单用 cancel_order。",
     {"order_id": p(S, "订单号，形如 O-00000"), "amount": p(N, "退款金额，单位元，数字")}, ["order_id", "amount"]),
    ("get_refund", "查询退款进度", "返回退款单的金额、状态和到账时间。",
     {"refund_id": p(S, "退款单号，形如 RF-0000")}, ["refund_id"]),
    ("list_refunds", "列出订单的退款记录", "一个订单可能有多笔部分退款。",
     {"order_id": p(S, "订单号，形如 O-00000")}, ["order_id"]),
    ("cancel_refund", "撤销尚未到账的退款", "只有处理中的退款可以撤销。",
     {"refund_id": p(S, "退款单号，形如 RF-0000")}, ["refund_id"]),
    # invoices
    ("create_invoice", "为订单开具发票", "为没有开过票的订单开新发票。已经开过的发票要重新发送，用 resend_invoice。",
     {"order_id": p(S, "订单号，形如 O-00000"), "title": p(S, "发票抬头")}, ["order_id", "title"]),
    ("get_invoice", "查询发票详情", "返回抬头、金额、开票时间和状态。",
     {"invoice_id": p(S, "发票号，形如 INV-0000")}, ["invoice_id"]),
    ("resend_invoice", "重新发送已开具的发票", "把已有发票的 PDF 再次发到开票时登记的邮箱，不会重新开票。",
     {"invoice_id": p(S, "发票号，形如 INV-0000")}, ["invoice_id"]),
    ("void_invoice", "作废发票", "作废后不可恢复，需要重新开票。",
     {"invoice_id": p(S, "发票号，形如 INV-0000"), "reason": p(S, "作废原因")}, ["invoice_id", "reason"]),
    ("list_invoices", "列出客户的发票", "按开票时间倒序。",
     {"customer_id": p(S, "客户编号，形如 C-0000")}, ["customer_id"]),
    # customers
    ("get_customer", "查询客户资料", "返回客户的名称、联系人、电话和会员等级。客户的订单用 list_orders。",
     {"customer_id": p(S, "客户编号，形如 C-0000")}, ["customer_id"]),
    ("search_customers", "按名称或电话搜索客户", "模糊匹配，返回客户编号列表。",
     {"keyword": p(S, "客户名称或电话")}, ["keyword"]),
    ("update_customer", "修改客户资料", "修改客户的联系人或电话。",
     {"customer_id": p(S, "客户编号，形如 C-0000"), "contact": p(S, "联系人姓名"), "phone": p(S, "联系电话")}, ["customer_id"]),
    ("create_customer", "新建客户", "录入新客户，返回客户编号。",
     {"name": p(S, "客户名称"), "phone": p(S, "联系电话")}, ["name", "phone"]),
    # tickets
    ("create_ticket", "新建客服工单", "记录客户问题，返回工单号。",
     {"title": p(S, "工单标题"), "customer_id": p(S, "客户编号，形如 C-0000")}, ["title"]),
    ("get_ticket", "查询工单详情", "返回工单的标题、状态、负责人和全部评论。",
     {"ticket_id": p(S, "工单号，形如 TK-0000")}, ["ticket_id"]),
    ("search_tickets", "按关键词搜索工单", "在工单标题里模糊搜索。",
     {"query": p(S, "搜索关键词")}, ["query"]),
    ("update_ticket", "修改工单的标题或描述", "只改文字内容，不能改状态和负责人。",
     {"ticket_id": p(S, "工单号，形如 TK-0000"), "title": p(S, "新标题"), "description": p(S, "新描述")}, ["ticket_id"]),
    ("update_ticket_status", "修改工单状态", "把工单改成待处理、处理中、已解决或已关闭。",
     {"ticket_id": p(S, "工单号，形如 TK-0000"),
      "status": p(S, "新状态：open 待处理，pending 处理中，resolved 已解决，closed 已关闭", ["open", "pending", "resolved", "closed"])},
     ["ticket_id", "status"]),
    ("assign_ticket", "把工单转给别人处理", "修改工单负责人，原负责人会收到通知。",
     {"ticket_id": p(S, "工单号，形如 TK-0000"), "assignee_id": p(S, "新负责人的员工编号，形如 U-00")}, ["ticket_id", "assignee_id"]),
    ("add_ticket_comment", "给工单添加评论", "评论对客户不可见。",
     {"ticket_id": p(S, "工单号，形如 TK-0000"), "comment": p(S, "评论内容")}, ["ticket_id", "comment"]),
    # products and inventory
    ("get_product", "查询商品信息", "返回商品名称、规格和售价，不含库存。库存用 get_inventory。",
     {"sku": p(S, "商品 SKU，形如 SK-0000")}, ["sku"]),
    ("search_products", "按名称搜索商品", "模糊匹配商品名，返回 SKU 列表。",
     {"keyword": p(S, "商品名关键词")}, ["keyword"]),
    ("update_product_price", "修改商品售价", "立即生效。",
     {"sku": p(S, "商品 SKU，形如 SK-0000"), "price": p(N, "新售价，单位元")}, ["sku", "price"]),
    ("get_inventory", "查询商品库存", "返回各仓库的可用库存数量。",
     {"sku": p(S, "商品 SKU，形如 SK-0000")}, ["sku"]),
    ("adjust_inventory", "增减某个仓库的库存", "入库传正数，出库或盘亏传负数。仓库之间调拨用 transfer_inventory。",
     {"sku": p(S, "商品 SKU，形如 SK-0000"),
      "warehouse": p(S, "仓库：beijing 北京仓，shanghai 上海仓，guangzhou 广州仓", ["beijing", "shanghai", "guangzhou"]),
      "delta": p(I, "变化量，入库为正、出库为负")}, ["sku", "warehouse", "delta"]),
    ("transfer_inventory", "在仓库之间调拨库存", "从一个仓库调到另一个仓库。",
     {"sku": p(S, "商品 SKU，形如 SK-0000"), "from_warehouse": p(S, "调出仓库", ["beijing", "shanghai", "guangzhou"]),
      "to_warehouse": p(S, "调入仓库", ["beijing", "shanghai", "guangzhou"]), "quantity": p(I, "调拨数量")},
     ["sku", "from_warehouse", "to_warehouse", "quantity"]),
    ("list_low_stock", "列出库存不足的商品", "返回可用库存低于阈值的 SKU。",
     {"threshold": p(I, "库存阈值，默认 10")}, []),
    # coupons
    ("validate_coupon", "检查优惠券能不能用", "返回优惠券是否有效、是否过期、剩余次数。",
     {"code": p(S, "优惠券码，大写字母和数字")}, ["code"]),
    ("get_coupon", "查询优惠券的规则", "返回面额、门槛和适用商品，不判断当前是否可用。",
     {"code": p(S, "优惠券码，大写字母和数字")}, ["code"]),
    ("create_coupon", "创建优惠券", "生成新的优惠券码。",
     {"amount": p(N, "面额，单位元"), "min_spend": p(N, "使用门槛，单位元")}, ["amount"]),
    ("disable_coupon", "停用优惠券", "停用后立即失效。",
     {"code": p(S, "优惠券码，大写字母和数字")}, ["code"]),
    # calendar
    ("create_calendar_event", "在我的日历上新建日程", "只写入个人日历，不预订会议室。订会议室用 book_meeting_room。",
     {"title": p(S, "日程标题"), "start": p(S, "开始" + DT), "end": p(S, "结束" + DT)}, ["title", "start", "end"]),
    ("update_calendar_event", "修改已有日程", "修改日程的时间或标题。",
     {"event_id": p(S, "日程编号，形如 EV-0000"), "start": p(S, "新的开始" + DT), "end": p(S, "新的结束" + DT)}, ["event_id"]),
    ("delete_calendar_event", "删除日程", "删除后参与人会收到取消通知。",
     {"event_id": p(S, "日程编号，形如 EV-0000")}, ["event_id"]),
    ("list_calendar_events", "列出某天的日程", "返回当天全部日程。",
     {"date": p(S, DATE)}, ["date"]),
    ("find_free_slots", "查找多人的共同空闲时间", "返回指定日期内所有人都空闲的时间段。",
     {"user_ids": p(S, "员工编号，逗号分隔"), "date": p(S, DATE)}, ["user_ids", "date"]),
    ("invite_to_event", "邀请同事参加日程", "给已有日程添加参与人。",
     {"event_id": p(S, "日程编号，形如 EV-0000"), "user_id": p(S, "员工编号，形如 U-00")}, ["event_id", "user_id"]),
    # meeting rooms
    ("list_meeting_rooms", "列出空闲的会议室", "返回指定时间段内空闲的会议室和容量。",
     {"start": p(S, "开始" + DT), "end": p(S, "结束" + DT)}, ["start", "end"]),
    ("book_meeting_room", "预订会议室", "按会议室编号预订一个时间段，不会写入个人日历。",
     {"room_id": p(S, "会议室编号，形如 R-000"), "start": p(S, "开始" + DT), "end": p(S, "结束" + DT),
      "subject": p(S, "会议主题")}, ["room_id", "start", "end"]),
    ("cancel_room_booking", "取消会议室预订", "释放已预订的会议室。",
     {"booking_id": p(S, "预订单号，形如 BK-0000")}, ["booking_id"]),
    # messaging
    ("send_email", "发送邮件", "发给任意邮箱地址，支持主题和正文。",
     {"to": p(S, "收件人邮箱"), "subject": p(S, "邮件主题"), "body": p(S, "邮件正文")}, ["to", "subject", "body"]),
    ("send_sms", "发送短信", "发到中国大陆手机号，内容不超过 70 字。",
     {"phone": p(S, "11 位手机号"), "content": p(S, "短信内容")}, ["phone", "content"]),
    ("send_notification", "给员工发 App 内通知", "只能发给公司员工，按员工编号。",
     {"user_id": p(S, "员工编号，形如 U-00"), "message": p(S, "通知内容")}, ["user_id", "message"]),
    ("send_chat_message", "在群聊里发消息", "发到指定的工作群。",
     {"channel": p(S, "群名称"), "text": p(S, "消息内容")}, ["channel", "text"]),
    ("list_emails", "列出收件箱里的邮件", "按时间倒序，可按发件人过滤。",
     {"sender": p(S, "发件人邮箱")}, []),
    ("reply_email", "回复一封邮件", "按邮件编号回复原发件人。",
     {"email_id": p(S, "邮件编号，形如 M-0000"), "body": p(S, "回复正文")}, ["email_id", "body"]),
    # reminders
    ("create_reminder", "设置一个到点提醒", "到时间后给我推送一条提醒，不占用日历时间。",
     {"text": p(S, "提醒内容"), "remind_at": p(S, "提醒" + DT)}, ["text", "remind_at"]),
    ("list_reminders", "列出我的提醒", "返回尚未触发的提醒。", {}, []),
    ("delete_reminder", "删除提醒", "按提醒编号删除。",
     {"reminder_id": p(S, "提醒编号，形如 RM-0000")}, ["reminder_id"]),
    # employees
    ("get_employee", "查询员工资料", "按员工编号返回姓名、邮箱、电话和部门。",
     {"employee_id": p(S, "员工编号，形如 U-00")}, ["employee_id"]),
    ("search_employees", "按姓名搜索员工", "模糊匹配姓名，返回员工编号列表。",
     {"name": p(S, "员工姓名")}, ["name"]),
    ("list_team_members", "列出部门成员", "返回部门下的全部员工。",
     {"department": p(S, "部门名称")}, ["department"]),
    ("get_manager", "查询员工的直属上级", "返回上级的员工编号和姓名。",
     {"employee_id": p(S, "员工编号，形如 U-00")}, ["employee_id"]),
    ("update_employee_phone", "修改员工的联系电话", "只能修改本人或下属的电话。",
     {"employee_id": p(S, "员工编号，形如 U-00"), "phone": p(S, "新电话")}, ["employee_id", "phone"]),
    # leave
    ("create_leave_request", "提交请假申请", "提交后进入上级审批，开始和结束日期都包含在内。",
     {"leave_type": p(S, "假期类型：annual 年假，sick 病假，personal 事假", ["annual", "sick", "personal"]),
      "start_date": p(S, "开始" + DATE), "end_date": p(S, "结束" + DATE)}, ["leave_type", "start_date", "end_date"]),
    ("get_leave_balance", "查询剩余假期天数", "返回年假、病假的剩余天数。",
     {"employee_id": p(S, "员工编号，形如 U-00，不传查自己")}, []),
    ("cancel_leave_request", "撤回请假申请", "只能撤回尚未开始的请假。",
     {"request_id": p(S, "申请编号，形如 LV-0000")}, ["request_id"]),
    ("approve_leave_request", "审批下属的请假申请", "上级使用。",
     {"request_id": p(S, "申请编号，形如 LV-0000"), "approved": p("boolean", "是否同意")}, ["request_id", "approved"]),
    # expenses
    ("submit_expense", "提交一笔报销", "提交后进入财务审核。",
     {"category": p(S, "类别：transport 交通，meal 餐饮，hotel 住宿，office 办公用品", ["transport", "meal", "hotel", "office"]),
      "amount": p(N, "金额，单位元，数字"), "date": p(S, "消费" + DATE)}, ["category", "amount", "date"]),
    ("get_expense", "查询报销单", "返回报销单的金额和审核状态。",
     {"expense_id": p(S, "报销单号，形如 EX-0000")}, ["expense_id"]),
    ("list_expenses", "列出我的报销单", "可按月份过滤。",
     {"month": p(S, "月份，格式 YYYY-MM")}, []),
    ("approve_expense", "审批报销单", "财务或上级使用。",
     {"expense_id": p(S, "报销单号，形如 EX-0000"), "approved": p("boolean", "是否同意")}, ["expense_id", "approved"]),
    # files
    ("share_file", "把共享盘里的文件分享给同事", "按文件路径分享，权限分只读和可编辑。",
     {"path": p(S, "文件在共享盘里的路径或文件名"), "user_id": p(S, "同事的员工编号，形如 U-00"),
      "permission": p(S, "权限：view 只读，edit 可编辑", ["view", "edit"])}, ["path", "user_id", "permission"]),
    ("search_files", "在共享盘里搜索文件", "按文件名模糊匹配。",
     {"keyword": p(S, "文件名关键词")}, ["keyword"]),
    ("get_file_info", "查询文件信息", "返回大小、修改时间和当前分享对象。",
     {"path": p(S, "文件路径")}, ["path"]),
    ("upload_file", "上传文件到共享盘", "把本地文件上传到指定目录。",
     {"local_path": p(S, "本地文件路径"), "folder": p(S, "共享盘目录")}, ["local_path", "folder"]),
    ("delete_file", "删除共享盘里的文件", "删除后 30 天内可在回收站恢复。",
     {"path": p(S, "文件路径")}, ["path"]),
    ("move_file", "移动共享盘里的文件", "移动到另一个目录。",
     {"path": p(S, "文件路径"), "folder": p(S, "目标目录")}, ["path", "folder"]),
    # weather
    ("get_current_weather", "查询城市当前的实时天气", "只返回此刻的温度和天气，不含未来几天。",
     {"city": p(S, "城市中文名")}, ["city"]),
    ("get_weather_forecast", "查询城市未来某天的天气预报", "支持未来 7 天，返回降水概率和温度范围。",
     {"city": p(S, "城市中文名"), "date": p(S, DATE)}, ["city", "date"]),
    ("get_air_quality", "查询城市的空气质量", "返回 AQI 和首要污染物。",
     {"city": p(S, "城市中文名")}, ["city"]),
    # travel
    ("get_flight_status", "查询某个航班的实时状态", "返回计划和预计起降时间、登机口、是否延误。",
     {"flight_no": p(S, "航班号，如 MU5101"), "date": p(S, "航班" + DATE)}, ["flight_no", "date"]),
    ("search_flights", "搜索两地之间的航班", "按出发地、目的地和日期返回可预订航班和价格。",
     {"from_city": p(S, "出发城市"), "to_city": p(S, "到达城市"), "date": p(S, DATE)}, ["from_city", "to_city", "date"]),
    ("book_flight", "预订机票", "按航班号和日期出票。",
     {"flight_no": p(S, "航班号"), "date": p(S, DATE), "passenger": p(S, "乘机人姓名")}, ["flight_no", "date", "passenger"]),
    ("search_hotels", "搜索酒店", "按城市和入住日期返回可订酒店。",
     {"city": p(S, "城市"), "check_in": p(S, "入住" + DATE), "nights": p(I, "入住晚数")}, ["city", "check_in"]),
    ("book_hotel", "预订酒店", "按酒店编号预订。",
     {"hotel_id": p(S, "酒店编号，形如 H-0000"), "check_in": p(S, "入住" + DATE), "nights": p(I, "入住晚数")},
     ["hotel_id", "check_in", "nights"]),
    # finance
    ("convert_currency", "把一笔金额换算成另一种货币", "按当前汇率直接给出换算后的金额。",
     {"amount": p(N, "金额，数字"), "from_currency": p(S, "原币种，ISO 4217 三位代码，如 USD"),
      "to_currency": p(S, "目标币种，ISO 4217 三位代码，如 CNY")}, ["amount", "from_currency", "to_currency"]),
    ("get_exchange_rate", "查询两种货币之间的汇率", "只返回汇率本身，不做金额换算。",
     {"base": p(S, "基准币种，ISO 4217 三位代码"), "quote": p(S, "报价币种，ISO 4217 三位代码")}, ["base", "quote"]),
    # ops
    ("deploy_service", "把服务发布到指定版本", "发布一个新版本。回到上一个版本用 rollback_deployment。",
     {"service": p(S, "服务名"), "version": p(S, "版本号，如 v1.4.2")}, ["service", "version"]),
    ("rollback_deployment", "把服务回滚到上一个版本", "撤销最近一次发布，不需要指定版本号。",
     {"service": p(S, "服务名")}, ["service"]),
    ("restart_service", "重启服务", "滚动重启所有实例，版本不变。",
     {"service": p(S, "服务名")}, ["service"]),
    ("get_service_status", "查询服务的运行状态", "返回实例数、健康状态和当前版本。",
     {"service": p(S, "服务名")}, ["service"]),
    ("scale_service", "调整服务的实例数", "扩容或缩容。",
     {"service": p(S, "服务名"), "replicas": p(I, "目标实例数")}, ["service", "replicas"]),
    ("get_service_logs", "查看服务最近的日志", "返回最近若干行日志。",
     {"service": p(S, "服务名"), "lines": p(I, "行数，默认 100")}, ["service"]),
    ("list_deployments", "列出服务的发布历史", "按时间倒序返回版本和发布人。",
     {"service": p(S, "服务名")}, ["service"]),
    # alerts
    ("silence_alert", "把告警静默一段时间", "静默期间不再通知，到期自动恢复。",
     {"alert_id": p(S, "告警编号，形如 AL-0000"), "duration_minutes": p(I, "静默时长，单位分钟")}, ["alert_id", "duration_minutes"]),
    ("ack_alert", "认领告警", "表示有人在处理，告警继续保留。",
     {"alert_id": p(S, "告警编号，形如 AL-0000")}, ["alert_id"]),
    ("resolve_alert", "把告警标记为已解决", "关闭告警。",
     {"alert_id": p(S, "告警编号，形如 AL-0000")}, ["alert_id"]),
    ("list_alerts", "列出当前未解决的告警", "可按服务过滤。",
     {"service": p(S, "服务名")}, []),
]

BY_NAME = {t[0]: t for t in TOOLS}
assert len(TOOLS) == len(BY_NAME) == 100, len(TOOLS)


def render(name, level):
    _, short, detail, params, required = BY_NAME[name]
    props = {}
    for k, (t, d, enum) in params.items():
        prop = {"type": t}
        if level == "full":
            prop["description"] = d
        if level in ("full", "enum") and enum:
            prop["enum"] = list(enum)
        props[k] = prop
    desc = {"name": "", "short": short, "enum": short, "full": f"{short}。{detail}"}[level]
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": list(required)}}}
