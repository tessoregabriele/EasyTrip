import apiClient from './client';

export function register(payload) {
  return apiClient.post('/auth/register/', payload).then((res) => res.data);
}

export function login(username, password) {
  return apiClient.post('/auth/login/', { username, password }).then((res) => res.data);
}

export function getMe() {
  return apiClient.get('/auth/me/').then((res) => res.data);
}

export function updateMe(payload) {
  return apiClient.patch('/auth/me/', payload).then((res) => res.data);
}
