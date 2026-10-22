import React, { useState, useEffect } from 'react';
import {
  User,
  Lock,
  History,
  Bell,
  Save,
  CheckCircle,
  AlertCircle,
  Camera,
} from 'lucide-react';
import Navbar from '../components/Navbar';
import { api } from '../services/api';

export default function AccountPage() {
  const [activeTab, setActiveTab] = useState('profile');
  const [profile, setProfile] = useState({
    fullName: '',
    email: '',
    phone: '',
    bio: '',
    avatarUrl: '',
    role: '',
  });
  const [passwords, setPasswords] = useState({
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [history, setHistory] = useState([]);
  const [notifications, setNotifications] = useState({
    emailNewCourses: true,
    emailAssignments: true,
    emailGradeUpdates: true,
  });
  const [message, setMessage] = useState({ type: '', text: '' });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getProfile()
      .then((data) => {
        setProfile(data.profile);
        setHistory(data.history || []);
        setNotifications(data.notifications || {});
        setLoading(false);
      })
      .catch((err) => {
        setMessage({ type: 'error', text: err.message || 'Không thể tải hồ sơ' });
        setLoading(false);
      });
  }, []);

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    setMessage({ type: '', text: '' });

    try {
      const res = await api.updateProfile({
        fullName: profile.fullName,
        phone: profile.phone,
        bio: profile.bio,
        avatarUrl: profile.avatarUrl,
      });
      setMessage({ type: 'success', text: res.message || 'Cập nhật thông tin thành công!' });
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Có lỗi xảy ra khi lưu thông tin.' });
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setMessage({ type: '', text: '' });

    if (passwords.newPassword !== passwords.confirmPassword) {
      setMessage({ type: 'error', text: 'Xác nhận mật khẩu mới không khớp.' });
      return;
    }

    try {
      const res = await api.changePassword(passwords.oldPassword, passwords.newPassword);
      setMessage({ type: 'success', text: res.message || 'Đổi mật khẩu thành công!' });
      setPasswords({ oldPassword: '', newPassword: '', confirmPassword: '' });
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Mật khẩu cũ không đúng hoặc mật khẩu quá ngắn.' });
    }
  };

  const handleToggleNotification = async (key) => {
    const updated = { ...notifications, [key]: !notifications[key] };
    setNotifications(updated);

    try {
      await api.updateNotifications(updated);
    } catch {
      // Revert if error
      setNotifications(notifications);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50/60 pb-16 font-sans">
      <Navbar user={profile} />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 mt-8 space-y-6">
        {/* Tiêu đề trang */}
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900">Quản lý Tài khoản</h1>
          <p className="text-sm text-slate-500 mt-1">
            Cập nhật hồ sơ cá nhân, bảo mật và tùy chọn hệ thống.
          </p>
        </div>

        {/* Thông báo Alert */}
        {message.text && (
          <div
            className={`p-4 rounded-xl flex items-center space-x-3 text-sm font-medium ${
              message.type === 'success'
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                : 'bg-rose-50 text-rose-700 border border-rose-200'
            }`}
          >
            {message.type === 'success' ? (
              <CheckCircle className="w-5 h-5 shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 shrink-0" />
            )}
            <span>{message.text}</span>
          </div>
        )}

        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden flex flex-col md:flex-row">
          {/* Cột Tabs Điều hướng bên trái */}
          <div className="w-full md:w-64 border-b md:border-b-0 md:border-r border-slate-200 bg-slate-50/50 p-4 space-y-1">
            {[
              { id: 'profile', label: 'Thông tin cá nhân', icon: User },
              { id: 'security', label: 'Đổi mật khẩu', icon: Lock },
              { id: 'history', label: 'Lịch sử học tập', icon: History },
              { id: 'notifications', label: 'Cài đặt thông báo', icon: Bell },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  setMessage({ type: '', text: '' });
                }}
                className={`w-full flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition ${
                  activeTab === tab.id
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            ))}
          </div>

          {/* Cột Nội dung bên phải */}
          <div className="flex-1 p-6 sm:p-8">
            {/* TAB 1: THÔNG TIN CÁ NHÂN */}
            {activeTab === 'profile' && (
              <form onSubmit={handleUpdateProfile} className="space-y-6">
                <div className="flex items-center space-x-5">
                  <div className="relative group">
                    <img
                      src={profile.avatarUrl}
                      alt={profile.fullName}
                      className="w-20 h-20 rounded-2xl object-cover ring-2 ring-slate-200"
                    />
                    <label className="absolute inset-0 bg-black/40 rounded-2xl opacity-0 group-hover:opacity-100 flex items-center justify-center cursor-pointer transition text-white">
                      <Camera className="w-5 h-5" />
                    </label>
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-800 text-base">{profile.fullName}</h3>
                    <p className="text-xs text-slate-500">{profile.email}</p>
                    <span className="inline-block mt-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                      Vai trò: {profile.role}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Họ và tên
                    </label>
                    <input
                      type="text"
                      value={profile.fullName}
                      onChange={(e) => setProfile({ ...profile, fullName: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-hidden"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Email (Cố định bảo vệ hệ thống)
                    </label>
                    <input
                      type="email"
                      value={profile.email}
                      disabled
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-100 text-slate-500 text-sm cursor-not-allowed"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Số điện thoại
                    </label>
                    <input
                      type="tel"
                      value={profile.phone}
                      onChange={(e) => setProfile({ ...profile, phone: e.target.value })}
                      placeholder="0912 345 678"
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-hidden"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Tiểu sử ngắn (Bio)
                    </label>
                    <textarea
                      rows={3}
                      value={profile.bio}
                      onChange={(e) => setProfile({ ...profile, bio: e.target.value })}
                      placeholder="Mô tả ngắn gọn về bản thân..."
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-hidden"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  className="inline-flex items-center space-x-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm rounded-xl transition shadow-xs"
                >
                  <Save className="w-4 h-4" />
                  <span>Lưu thay đổi</span>
                </button>
              </form>
            )}

            {/* TAB 2: ĐỔI MẬT KHẨU */}
            {activeTab === 'security' && (
              <form onSubmit={handleChangePassword} className="space-y-4 max-w-md">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Mật khẩu hiện tại
                  </label>
                  <input
                    type="password"
                    value={passwords.oldPassword}
                    onChange={(e) => setPasswords({ ...passwords, oldPassword: e.target.value })}
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-hidden"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Mật khẩu mới (Tối thiểu 8 ký tự)
                  </label>
                  <input
                    type="password"
                    value={passwords.newPassword}
                    onChange={(e) => setPasswords({ ...passwords, newPassword: e.target.value })}
                    required
                    minLength={8}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-hidden"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Xác nhận mật khẩu mới
                  </label>
                  <input
                    type="password"
                    value={passwords.confirmPassword}
                    onChange={(e) =>
                      setPasswords({ ...passwords, confirmPassword: e.target.value })
                    }
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-hidden"
                  />
                </div>

                <button
                  type="submit"
                  className="mt-2 inline-flex items-center space-x-2 px-5 py-2.5 bg-slate-900 hover:bg-indigo-600 text-white font-semibold text-sm rounded-xl transition shadow-xs"
                >
                  <Lock className="w-4 h-4" />
                  <span>Cập nhật mật khẩu</span>
                </button>
              </form>
            )}

            {/* TAB 3: LỊCH SỬ HỌC TẬP */}
            {activeTab === 'history' && (
              <div className="space-y-4">
                <h3 className="font-bold text-slate-800 text-base">Lịch sử đăng ký và điểm số</h3>
                <div className="overflow-x-auto border border-slate-200 rounded-xl">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 text-xs uppercase font-bold">
                      <tr>
                        <th className="px-4 py-3">Khóa học</th>
                        <th className="px-4 py-3">Ngày ghi danh</th>
                        <th className="px-4 py-3">Trạng thái</th>
                        <th className="px-4 py-3">Điểm số</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {history.map((row, idx) => (
                        <tr key={idx} className="hover:bg-slate-50/50">
                          <td className="px-4 py-3 font-semibold text-slate-800">
                            {row.courseTitle}
                          </td>
                          <td className="px-4 py-3 text-slate-500">{row.enrolledAt}</td>
                          <td className="px-4 py-3">
                            <span
                              className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-bold ${
                                row.status === 'Đã hoàn thành'
                                  ? 'bg-emerald-50 text-emerald-700'
                                  : 'bg-amber-50 text-amber-700'
                              }`}
                            >
                              {row.status}
                            </span>
                          </td>
                          <td className="px-4 py-3 font-bold text-slate-700">{row.score}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB 4: CÀI ĐẶT THÔNG BÁO */}
            {activeTab === 'notifications' && (
              <div className="space-y-5">
                <h3 className="font-bold text-slate-800 text-base">Tùy chọn nhận Email</h3>
                {[
                  {
                    key: 'emailNewCourses',
                    title: 'Khóa học mới ra mắt',
                    desc: 'Nhận email giới thiệu các khóa học chất lượng cao vừa được xuất bản.',
                  },
                  {
                    key: 'emailAssignments',
                    title: 'Thông báo bài tập & Hạn nộp',
                    desc: 'Nhận nhắc nhở hạn nộp bài tập để không bỏ lỡ điểm chuyên cần.',
                  },
                  {
                    key: 'emailGradeUpdates',
                    title: 'Cập nhật điểm số',
                    desc: 'Nhận thông báo ngay lập tức khi giảng viên công bố điểm số mới.',
                  },
                ].map((item) => (
                  <div
                    key={item.key}
                    className="flex items-center justify-between p-4 rounded-xl border border-slate-200"
                  >
                    <div>
                      <p className="font-semibold text-sm text-slate-800">{item.title}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{item.desc}</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={notifications[item.key] || false}
                        onChange={() => handleToggleNotification(item.key)}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-slate-200 peer-focus:outline-hidden rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
                    </label>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
