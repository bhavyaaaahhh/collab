import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import type { Message } from "../types";

function authorClass(sender: string, reviewers: string[]): string {
  if (sender === "user" || sender === "system" || sender === "executor") return sender;
  return reviewers.indexOf(sender) === 1 ? "agent-b" : "agent-a";
}

export function Chat({ messages, reviewers, live, onSend, children }: {
  messages: Message[]; reviewers: string[]; live: boolean; onSend: (text: string) => void; children?: ReactNode;
}) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [messages.length]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    onSend(text);
    setText("");
  }

  return (
    <section className="chat">
      <div className="messages">
        {messages.length === 0 && <p className="muted">No messages yet — the agents are reading the task.</p>}
        {messages.map((m) => (
          <div key={m.seq} className={`msg ${authorClass(m.sender, reviewers)}`}>
            <div className="sender">{m.sender} <span className="muted">{new Date(m.at * 1000).toLocaleTimeString()}</span></div>
            <div className="body">{m.text}</div>
          </div>
        ))}
        <div ref={end} />
      </div>
      {children}
      {live && (
        <form className="composer" onSubmit={submit}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Message both agents…" />
          <button type="submit">Send</button>
        </form>
      )}
    </section>
  );
}
