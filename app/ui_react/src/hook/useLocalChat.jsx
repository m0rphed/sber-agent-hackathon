// src/useLocalChat.js
import { useEffect, useState } from 'react';
import {
  createEmptySession,
  loadSessionsFromStorage,
  saveSessionsToStorage,
} from '../elements/storage';

const initialSessions = loadSessionsFromStorage();

export function useLocalChat() {
  const [sessions, setSessions] = useState(initialSessions);
  const [currentSessionId, setCurrentSessionId] = useState(
    initialSessions[0] ? initialSessions[0].id : null
  );

  // любое изменение sessions — сохраняем в localStorage
  useEffect(() => {
    saveSessionsToStorage(sessions);
  }, [sessions]);

  const currentSession =
    sessions.find((s) => s.id === currentSessionId) || sessions[0] || null;

  function createSession() {
    const newSession = createEmptySession();
    setSessions((prev) => [newSession, ...prev]);
    setCurrentSessionId(newSession.id);
  }

  function selectSession(id) {
    setCurrentSessionId(id);
  }

  function renameSession(id, title) {
    const now = new Date().toISOString();
    setSessions((prev) =>
      prev.map((s) =>
        s.id === id ? { ...s, title, updatedAt: now } : s
      )
    );
  }

  function appendMessage(sessionId, message) {
    const now = new Date().toISOString();
    setSessions((prev) =>
      prev.map((s) =>
        s.id === sessionId
          ? {
              ...s,
              messages: [...s.messages, message],
              updatedAt: now,
            }
          : s
      )
    );
  }

  return {
    sessions,
    currentSession,
    currentSessionId,
    createSession,
    selectSession,
    renameSession,
    appendMessage,
  };
}
