import apiClient from './client';

export function listBookings() {
  // Endpoint paginato (DRF PageNumberPagination): normalizziamo restituendo l'array.
  return apiClient.get('/bookings/').then((res) => res.data.results ?? res.data);
}

export function getBooking(id) {
  return apiClient.get(`/bookings/${id}/`).then((res) => res.data);
}

export function confirmBooking(id) {
  return apiClient.post(`/bookings/${id}/confirm/`).then((res) => res.data);
}

export function cancelBooking(id) {
  return apiClient.post(`/bookings/${id}/cancel/`).then((res) => res.data);
}
