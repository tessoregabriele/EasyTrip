import apiClient from './client';

export function listConversations() {
  // L'endpoint è paginato (DRF PageNumberPagination): normalizziamo qui
  // restituendo direttamente l'array, così le pagine non devono saperlo.
  return apiClient.get('/conversations/').then((res) => res.data.results ?? res.data);
}

export function getConversation(id) {
  return apiClient.get(`/conversations/${id}/`).then((res) => res.data);
}

export function createConversation(title = '') {
  return apiClient.post('/conversations/', { title }).then((res) => res.data);
}

export function sendMessage(conversationId, content) {
  return apiClient
    .post(`/conversations/${conversationId}/send_message/`, { content })
    .then((res) => res.data);
}
