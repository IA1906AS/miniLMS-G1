import React from 'react';
import { BookOpen, LogOut, Bell, Compass } from 'lucide-react';
import { removeAuthToken } from '../services/api';

export default function Navbar({ user }) {
  const roleBadgeColor = {
    ADMIN: 'bg-rose-500/10 text-rose-600 border-rose-200',
    INSTRUCTOR: 'bg-purple-500/10 text-purple-600 border-purple-200',
    STUDENT: 'bg-emerald-500/10 text-emerald-600 border-emerald-200',
  }[user?.role] || 'bg-slate-100 text-slate-700';

  const handleLogout = () => {
    removeAuthToken();
    window.location.href = '/login';
  };

  return (
    <header className="sticky top-0 z-50 backdrop-blur-md bg-white/85 border-b border-slate-200/80 shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand Logo */}
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-200">
            <BookOpen className="w-5 h-5" />
          </div>
          <span className="font-bold text-xl bg-gradient-to-r from-slate-900 to-slate-700 bg-clip-text text-transparent">
            miniLMS
          </span>
        </div>

        {/* Navigation links */}
        <nav className="hidden md:flex items-center space-x-6">
          <a href="/home" className="text-sm font-semibold text-indigo-600 flex items-center space-x-1.5">
            <Compass className="w-4 h-4" />
            <span>Trang chủ</span>
          </a>
          <a href="/courses" className="text-sm font-medium text-slate-600 hover:text-slate-900 transition">
            Khóa học
          </a>
          <a href="/account" className="text-sm font-medium text-slate-600 hover:text-slate-900 transition">
            Tài khoản
          </a>
        </nav>

        {/* User Badge & Profile */}
        <div className="flex items-center space-x-4">
          <button className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-full transition relative">
            <Bell className="w-5 h-5" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-indigo-600 rounded-full animate-ping" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-indigo-600 rounded-full" />
          </button>

          <div className="flex items-center space-x-3 pl-3 border-l border-slate-200">
            <a href="/account" className="flex items-center space-x-3 group">
              <img
                src={user?.avatarUrl || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150'}
                alt={user?.fullName || 'Avatar'}
                className="w-9 h-9 rounded-full object-cover ring-2 ring-indigo-500/20 group-hover:ring-indigo-500 transition"
              />
              <div className="hidden sm:block text-left">
                <p className="text-sm font-semibold text-slate-800 leading-none group-hover:text-indigo-600 transition">
                  {user?.fullName}
                </p>
                <span className={`inline-block mt-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${roleBadgeColor}`}>
                  {user?.role}
                </span>
              </div>
            </a>

            <button
              onClick={handleLogout}
              title="Đăng xuất"
              className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
