import React, { useState, useEffect } from 'react';
import {
  PlayCircle,
  CheckCircle2,
  Clock,
  Award,
  ArrowRight,
  Sparkles,
  BookOpen,
} from 'lucide-react';
import Navbar from '../components/Navbar';
import { api } from '../services/api';

export default function HomePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getHome()
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || 'Không thể tải dữ liệu trang chủ');
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center space-y-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
          <p className="text-sm font-medium text-slate-500">Đang tải bảng điều khiển...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="p-6 bg-white rounded-2xl shadow-sm border border-rose-200 text-center max-w-md">
          <p className="text-rose-600 font-semibold mb-2">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium"
          >
            Thử lại
          </button>
        </div>
      </div>
    );
  }

  const { user, stats, enrolledCourses, featuredCourses } = data || {};

  return (
    <div className="min-h-screen bg-slate-50/60 font-sans pb-16">
      <Navbar user={user} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-8 space-y-10">
        {/* 1. Phần Chào mừng (Hero Section) */}
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-indigo-700 via-indigo-600 to-violet-600 p-8 sm:p-10 text-white shadow-xl shadow-indigo-950/10">
          <div className="absolute right-0 top-0 -mt-10 -mr-10 w-96 h-96 rounded-full bg-white/10 blur-3xl pointer-events-none" />

          <div className="relative z-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div className="space-y-2 max-w-2xl">
              <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-white/15 backdrop-blur-md text-xs font-semibold tracking-wide">
                <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                <span>Chào mừng bạn quay trở lại!</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
                Xin chào, {user?.fullName}! 👋
              </h1>
              <p className="text-indigo-100 text-sm sm:text-base leading-relaxed">
                Hôm nay là một ngày tuyệt vời để bứt phá kỹ năng mới. Hãy tiếp tục các bài học đang
                dang dở nhé!
              </p>
            </div>

            <div className="flex items-center space-x-3 bg-white/10 backdrop-blur-md p-2 pr-4 rounded-2xl border border-white/20">
              <img
                src={user?.avatarUrl}
                alt={user?.fullName}
                className="w-12 h-12 rounded-xl object-cover border border-white/30"
              />
              <div>
                <p className="font-semibold text-sm leading-snug">{user?.fullName}</p>
                <span className="text-[11px] text-indigo-200 uppercase font-bold tracking-wider">
                  Vai trò: {user?.role}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* 2. Thống kê nhanh (Dashboard Stats) */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
          {[
            {
              label: 'Khóa học hoàn thành',
              value: stats?.completedCourses || 0,
              icon: CheckCircle2,
              color: 'text-emerald-600',
              bg: 'bg-emerald-50',
            },
            {
              label: 'Đang theo học',
              value: stats?.inProgressCourses || 0,
              icon: BookOpen,
              color: 'text-indigo-600',
              bg: 'bg-indigo-50',
            },
            {
              label: 'Tổng giờ tích lũy',
              value: `${stats?.totalHours || 0}h`,
              icon: Clock,
              color: 'text-amber-600',
              bg: 'bg-amber-50',
            },
            {
              label: 'Chứng chỉ đạt được',
              value: stats?.certificates || 0,
              icon: Award,
              color: 'text-rose-600',
              bg: 'bg-rose-50',
            },
          ].map((item, idx) => (
            <div
              key={idx}
              className="p-5 rounded-2xl bg-white border border-slate-200/80 shadow-xs hover:shadow-md transition"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs sm:text-sm font-medium text-slate-500">{item.label}</span>
                <div className={`p-2.5 rounded-xl ${item.bg}`}>
                  <item.icon className={`w-5 h-5 ${item.color}`} />
                </div>
              </div>
              <p className="text-2xl sm:text-3xl font-bold text-slate-900 mt-2">{item.value}</p>
            </div>
          ))}
        </section>

        {/* 3. Khóa học đang học (Enrolled Courses) */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl sm:text-2xl font-bold text-slate-900">Khóa học của bạn</h2>
              <p className="text-xs sm:text-sm text-slate-500">Tiến độ và bài học gần đây nhất</p>
            </div>
          </div>

          {enrolledCourses?.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-2xl border border-dashed border-slate-300">
              <BookOpen className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-600 font-medium">Bạn chưa đăng ký khóa học nào.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {enrolledCourses?.map((course) => (
                <div
                  key={course.id}
                  className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs hover:shadow-lg transition-all duration-300 flex flex-col justify-between group"
                >
                  <div>
                    <div className="relative h-44 overflow-hidden">
                      <img
                        src={course.thumbnail}
                        alt={course.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                      />
                      <span className="absolute top-3 right-3 text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-900/70 backdrop-blur-md text-white">
                        {course.progress}% hoàn thành
                      </span>
                    </div>

                    <div className="p-5 space-y-3">
                      <h3 className="font-bold text-lg text-slate-900 line-clamp-1 group-hover:text-indigo-600 transition">
                        {course.title}
                      </h3>
                      <p className="text-xs text-slate-500">
                        Giảng viên:{' '}
                        <span className="font-medium text-slate-700">{course.instructor}</span>
                      </p>

                      {/* Thanh progress bar */}
                      <div className="space-y-1.5">
                        <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500 rounded-full transition-all duration-700"
                            style={{ width: `${course.progress}%` }}
                          />
                        </div>
                      </div>

                      <div className="text-xs text-slate-500 pt-1 flex items-center space-x-1.5">
                        <PlayCircle className="w-4 h-4 text-indigo-500 shrink-0" />
                        <span className="truncate">{course.nextLessonTitle}</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-5 pt-0">
                    <a
                      href={`/learn/${course.id}/${course.nextLessonId}`}
                      className="w-full inline-flex items-center justify-center space-x-2 py-2.5 px-4 rounded-xl bg-indigo-50 text-indigo-600 font-semibold text-sm hover:bg-indigo-600 hover:text-white transition shadow-xs"
                    >
                      <span>Tiếp tục học</span>
                      <ArrowRight className="w-4 h-4" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 4. Khóa học gợi ý / Nổi bật */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl sm:text-2xl font-bold text-slate-900">Khóa học gợi ý</h2>
              <p className="text-xs sm:text-sm text-slate-500">
                Mở rộng kiến thức với các khóa học được tuyển chọn
              </p>
            </div>
            <a
              href="/courses"
              className="text-sm font-semibold text-indigo-600 hover:text-indigo-700 inline-flex items-center space-x-1"
            >
              <span>Xem tất cả</span>
              <ArrowRight className="w-4 h-4" />
            </a>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {featuredCourses?.map((course) => (
              <div
                key={course.id}
                className="bg-white rounded-2xl border border-slate-200 p-4 hover:shadow-lg transition space-y-3 flex flex-col justify-between"
              >
                <div className="space-y-3">
                  <img
                    src={course.thumbnail}
                    alt={course.title}
                    className="w-full h-40 object-cover rounded-xl"
                  />
                  {course.isFeatured && (
                    <span className="inline-block text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full uppercase">
                      Nổi bật
                    </span>
                  )}
                  <h4 className="font-bold text-slate-800 line-clamp-1">{course.title}</h4>
                  <p className="text-xs text-slate-500 line-clamp-2">
                    {course.description || 'Nội dung bài học chuẩn kiến trúc bảo mật đa tầng.'}
                  </p>
                </div>

                <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                  <span className="text-xs text-slate-500 font-medium">
                    Thời lượng: {course.duration}
                  </span>
                  <button className="px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-indigo-600 text-white font-medium text-xs transition">
                    Đăng ký ngay
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
