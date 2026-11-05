# Demo nghiệm thu — đề xuất trình tự cho giảng viên

1. Giới thiệu tóm tắt 6 tính năng và phần nhóm chọn chính thức; nhấn mạnh nguyên tắc 1 pattern/1 tính năng, 1 module & 1 bảng tối đa/pattern.
2. Demo đăng nhập role STUDENT → dashboard course hợp lệ trả thống kê. Role không đủ quyền → 403/404 và không rò cache.
3. Bật fake stats delay 3s tại local. Chạy baseline lab: dashboard chậm. Hiển thị code thiếu timeout, đo thời gian thật từ Burp/CSV.
4. Chuyển patched commit. Cùng delay: dashboard phản hồi trong deadline với `isFallback` + `asOf` hoặc explicit unavailable khi cache không hợp lệ. Nêu limitation stale data.
5. Test #5 breaker: fake 5xx cho đến OPEN; recovery HALF_OPEN/CLOSED.
6. Test #7: thử sửa quiz submitted, submit expired → bị từ chối.
7. Test #8: simulate SMTP fail, enrollment + outbox vẫn được ghi cùng transaction, retry thành công (nếu sử dụng DB và đã được cho phép).
8. Test #9: nhiều report export chậm nhưng `/me` tiếp tục nhanh; ghi số thật.
9. Test #10: class capacity 2 với 5 tranh chỗ đồng thời, xác nhận active<=2; hết TTL slot được giải phóng.
10. Cuối cùng: `uv run pytest -q` + security matrix + report before/after, chỉ chiếu logs sanitized.

**Nếu thời gian demo ngắn:** ưu tiên đầy đủ #6 (vì pattern bạn đã chọn), rồi 1 test chủ chốt mỗi tính năng khác; đừng tự nhận kết quả chưa đo.
