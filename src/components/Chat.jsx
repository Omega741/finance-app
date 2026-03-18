// MIT License - Copyright (c) 2024 Finance App

import { useState, useRef, useEffect } from 'react';
import { sendMessage } from '../ai/claudeChat';

const STORAGE_KEY = 'finance_chat_history';

const STARTERS = [
  'What are my biggest spending categories?',
  'How much am I saving each month on average?',
  'Where can I cut back to save more?',
  'What subscriptions am I paying for?',
  'How does my spending compare month to month?',
];

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    return [];
  }
}

export default function Chat({ transactions }) {
  const [messages, setMessages] = useState(loadHistory);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  }, [messages]);

  const send = async (text) => {
    const content = (text || input).trim();
    if (!content || loading) return;

    const userMsg = { role: 'user', content };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput('');
    setLoading(true);
    setError('');

    try {
      const reply = await sendMessage(next, transactions);
      setMessages([...next, { role: 'assistant', content: reply }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    setError('');
    localStorage.removeItem(STORAGE_KEY);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const autoResize = (e) => {
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
  };

  return (
    <div className="chat-wrapper">
      {messages.length > 0 && (
        <div className="chat-toolbar">
          <span className="chat-toolbar-info">{messages.length} message{messages.length !== 1 ? 's' : ''}</span>
          <button className="btn-clear-chat" onClick={clearChat}>Clear chat</button>
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <div className="chat-avatar-lg">AI</div>
            <p className="chat-intro">
              {transactions.length > 0
                ? `I have access to your ${transactions.length} transactions. Ask me anything about your finances.`
                : 'Upload a CSV first, then I can give you personalized financial advice based on your actual data.'}
            </p>
            {transactions.length > 0 && (
              <div className="chat-starters">
                {STARTERS.map(s => (
                  <button
                    key={s}
                    className="starter-btn"
                    onClick={() => send(s)}
                    disabled={loading}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`chat-row ${msg.role}`}>
            {msg.role === 'assistant' && <div className="chat-avatar">AI</div>}
            <div className="msg-bubble">
              {msg.content.split('\n').map((line, j) => (
                <p key={j} className={line === '' ? 'msg-spacer' : ''}>{line || '\u00A0'}</p>
              ))}
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-row assistant">
            <div className="chat-avatar">AI</div>
            <div className="msg-bubble loading-bubble">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          </div>
        )}

        {error && <div className="chat-error">{error}</div>}

        <div ref={bottomRef} />
      </div>

      <div className="chat-input-wrap">
        <textarea
          className="chat-textarea"
          value={input}
          onChange={e => { setInput(e.target.value); autoResize(e); }}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your finances... (Enter to send, Shift+Enter for newline)"
          rows={1}
          disabled={loading}
        />
        <button
          className="chat-send-btn"
          onClick={() => send()}
          disabled={loading || !input.trim()}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
