# LevAgent

Tác nhân giao dịch **đòn bẩy** tiền điện tử. Mỗi vòng nó đọc nến, tính chỉ báo, đọc tiêu đề tin, rồi **tự quyết định** đứng ngoài, vào lệnh hoặc đóng lệnh.

Đây không phải lời khuyên đầu tư. Đòn bẩy có thể làm mất hết số vốn đã nạp. Kết quả backtest không phải lợi nhuận tương lai.

Chương trình **không** dùng mô hình ngôn ngữ để đoán giá. Quyết định là quy tắc cố định, nên cùng một dữ liệu luôn ra cùng một lệnh và có lý do đọc được.

## An toàn

- Mặc định chỉ có sổ **giả lập**. Không có khóa API thì không thể gửi lệnh.
- Lệnh thật chỉ gửi khi có đủ ba điều kiện: `python -m levagent live --send`, biến `LEVAGENT_ARM_LIVE=I_ACCEPT_TOTAL_LOSS`, và `BINANCE_API_KEY` / `BINANCE_API_SECRET`.
- Trần đòn bẩy cứng là **10x**. Mặc định là **3x**. Không nới qua tham số dòng lệnh.
- Mỗi lệnh đều có dừng lỗ và chốt lời. Nếu dừng lỗ nằm sau giá thanh lý, lệnh bị bỏ.
- Khối lượng tính từ số tiền chấp nhận mất tại dừng lỗ (mặc định **0,5% vốn**), không phải từ mức đòn bẩy tối đa.
- Lỗ đã chốt trong ngày vượt **3%** thì không mở lệnh mới.
- Tin tức chỉ được **chặn** lệnh, không tự tạo lệnh.
- Nếu lệnh thật khớp mà không đặt được dừng lỗ, tác nhân hủy lệnh chờ và gửi lệnh đóng vị thế.

Sàn lệnh thật duy nhất là **Binance USDT-M**, tài khoản ở chế độ một chiều (one-way).

## Quy tắc vào lệnh

Điểm kỹ thuật từ -1 đến +1, ghép từ:

- hướng EMA 20 so với EMA 50, chia cho ATR
- RSI 14
- histogram MACD 12/26/9

Vào **mua** khi điểm ≥ 0,40, EMA nhanh nằm trên EMA chậm, histogram dương, và RSI trong khoảng 45–85.

Vào **bán** khi các điều kiện đối xứng, RSI trong khoảng 15–55.

Đứng ngoài khi ATR vượt 5% giá, khi chưa đủ nến, hoặc khi tin trong cửa sổ thời gian trái chiều mạnh (điểm tin ≤ -0,55 với lệnh mua, ≥ +0,55 với lệnh bán).

Dừng lỗ đặt cách giá **1,5 ATR**. Chốt lời ở **2 lần** khoảng dừng. Đòn bẩy là số nguyên nhỏ nhất đủ ký quỹ cho khối lượng đó, và bị hạ xuống nếu dừng lỗ không còn nằm trước giá thanh lý.

Tin đọc từ RSS CoinDesk và Cointelegraph, cộng tiêu đề bạn truyền bằng `--headline`. Từ điển có cả tiếng Việt và tiếng Anh (`bị hack`, `phê duyệt ETF`, `ban`, `rally`, …).

## Cách chạy

Cần Python 3.11 trở lên. Không cần cài thư viện.

```bash
python -m levagent demo
python -m levagent decide --synthetic
python -m levagent decide --synthetic --headline "Bitcoin bị hack, nhà đầu tư phá sản"
python -m levagent backtest --symbol BTCUSDT --interval 1h
python -m levagent run --symbol BTCUSDT --interval 1h
python -m levagent status
```

`demo`, `decide --synthetic` và `run --synthetic` không cần mạng. `decide`, `backtest` và `run` không có `--synthetic` thì tải nến công khai và RSS. Nến được thử lần lượt từ Binance USDT-M, `data-api.binance.vision`, rồi Binance.US, vì một số mạng bị chặn HTTP 451.

`run` ghi sổ giả lập vào `state/paper.json`. Chạy lại lệnh đó mỗi khi nến đóng (ví dụ mỗi giờ với khung `1h`) để tác nhân tự cập nhật dừng lỗ, chốt lời, thanh lý và lệnh mới. Thêm `--reset` nếu muốn xóa sổ.

Giờ in ra là **ICT** (UTC+7). Ngày khóa lỗ tính theo ngày UTC của nến.

Tham số: `--symbol`, `--interval` (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`), `--equity`, `--risk` (tối đa 0,02), `--leverage` (1–10).

## Lệnh thật

Xem kế hoạch, không gửi:

```bash
python -m levagent live --symbol BTCUSDT --interval 1h
```

Chỉ khi bạn tự chấp nhận mất vốn:

```bash
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
export LEVAGENT_ARM_LIVE=I_ACCEPT_TOTAL_LOSS
python -m levagent live --symbol BTCUSDT --interval 1h --send
```

Không commit khóa API. Tệp `.env` đã nằm trong `.gitignore`.

## Kiểm thử

```bash
python -m unittest discover -s tests -t . -v
```
