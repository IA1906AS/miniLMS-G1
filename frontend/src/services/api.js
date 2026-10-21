/**
 * API Service helper for miniLMS Frontend.
 * Automatically attaches JWT Bearer token from localStorage.
 */

const API_BASE = '/api';

export const getAuthToken = () => localStorage.getItem('accessToken');
export const setAuthToken = (token) => localStorage.setItem('accessToken', token);
export const removeAuthToken = () => localStorage.removeItem('accessToken');

export async function fetchWithAuth(endpoint, options = {}) {
  const token = getAuthToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    removeAuthToken();
    window.location.href = '/login';
    throw new Error('UNAUTHENTICATED');
  }

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || 'Request failed');
  }

  return data;
}

export const api = {
  // Authentication
  login: async (email, password) => {
    const res = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Đăng nhập thất bại');
    setAuthToken(data.accessToken);
    return data;
  },

  // Home Dashboard
  getHome: () => fetchWithAuth('/home'),

  // Account / Profile
  getProfile: () => fetchWithAuth('/account/profile'),
  updateProfile: (profileData) =>
    fetchWithAuth('/account/profile', {
      method: 'PUT',
      body: JSON.stringify(profileData),
    }),
  changePassword: (oldPassword, newPassword) =>
    fetchWithAuth('/account/change-password', {
      method: 'PUT',
      body: JSON.stringify({ oldPassword, newPassword }),
    }),
  updateNotifications: (notificationSettings) =>
    fetchWithAuth('/account/notifications', {
      method: 'PUT',
      body: JSON.stringify(notificationSettings),
    }),
};
