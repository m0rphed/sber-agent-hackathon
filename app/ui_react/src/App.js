// src/App.jsx
import React, { useState } from 'react';
import { useLocalChat } from './hook/useLocalChat';
import './index.css';

function generateMessageId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'msg-' + Date.now() + '-' + Math.random().toString(16).slice(2);
}

// Станет:
async function sendToAssistant(history, currentSessionId) {
  const lastUser = history[history.length - 1];

  const res = await fetch('http://localhost:8000/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      chat_id: currentSessionId,     // id диалога из фронта
      message: lastUser.content,
      graph_id: 'supervisor',        // или 'hybrid', если нужно
    }),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(errText || 'Ошибка ответа API');
  }

  const data = await res.json(); // { reply: "..." }

  return {
    id: generateMessageId(),
    role: 'assistant',
    content: data.reply,
    createdAt: new Date().toISOString(),
  };
}


// ЗАГЛУШКА: здесь ты потом подставишь реальный запрос к backend / LLM
// async function sendToAssistantStub(messages) {
//   const lastUser = messages[messages.length - 1];
//   return new Promise((resolve) => {
//     setTimeout(() => {
//       resolve({
//         id: generateMessageId(),
//         role: 'assistant',
//         content:
//           'Это заглушка ответа ассистента.\n\nВаш вопрос: ' +
//           lastUser.content,
//         createdAt: new Date().toISOString(),
//       });
//     }, 800);
//   });
// }

/*
// Пример реального вызова API (потом заменишь stub):

async function sendToAssistant(messages) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error('Ошибка запроса к ассистенту');
  const data = await res.json();
  return {
    id: data.id,
    role: 'assistant',
    content: data.content,
    createdAt: data.createdAt,
  };
}
*/

export default function App() {
  const {
    sessions,
    currentSession,
    currentSessionId,
    createSession,
    selectSession,
    renameSession,
    appendMessage,
  } = useLocalChat();

  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);

  if (!currentSession) {
    return (
      <div className="app-root">
        <button onClick={createSession}>Создать первый диалог</button>
      </div>
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || !currentSessionId) return;

    setInput('');
    const now = new Date().toISOString();

    const userMessage = {
      id: generateMessageId(),
      role: 'user',
      content: text,
      createdAt: now,
    };

    // 1. сохраняем пользовательское сообщение
    appendMessage(currentSessionId, userMessage);

    // 2. если это первое сообщение в диалоге — используем его как заголовок
    if (!currentSession.messages || currentSession.messages.length === 0) {
      renameSession(currentSessionId, text.slice(0, 50));
    }

    // 3. запрашиваем ответ ассистента
    setIsSending(true);
    try {
      const history = [...currentSession.messages, userMessage];

      // сейчас — заглушка
      const reply = await sendToAssistant(history);

      // потом можно заменить:
      // const reply = await sendToAssistant(history);

      appendMessage(currentSessionId, reply);
    } catch (err) {
      console.error(err);
      const errorReply = {
        id: generateMessageId(),
        role: 'assistant',
        content:
          'Произошла ошибка при обращении к сервису. Попробуйте ещё раз чуть позже.',
        createdAt: new Date().toISOString(),
      };
      appendMessage(currentSessionId, errorReply);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="app-root">
      {/* Левый сайдбар со списком диалогов */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>Диалоги</h2>
          <button onClick={createSession}>Новый диалог</button>
        </div>

        <div className="session-list">
          {sessions.map((s) => (
            <button
              key={s.id}
              className={
                'session-item' +
                (s.id === currentSessionId ? ' session-item--active' : '')
              }
              onClick={() => selectSession(s.id)}
            >
              <div className="session-title">{s.title}</div>
              <div className="session-date">
                {new Date(s.updatedAt).toLocaleString('ru-RU')}
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* Основная область чата */}
      <main className="chat">
        <header className="chat-header">
          <h1>{currentSession.title}</h1>
          <span className="chat-subtitle">
            Помощник по социальным и государственным услугам
          </span>
        </header>

        <div className="chat-messages">
          {currentSession.messages.map((m) => (
            <div
              key={m.id}
              className={
                'message ' +
                (m.role === 'user' ? 'message--user' : 'message--assistant')
              }
            >
              <div className="message-bubble">
                <pre className="message-text">{m.content}</pre>
                <div className="message-meta">
                  {m.role === 'user' ? 'Вы' : 'Ассистент'} ·{' '}
                  {new Date(m.createdAt).toLocaleTimeString('ru-RU', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </div>
              </div>
            </div>
          ))}
          {isSending && (
            <div className="message message--assistant">
              <div className="message-bubble">
                <span className="typing-indicator">Ассистент печатает…</span>
              </div>
            </div>
          )}
        </div>

        <form className="chat-input" onSubmit={handleSubmit}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Опишите вашу ситуацию или вопрос об услугах…"
            rows={2}
          />
          <button type="submit" disabled={!input.trim() || isSending}>
            Отправить
          </button>
        </form>
      </main>
    </div>
  );
}
