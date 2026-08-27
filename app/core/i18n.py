"""OrderAI 五語系訊息表；只接受正式 locale code。"""
_MESSAGES = {
    "zh-Hant-TW": {
        "order_not_found": "找不到訂單",
        "ai_quota_exceeded": "本月 AI 解析次數已達上限",
        "not_order_message": "非訂單訊息，已略過",
        "unauthorized": "未授權",
        "forbidden": "權限不足",
    },
    "en-US": {
        "order_not_found": "Order not found",
        "ai_quota_exceeded": "Monthly AI parsing limit reached",
        "not_order_message": "Not an order message; skipped",
        "unauthorized": "Unauthorized",
        "forbidden": "Forbidden",
    },
    "th-TH": {
        "order_not_found": "ไม่พบคำสั่งซื้อ",
        "ai_quota_exceeded": "ใช้โควต้าวิเคราะห์คำสั่งซื้อด้วย AI ประจำเดือนครบแล้ว",
        "not_order_message": "ไม่ใช่ข้อความสั่งซื้อ จึงข้ามแล้ว",
        "unauthorized": "ไม่ได้รับอนุญาต",
        "forbidden": "ไม่มีสิทธิ์เข้าถึง",
    },
    "ja-JP": {
        "order_not_found": "注文が見つかりません",
        "ai_quota_exceeded": "今月の AI 注文解析上限に達しました",
        "not_order_message": "注文メッセージではないためスキップしました",
        "unauthorized": "認証されていません",
        "forbidden": "アクセス権限がありません",
    },
    "id-ID": {
        "order_not_found": "Pesanan tidak ditemukan",
        "ai_quota_exceeded": "Batas analisis pesanan AI bulanan telah tercapai",
        "not_order_message": "Bukan pesan pesanan, dilewati",
        "unauthorized": "Tidak berwenang",
        "forbidden": "Akses ditolak",
    },
}


def t(key: str, lang: str = "zh-Hant-TW") -> str:
    return _MESSAGES.get(lang, _MESSAGES["zh-Hant-TW"]).get(key, key)
