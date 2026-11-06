-- ============================================================================
-- miniLMS Database Initialization Script (PostgreSQL 16+)
-- Meets all specifications from Section 2 of requirements and SQLAlchemy Models
-- ============================================================================

-- Clean up existing tables if resetting
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS outbox_events CASCADE;
DROP TABLE IF EXISTS seat_reservations CASCADE;
DROP TABLE IF EXISTS quiz_attempts CASCADE;
DROP TABLE IF EXISTS quizzes CASCADE;
DROP TABLE IF EXISTS idempotency_records CASCADE;
DROP TABLE IF EXISTS submissions CASCADE;
DROP TABLE IF EXISTS assignments CASCADE;
DROP TABLE IF EXISTS lessons CASCADE;
DROP TABLE IF EXISTS enrollments CASCADE;
DROP TABLE IF EXISTS classes CASCADE;
DROP TABLE IF EXISTS courses CASCADE;
DROP TABLE IF EXISTS password_reset_tokens CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ----------------------------------------------------------------------------
-- 1. USERS TABLE
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL DEFAULT '',
    role VARCHAR(20) NOT NULL DEFAULT 'guest',
    bio TEXT DEFAULT '',
    phone_number VARCHAR(50),
    avatar_url VARCHAR(255),
    notification_preferences TEXT DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);

-- ----------------------------------------------------------------------------
-- 2. PASSWORD RESET TOKENS
-- ----------------------------------------------------------------------------
CREATE TABLE password_reset_tokens (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
CREATE INDEX idx_password_reset_tokens_hash ON password_reset_tokens(token_hash);

-- ----------------------------------------------------------------------------
-- 3. COURSES TABLE
-- ----------------------------------------------------------------------------
CREATE TABLE courses (
    id VARCHAR(36) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    instructor_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    description TEXT DEFAULT '',
    thumbnail VARCHAR(255) DEFAULT '',
    duration_hours INT DEFAULT 30,
    is_featured BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 4. ENROLLMENTS TABLE (with Score for Academic Records)
-- ----------------------------------------------------------------------------
CREATE TABLE enrollments (
    course_id VARCHAR(36) NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    student_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score FLOAT NOT NULL DEFAULT 0.0,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (course_id, student_id)
);

-- ----------------------------------------------------------------------------
-- 5. LESSONS TABLE
-- ----------------------------------------------------------------------------
CREATE TABLE lessons (
    id VARCHAR(36) PRIMARY KEY,
    course_id VARCHAR(36) NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    order_index INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_lessons_course_id ON lessons(course_id);

-- ----------------------------------------------------------------------------
-- 6. ASSIGNMENTS TABLE
-- ----------------------------------------------------------------------------
CREATE TABLE assignments (
    id VARCHAR(36) PRIMARY KEY,
    course_id VARCHAR(36) NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description VARCHAR(1000) NOT NULL DEFAULT '',
    max_score FLOAT NOT NULL DEFAULT 10.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_assignments_course_id ON assignments(course_id);

-- ----------------------------------------------------------------------------
-- 7. SUBMISSIONS TABLE
-- ----------------------------------------------------------------------------
CREATE TABLE submissions (
    id VARCHAR(36) PRIMARY KEY,
    assignment_id VARCHAR(36) NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    student_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content VARCHAR(2000) NOT NULL DEFAULT '',
    score FLOAT,
    feedback VARCHAR(1000) NOT NULL DEFAULT '',
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_submissions_assignment_id ON submissions(assignment_id);
CREATE INDEX idx_submissions_student_id ON submissions(student_id);

-- ----------------------------------------------------------------------------
-- 8. CLASSES TABLE (For Room & Seat Capacity)
-- ----------------------------------------------------------------------------
CREATE TABLE classes (
    id VARCHAR(50) PRIMARY KEY,
    course_id VARCHAR(36) NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    code VARCHAR(50) NOT NULL,
    room VARCHAR(50) NOT NULL DEFAULT 'Room-Online',
    capacity INT NOT NULL DEFAULT 30,
    reserved_count INT NOT NULL DEFAULT 0,
    confirmed_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_classes_course_id ON classes(course_id);

-- ----------------------------------------------------------------------------
-- 9. SEAT RESERVATIONS TABLE (Pattern #10: Two-Phase Reservation)
-- ----------------------------------------------------------------------------
CREATE TABLE seat_reservations (
    id VARCHAR(36) PRIMARY KEY,
    class_id VARCHAR(50) NOT NULL,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'HELD', -- HELD, CONFIRMED, CANCELLED, EXPIRED
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ
);

CREATE INDEX idx_reservations_class_id ON seat_reservations(class_id);
CREATE INDEX idx_reservations_user_id ON seat_reservations(user_id);

-- ----------------------------------------------------------------------------
-- 10. QUIZZES TABLE (Pattern #7: State Machine Lifecycle)
-- ----------------------------------------------------------------------------
CREATE TABLE quizzes (
    id VARCHAR(36) PRIMARY KEY,
    course_id VARCHAR(36) NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    time_limit_seconds INT NOT NULL DEFAULT 1800,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quizzes_course_id ON quizzes(course_id);

-- ----------------------------------------------------------------------------
-- 11. QUIZ ATTEMPTS TABLE
-- ----------------------------------------------------------------------------
CREATE TABLE quiz_attempts (
    id VARCHAR(36) PRIMARY KEY,
    quiz_id VARCHAR(36) NOT NULL,
    student_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    state VARCHAR(20) NOT NULL DEFAULT 'CREATED', -- CREATED, IN_PROGRESS, SUBMITTED, EXPIRED
    answers TEXT NOT NULL DEFAULT '{}',
    score FLOAT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMPTZ
);

CREATE INDEX idx_quiz_attempts_quiz_id ON quiz_attempts(quiz_id);
CREATE INDEX idx_quiz_attempts_student_id ON quiz_attempts(student_id);

-- ----------------------------------------------------------------------------
-- 12. TRANSACTIONAL OUTBOX EVENTS TABLE (Pattern #8: Outbox)
-- ----------------------------------------------------------------------------
CREATE TABLE outbox_events (
    id VARCHAR(36) PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    deduplication_key VARCHAR(150) NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING, PROCESSED, FAILED
    retry_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_events_dedup ON outbox_events(deduplication_key);
CREATE INDEX idx_outbox_events_status ON outbox_events(status);

-- ----------------------------------------------------------------------------
-- 13. IDEMPOTENCY RECORDS TABLE (Pattern #4: Idempotency Key)
-- ----------------------------------------------------------------------------
CREATE TABLE idempotency_records (
    key VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING', -- PROCESSING, COMPLETED, FAILED
    response_code INT,
    response_body TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_idempotency_user_id ON idempotency_records(user_id);

-- ----------------------------------------------------------------------------
-- 14. AUDIT LOGS TABLE (Defense in Depth: Layer 7 Audit Trail)
-- ----------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    ip_address VARCHAR(45),
    details TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);

-- ============================================================================
-- SEED DATA INSERTION (Matches seed.json with bcrypt hash for 'Lms@2026')
-- ============================================================================

-- Password: 'Lms@2026' -> $2b$10$Zo.tLFw2ydGyFc6jj3GkjuAFK3EyQnWHru0XJB6W4mcyT59oHfdn2
INSERT INTO users (id, email, password_hash, full_name, role, phone_number, bio, avatar_url, is_active, is_verified) VALUES
('u1', 'admin@lms.test', '$2b$10$Zo.tLFw2ydGyFc6jj3GkjuAFK3EyQnWHru0XJB6W4mcyT59oHfdn2', 'Quản Trị Viên Hệ Thống', 'ADMIN', '0901234567', 'Quản trị viên cấp cao miniLMS', 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=150', TRUE, TRUE),
('u2', 'an.gv@lms.test', '$2b$10$Zo.tLFw2ydGyFc6jj3GkjuAFK3EyQnWHru0XJB6W4mcyT59oHfdn2', 'ThS. Nguyễn Văn An', 'INSTRUCTOR', '0912345678', 'Giảng viên bộ môn Phát triển Ứng dụng Web & An toàn Thông tin', 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150', TRUE, TRUE),
('u3', 'binh.gv@lms.test', '$2b$10$Zo.tLFw2ydGyFc6jj3GkjuAFK3EyQnWHru0XJB6W4mcyT59oHfdn2', 'TS. Trần Thị Bình', 'INSTRUCTOR', '0923456789', 'Chuyên gia Cơ sở dữ liệu phân tán & Tối ưu hóa truy vấn', 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150', TRUE, TRUE),
('u4', 'chi.sv@lms.test', '$2b$10$Zo.tLFw2ydGyFc6jj3GkjuAFK3EyQnWHru0XJB6W4mcyT59oHfdn2', 'Lê Linh Chi', 'STUDENT', '0934567890', 'Sinh viên ngành Kỹ thuật Phần mềm, đam mê Web Fullstack', 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150', TRUE, TRUE),
('u5', 'dung.sv@lms.test', '$2b$10$Zo.tLFw2ydGyFc6jj3GkjuAFK3EyQnWHru0XJB6W4mcyT59oHfdn2', 'Phạm Quốc Dũng', 'STUDENT', '0945678901', 'Sinh viên ngành An toàn Thông tin (IA1906AS)', 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150', TRUE, TRUE),
('u6', 'em.sv@lms.test', '$2b$10$Zo.tLFw2ydGyFc6jj3GkjuAFK3EyQnWHru0XJB6W4mcyT59oHfdn2', 'Hoàng Thị Ánh Em', 'STUDENT', '0956789012', 'Sinh viên chuyên ngành Hệ thống Thông tin quản lý', 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=150', TRUE, TRUE);

INSERT INTO courses (id, title, instructor_id, description, thumbnail, duration_hours, is_featured) VALUES
('c1', 'Lập trình Web', 'u2', 'Xây dựng ứng dụng web hiện đại từ frontend đến backend, chuẩn kiến trúc RESTful API.', 'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600', 30, TRUE),
('c2', 'Cơ sở dữ liệu', 'u3', 'Thiết kế chuẩn hóa cơ sở dữ liệu quan hệ, tối ưu chỉ mục và xử lý N+1 truy vấn.', 'https://images.unsplash.com/photo-1544383835-bda2bc66a55d?w=600', 45, TRUE),
('c3', 'An toàn Ứng dụng Web (IAW301)', 'u2', 'Các kỹ thuật phòng chống OWASP Top 10, kiểm soát truy cập phân tầng (Defense-in-Depth).', 'https://images.unsplash.com/photo-1563986768609-322da13575f3?w=600', 36, TRUE);

INSERT INTO enrollments (course_id, student_id, score) VALUES
('c1', 'u4', 7.5),
('c1', 'u5', 8.0),
('c2', 'u5', 6.0),
('c2', 'u6', 9.0);

INSERT INTO lessons (id, course_id, title, content, order_index) VALUES
('c1-l1', 'c1', 'Bài 1: Giới thiệu Kiến trúc Ứng dụng Web & REST', 'Nội dung chi tiết về giao thức HTTP, phương thức GET, POST, PUT, DELETE và mã trạng thái HTTP chuẩn.', 1),
('c1-l2', 'c1', 'Bài 2: Thiết kế RESTful API với Flask & Blueprint', 'Phân tách module ứng dụng theo Blueprint, xử lý request context và serialization JSON.', 2),
('c1-l3', 'c1', 'Bài 3: Xác thực JWT & Cơ chế Phân quyền RBAC', 'Mã hóa token HS256, kiểm tra thời hạn exp, giải mã claim sub và bảo vệ endpoint phân tầng.', 3),
('c1-l4', 'c1', 'Bài 4: Tích hợp Frontend React / SPA', 'Giao tiếp RESTful API bất đồng bộ với fetch(), quản lý state và xử lý lỗi.', 4),
('c2-l1', 'c2', 'Bài 1: Mô hình Thực thể Quan hệ & Chuẩn hóa 3NF', 'Phân tích các dạng chuẩn 1NF, 2NF, 3NF và Boyce-Codd Normal Form trong thiết kế quan hệ.', 1),
('c2-l2', 'c2', 'Bài 2: Truy vấn SQL nâng cao & Aggregation', 'Kỹ thuật GROUP BY, HAVING, Window Functions và tối ưu hóa câu truy vấn phức tạp.', 2),
('c2-l3', 'c2', 'Bài 3: Chỉ mục B-Tree và Kế hoạch Thực thi', 'Phân tích kế hoạch truy vấn với EXPLAIN ANALYZE và tối ưu hóa index scan.', 3),
('c2-l4', 'c2', 'Bài 4: Kỹ thuật chống N+1 Query trong ORM', 'Sử dụng eager loading (joinedload, selectinload) trong SQLAlchemy để loại bỏ N+1 query.', 4),
('c3-l1', 'c3', 'Bài 1: Tổng quan Mô hình Phòng thủ Đa tầng', 'Nguyên lý Defense in Depth trong phát triển phần mềm an toàn theo tiêu chuẩn OWASP.', 1),
('c3-l2', 'c3', 'Bài 2: Kiểm soát Xác thực & Chống Brute-Force', 'Cơ chế Rate Limiting, Brute Force Lockout và Timing Attack Mitigation bằng bcrypt.', 2),
('c3-l3', 'c3', 'Bài 3: Chống Khai thác IDOR / BOLA', 'Kiểm tra quyền sở hữu tài nguyên ở tầng Domain Service thay vì chỉ kiểm tra ở Route Guard.', 3),
('c3-l4', 'c3', 'Bài 4: Audit Logging & Giám sát An ninh', 'Ghi nhật ký kiểm toán không rò rỉ secret, lưu vết mọi thay đổi điểm số và phân quyền.', 4);

INSERT INTO assignments (id, course_id, title, description, max_score) VALUES
('a1', 'c1', 'Bài tập Lớn: Triển khai RESTful API miniLMS', 'Xây dựng toàn bộ các endpoint xác thực, danh sách khóa học và cập nhật điểm với chuẩn mã HTTP.', 10.0),
('a2', 'c2', 'Bài thực hành: Chuẩn hóa Schema & Tối ưu Chỉ mục', 'Viết mã script DDL tạo bảng, khóa chính, khóa ngoại và phân tích kế hoạch EXPLAIN ANALYZE.', 10.0),
('a3', 'c3', 'Đồ án An toàn: Kiểm thử Tầng Phòng Thủ Đa Tầng', 'Thực hiện kiểm thử tự động 8 tầng bảo mật, quét mã tĩnh Semgrep SAST và kiểm thử IDOR.', 10.0);

INSERT INTO submissions (id, assignment_id, student_id, content, score, feedback) VALUES
('sub1', 'a1', 'u4', 'Em đã hoàn thành bài tập nộp tại repo GitHub: https://github.com/linhchi/web-lms-assignment1.git kèm mã nguồn API.', 8.5, 'Cấu trúc thư mục tốt, tuân thủ đúng chuẩn REST và trả mã HTTP 200/201 chuẩn xác.'),
('sub2', 'a1', 'u5', 'Mã nguồn nộp đồ án Flask REST API có kiểm tra xác thực JWT HS256 và middleware chặn deny-by-default.', 9.0, 'Rất tốt! Xử lý ngoại lệ đầy đủ và kiểm tra bảo mật đúng tiêu chuẩn.'),
('sub3', 'a2', 'u6', 'Báo cáo thiết kế ERD chuẩn 3NF và kịch bản truy vấn phân tích chỉ mục B-tree trên bảng lớn.', 9.5, 'Bài làm chỉn chu, có biểu đồ EXPLAIN ANALYZE so sánh chi phí trước và sau khi đánh chỉ mục.');

INSERT INTO classes (id, course_id, code, room, capacity, reserved_count, confirmed_count) VALUES
('lab_ai_101', 'c1', 'WEB101-L01', 'Phòng Lab 402 - Tòa Alpha', 2, 0, 0),
('seminar_sec', 'c3', 'SEC301-S01', 'Hội trường B - Tòa Beta', 3, 0, 0),
('db_tuning_lab', 'c2', 'DB201-L02', 'Phòng Máy 205 - Tòa Gamma', 5, 0, 0);

INSERT INTO quizzes (id, course_id, title, time_limit_seconds) VALUES
('quiz_c1_01', 'c1', 'Trắc nghiệm Kiến trúc REST & HTTP Headers', 1800),
('quiz_c2_01', 'c2', 'Trắc nghiệm Chuẩn hóa 3NF & Chỉ mục B-Tree', 2700),
('quiz_c3_01', 'c3', 'Trắc nghiệm Kiểm soát Xác thực & Chống IDOR', 2400);

-- Insert sample audit log
INSERT INTO audit_logs (id, event_type, user_id, ip_address, details) VALUES
('log_init_01', 'SYSTEM_INITIALIZATION', 'u1', '127.0.0.1', '{"message": "PostgreSQL database initialized successfully with full schema and seed data"}');

