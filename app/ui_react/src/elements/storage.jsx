// src/storage.js

const STORAGE_KEY = 'city-assistant-guest-chats-v1';

function generateId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'id-' + Date.now() + '-' + Math.random().toString(16).slice(2);
}

export function createEmptySession() {
  const now = new Date().toISOString();
  return {
    id: generateId(),
    title: 'Новый диалог',
    createdAt: now,
    updatedAt: now,
    messages: [], // массив объектов { id, role: 'user' | 'assistant', content, createdAt }
  };
}

export function loadSessionsFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      const first = createEmptySession();
      saveSessionsToStorage([first]);
      return [first];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      throw new Error('Invalid data format');
    }
    return parsed;
  } catch (e) {
    console.warn('Не удалось прочитать чаты из localStorage, создаю новый', e);
    const first = createEmptySession();
    saveSessionsToStorage([first]);
    return [first];
  }
}

export function saveSessionsToStorage(sessions) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch (e) {
    console.warn('Не удалось сохранить чаты в localStorage', e);
  }
}
