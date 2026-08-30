# KKPhim Telegram Bot

Telegram bot tìm kiếm phim sử dụng KKPhim API. Được thiết kế production-grade, async,
có session isolation trong group, rate limit, cache, retry, và dễ mở rộng.

## Kiến trúc tổng thể

```
project/
├── app/
│   ├── bot/
│   │   ├── handlers/        # Command & text handlers
│   │   ├── keyboards/       # Inline keyboard builders
│   │   ├── callbacks/       # Callback query handlers
│   │   ├── middleware/      # Logging, rate limit
│   │   └── filters/         # Chat type filters
│   ├── services/            # Business logic
│   ├── providers/kkphim/    # KKPhim API client + models
│   ├── database/            # SQLAlchemy models + repositories
│   ├── config.py
│   ├── logging_config.py
│   └── main.py
├── tests/
├── .env.example
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Chạy local

```bash
git clone <repo>
cd project
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
cp .env.example .env
# Sửa .env với TELEGRAM_BOT_TOKEN và KKPHIM_API_KEY
python -m app
```

## Chạy bằng Docker

```bash
cp .env.example .env
# Sửa .env với TELEGRAM_BOT_TOKEN và KKPHIM_API_KEY
docker-compose up --build -d
```

## Chạy tests

```bash
pytest
```

## Session isolation trong group

- Mỗi request tạo một `Session` với `id` ngẫu nhiên, lưu `user_id`, `chat_id`,
  `query`, `current_page`, `message_id`, `expires_at`.
- Callback data chỉ chứa `movie:<slug>:<session_id>` hoặc `page:<n>:<session_id>`.
- Khi callback đến, `SessionService.authorize()` kiểm tra:
  - session tồn tại,
  - chưa hết hạn,
  - đúng `chat_id`,
  - đúng `telegram_user_id` của chủ session.
- Nếu user khác bấm nhầm → trả lời "Đây là kết quả của người khác".

## Reply-to-message trong group

- Khi user gửi text trong group, bot `reply` vào message gốc với "Đang tìm kiếm..."
  sau đó `edit` message đó thành kết quả.
- Mỗi user có message reply riêng, không bị lẫn.

## Các chỗ cần chỉnh sau khi có tài liệu API KKPhim
## Tính năng đã hoàn thiện theo tài liệu API KKPhim (phimapi.com)

1. `app/providers/kkphim/client.py`: thay endpoint `/v1/search`, `/v1/movie/{slug}`,
   `/v1/new`, `/v1/popular`, `/v1/type/{type}`, `/v1/country/{country}`, `/v1/genre/{genre}`
   bằng endpoint thật.
2. `app/providers/kkphim/client.py` `_normalize_paginated`: điều chỉnh key JSON
   (`items`, `total`, `total_pages`) theo response thật.
3. `app/providers/kkphim/models.py`: thêm/bớt field cho khớp schema thật.
4. `app/bot/keyboards/common.py`: `countries_keyboard` và `genres_keyboard` nên
   lấy động từ API thay vì danh sách cứng.
5. `app/bot/keyboards/common.py`: `watch_keyboard` có thể cần xử lý nhiều server
   hoặc nhiều tập phức tạp hơn.
1. **KKPhim Provider & Models (`app/providers/kkphim/`)**:
   - Tích hợp chuẩn Base URL: `https://phimapi.com` (CDN: `https://phimimg.com/`).
   - Endpoint tìm kiếm: `/v1/api/tim-kiem` hỗ trợ từ khóa, lọc theo thể loại, quốc gia, năm, sắp xếp.
   - Endpoint chi tiết phim: `/phim/{slug}` trả về thông tin phim, diễn viên, đạo diễn, điểm TMDB/IMDB, trailer YouTube và danh sách tập phim theo từng server phát (Vietsub, Thuyết minh...).
   - Endpoint danh sách: `/v1/api/danh-sach` (Phim mới), `/v1/api/danh-sach/{type}` (Phim bộ, Phim lẻ, Hoạt hình, TV Shows, Chiếu rạp).
   - Endpoint thể loại (`/the-loai`), quốc gia (`/quoc-gia`), năm phát hành (`/nam-phat-hanh`).
   - Tự động chuẩn hóa đường dẫn ảnh tương đối thành URL đầy đủ.

2. **Giao diện Bot & Inline Keyboards (`app/bot/`)**:
   - Menu chính trực quan, bàn phím chọn thể loại, quốc gia, năm phát hành động lấy trực tiếp từ API và có cache tốc độ cao.
   - Bàn phím xem phim phân chia nhiều server phát, tự động phân trang 24 tập/trang cho phim bộ nhiều tập (50 - 1000+ tập).
   - Bộ lọc và làm sạch thẻ HTML an toàn cho tin nhắn Telegram.

3. **Lệnh hỗ trợ (Commands)**:
   - `/start` - Khởi động bot & menu chính
   - `/help` - Xem hướng dẫn sử dụng chi tiết
   - `/tim <tên phim>` hoặc gõ thẳng tên phim vào ô chat để tìm kiếm
   - `/phimmoi` - Danh sách phim mới cập nhật
   - `/chieurap` - Danh sách phim chiếu rạp nổi bật
   - `/phimbo` - Phim bộ nhiều tập
   - `/phimle` - Phim lẻ / điện ảnh
   - `/hoathinh` - Hoạt hình / Anime
   - `/theloai` - Khám phá theo thể loại
   - `/quocgia` - Khám phá theo quốc gia
   - `/nam` - Khám phá theo năm phát hành
   - `/yeuthich` - Quản lý danh sách phim yêu thích cá nhân

## License

MIT
