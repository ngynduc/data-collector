# Office File Collector — Hướng Dẫn Sử Dụng

Script PowerShell dùng để **gom các file Office nằm rải rác trên máy Windows về một thư mục tập trung** phục vụ điều tra / dọn dẹp sau sự cố nhiễm mã độc. Script tự động tính hash SHA256 và xuất log CSV để hỗ trợ phân tích IOC.

> ⚠️ **Cảnh báo an toàn:** Các file được gom rất có thể là file độc (macro virus, dropper...). **Không mở (double-click) bất kỳ file nào** trong thư mục đích. Giữ EDR (Carbon Black / ESET) giám sát thư mục này.

---

## 1. Yêu cầu

| Hạng mục | Yêu cầu |
|----------|---------|
| Hệ điều hành | Windows 10/11 hoặc Windows Server |
| PowerShell | 5.1 trở lên (mặc định có sẵn trên Windows) |
| Quyền | **Administrator** (để quét được thư mục hệ thống và profile của user khác) |

---

## 2. Cấu hình

Mở script và chỉnh các biến ở đầu file cho phù hợp:

| Biến | Ý nghĩa | Giá trị mặc định |
|------|---------|------------------|
| `$SearchPaths` | Danh sách đường dẫn cần quét | `@("C:\")` |
| `$DestFolder` | Thư mục gom file về | `C:\Quarantine_Collected` |
| `$Extensions` | Các phần mở rộng file Office cần tìm | `.doc .docx .xls .xlsx .ppt .pptx .docm .xlsm .pptm` |
| `$Mode` | `"Copy"` (giữ bản gốc) hoặc `"Move"` (di chuyển) | `"Copy"` |
| `$LogFile` | Đường dẫn file log CSV | `<DestFolder>\collection_log.csv` |

**Ví dụ quét nhiều ổ / nhiều đường dẫn:**

```powershell
$SearchPaths = @("C:\", "D:\", "C:\Users")
```

---

## 3. Cách chạy

### Bước 1 — Mở PowerShell với quyền Administrator
Nhấn `Start` → gõ `PowerShell` → chuột phải → **Run as administrator**.

### Bước 2 — Cho phép chạy script trong phiên hiện tại (nếu bị chặn)

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

> Lệnh này chỉ áp dụng cho cửa sổ PowerShell hiện tại, không thay đổi cấu hình toàn hệ thống.

### Bước 3 — Chạy script

```powershell
.\Collect-OfficeFiles.ps1
```

Hoặc copy toàn bộ nội dung script và dán thẳng vào cửa sổ PowerShell.

---

## 4. Kết quả đầu ra

Sau khi chạy xong, trong thư mục `$DestFolder` bạn sẽ có:

- **Các file Office đã gom** — tự động đổi tên nếu trùng (`tên_1.docx`, `tên_2.docx`...).
- **`collection_log.csv`** — log chi tiết với các cột:

| Cột | Mô tả |
|-----|-------|
| `OriginalPath` | Đường dẫn gốc của file |
| `NewPath` | Đường dẫn sau khi gom |
| `SizeKB` | Kích thước file (KB) |
| `LastWrite` | Thời điểm sửa đổi cuối |
| `SHA256` | Hash để đối chiếu IOC / submit VirusTotal |
| `Status` | `OK` hoặc thông báo lỗi |

---

## 5. Tích hợp với quy trình điều tra

- **VirusTotal:** Lấy cột `SHA256` trong CSV để tra cứu hàng loạt.
- **Splunk:** Ingest `collection_log.csv` để correlate thời điểm tạo file (`LastWrite`) với timeline của sự cố.
- **Lọc theo thời gian nhiễm:** Nếu chỉ muốn gom file do virus tạo trong một khoảng thời gian, thêm điều kiện lọc vào bước `Get-ChildItem`, ví dụ:

```powershell
Where-Object { $_.CreationTime -ge "2026-06-15" -and $_.CreationTime -le "2026-06-16" }
```

---

## 6. Xử lý sự cố thường gặp

| Vấn đề | Cách xử lý |
|--------|-----------|
| `cannot be loaded because running scripts is disabled` | Chạy `Set-ExecutionPolicy -Scope Process Bypass` trước. |
| Bỏ sót file trong thư mục hệ thống / profile khác | Đảm bảo đang chạy PowerShell **as Administrator**. |
| `Access denied` ở vài thư mục | Bình thường — script dùng `-ErrorAction SilentlyContinue` để bỏ qua và tiếp tục. |
| Quét chậm trên ổ lớn | Thu hẹp `$SearchPaths` về các thư mục nghi ngờ thay vì cả ổ `C:\`. |

---

## 7. Khuyến nghị an toàn

1. **Không mở file** đã gom bằng Office. Nếu cần xem nội dung, dùng môi trường sandbox / cách ly.
2. Sau khi điều tra xong, có thể nén thư mục (đặt mật khẩu) để lưu trữ phục vụ forensics.
3. Giữ giải pháp EDR/AV chạy nền trong suốt quá trình gom file.
4. Nếu dùng `$Mode = "Move"`, hãy **chạy thử với `Copy` và kiểm tra log trước** để tránh mất dữ liệu ngoài ý muốn.