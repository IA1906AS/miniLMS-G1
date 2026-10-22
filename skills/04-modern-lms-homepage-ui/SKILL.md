---
name: modern-lms-homepage-ui
description: Thiết kế giao diện Home Page và LMS Portal hiện đại theo chuẩn quản lý dự án Web (Executive Dashboard, Bento Grid, Glassmorphism, 4-Role Switcher, Live Defense-in-Depth Inspector).
---

# 🎨 SKILL 04: THIẾT KẾ MODERN LMS HOME PAGE & WEB APP PORTAL

## 1. Tầm nhìn Thiết kế (Theo yêu cầu của các Sếp / Quản lý Dự án Web hiện nay)

Các quản lý dự án Web (Project Managers / Product Owners) và giảng viên chấm trực tiếp đánh giá rất cao một giao diện đáp ứng 3 tiêu chí:
1. **Executive Look & Feel**: Thiết kế SaaS hiện đại (tông màu Indigo-Slate-Emerald, hiệu ứng Glassmorphism tinh tế, bố cục **Bento Grid**, Dark/Light Mode, Typography sắc nét với font `Inter` / `Plus Jakarta Sans`).
2. **Zero-Friction Demo (Demo 1-Click khi chấm bài)**:
   - Khi chấm trực tiếp trong 35 phút, giảng viên và PM không muốn phải gõ tay từng email/password.
   - Trang chủ cần tích hợp thanh **"Quick Demo Role Switcher (1-Click Login)"** cho cả 4 Roles (`Admin`, `Teacher An - c1`, `Teacher Bình - c2`, `Student Chi - u4`, `Student Dũng - u5`, `Student Em - u6`, và `Guest Mode`) cùng đầy đủ Modal **Đăng nhập / Đăng ký / Reset Password**.
3. **Visualizing Defense-in-Depth (Trực quan hóa 8 Lớp Bảo Vệ)**:
   - Hiển thị trạng thái thực tế của 8 lớp bảo vệ ngay trên giao diện, kèm bảng kết quả gọi API trực tiếp (HTTP Status, JSON Response, JWT Payload Inspector, và Live Audit Log Stream).

---

## 2. Cấu trúc Giao diện Trang chủ (`app/templates/index.html`)

Antigravity cần xây dựng file `app/templates/index.html` (được phục vụ tại route `GET /`) gồm 5 phân khu hiện đại:

### Khu vực 1: Sticky Glassmorphism Navbar
- Logo thương hiệu: **ShieldLMS — Defense-in-Depth Learning Platform**.
- Badge hiển thị trạng thái phiên hiện tại:
  - Khi chưa đăng nhập: Badge `ROLE: GUEST (Public Access)` + Nút **Đăng nhập**, **Đăng ký**, **Quên mật khẩu**.
  - Khi đã đăng nhập: Hiển thị `ID`, `Email`, Badge màu theo Role (`ADMIN` tím, `TEACHER/INSTRUCTOR` xanh dương, `STUDENT` xanh lá, `GUEST` xám), đồng hồ đếm ngược thời hạn JWT (`expiresIn`), và nút **Đăng xuất**.

### Khu vực 2: Executive Hero Section & Bento KPI Cards
- Tiêu đề lớn hiện đại kết hợp thông điệp bảo mật 8 lớp (Zero-Trust & Defense-in-Depth Architecture).
- **4 Bento Metric Cards**:
  1. **Active Courses**: Số khóa học đang mở (`Lập trình Web - c1`, `Cơ sở dữ liệu - c2`).
  2. **Role-Based Access (4 Roles)**: `Admin`, `Teacher`, `Student`, `Guest`.
  3. **Security Architecture**: `8 Independent Layers (HS256 + Bcrypt + Object Guards + Audit)`.
  4. **Brute-Force Shield**: `5 Attempts / 15m Lockout Active`.

### Khu vực 3: Quick Demo Role Switcher (Thanh chuyển nhanh 1-Click cho Buổi Chấm Bài)
- Các nút bấm điền sẵn hoặc đăng nhập nhanh chỉ với 1 cú click:
  - 👑 **Admin (`admin@lms.test`)**
  - 👨‍🏫 **Teacher An (`an.gv@lms.test` - Dạy c1)**
  - 👨‍🏫 **Teacher Bình (`binh.gv@lms.test` - Dạy c2)**
  - 🎓 **Student Chi (`chi.sv@lms.test` - Học c1)**
  - 🎓 **Student Dũng (`dung.sv@lms.test` - Học c1, c2)**
  - 🎓 **Student Em (`em.sv@lms.test` - Học c2)**
  - 🌐 **Guest Visitor (Chế độ Khách)**

### Khu vực 4: Không gian Làm việc Theo Vai Trò (Role-Specific Workspace)
- **Khi là Guest (`GUEST`)**:
  - Xem danh sách khóa học công khai, giảng viên phụ trách, đề cương môn học.
  - Khi bấm vào "Xem bảng điểm nội bộ", hệ thống minh họa ngay lớp chắn bảo mật (`401 UNAUTHENTICATED` hoặc `403 FORBIDDEN`).
- **Khi là Student (`STUDENT`)**:
  - Chọn môn học (`c1` hoặc `c2`) để tra cứu điểm của bản thân (`GET /courses/<id>/grades`).
  - Hiển thị điểm số trực quan kèm thanh tiến độ. Nếu bấm thử sửa điểm sẽ thấy ngay Lớp 3 & Lớp 4 chặn lại với `403 FORBIDDEN`.
- **Khi là Teacher (`INSTRUCTOR`)**:
  - Xem bảng điểm toàn bộ sinh viên trong lớp mình dạy (`GET /courses/<id>/grades`).
  - Form cập nhật điểm trực tiếp (`PUT /courses/<id>/grades/<student_id>`) có thông báo kết quả tức thì.
- **Khi là Admin (`ADMIN`)**:
  - Xem toàn bộ điểm của tất cả các môn học (`c1`, `c2`).
  - Bảng **Live Security Audit Log Viewer** đọc từ `audit.log` hiển thị thời gian thực các sự kiện sửa điểm (`oldScore` -> `newScore`) và các hành vi truy cập trái phép bị chặn (`FORBIDDEN`).

### Khu vực 5: Modal Xác thực Đa Năng (Auth Center)
- **Tab 1 - Đăng nhập (`POST /auth/login`)**: Hỗ trợ kiểm tra thông báo lỗi chuẩn xác (`401 INVALID_CREDENTIALS`, `429 ACCOUNT_LOCKED`).
- **Tab 2 - Đăng ký (`POST /auth/register`)**: Cho phép chọn Role (`Student`, `Teacher`, `Guest`), tạo tài khoản mới và đăng nhập ngay.
- **Tab 3 - Reset Password (`POST /auth/reset-password`)**: Cho phép đặt lại mật khẩu mới an toàn.
