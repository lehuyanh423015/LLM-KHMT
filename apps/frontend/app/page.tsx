"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, User, ChevronDown, ChevronUp, Zap, Star } from "lucide-react";
import { sendMessage, fetchProfileMemory, fetchHealth, setMode, setExperiment } from "../lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type Profile = {
  session_id: string;
  budget: string;
  preferred_category: string;
  preferred_color: string;
  priorities: string;
  dislikes: string;
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [isMemoryOpen, setIsMemoryOpen] = useState(false);
  
  // Model Mode states
  const [activeMode, setActiveMode] = useState<"fast" | "quality">("fast");
  const [activeModel, setActiveModel] = useState<string>("");
  
  // Experiment states
  const [enableMemory, setEnableMemory] = useState(true);
  const [enableRecentContext, setEnableRecentContext] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Initialize Session ID
    let currentSession = localStorage.getItem("chat_session_id");
    if (!currentSession) {
      currentSession = "session-" + Math.random().toString(36).substring(2, 9);
      localStorage.setItem("chat_session_id", currentSession);
    }
    setSessionId(currentSession);
    
    // Initial profile & health load
    fetchProfileMemory(currentSession).then(setProfile).catch(console.error);
    fetchHealth()
      .then((data) => {
        setActiveMode(data.active_mode);
        setActiveModel(data.active_model);
        if (data.experiments) {
          setEnableMemory(data.experiments.enable_memory);
          setEnableRecentContext(data.experiments.enable_recent_context);
        }
      })
      .catch(console.error);
  }, []);

  const handleToggleMode = async () => {
    try {
      const newMode = activeMode === "fast" ? "quality" : "fast";
      const res = await setMode(newMode);
      setActiveMode(res.active_mode);
      setActiveModel(res.active_model);
    } catch (e) {
      console.error("Failed to toggle mode:", e);
    }
  };

  const handleToggleExperiment = async (type: 'memory' | 'context', value: boolean) => {
    try {
      const newMemory = type === 'memory' ? value : enableMemory;
      const newContext = type === 'context' ? value : enableRecentContext;
      const res = await setExperiment(newMemory, newContext);
      setEnableMemory(res.experiments.enable_memory);
      setEnableRecentContext(res.experiments.enable_recent_context);
    } catch (e) {
      console.error("Failed to toggle experiment:", e);
    }
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!input.trim() || isLoading || !sessionId) return;

    const userMsg: Message = { id: Date.now().toString(), role: "user", content: input };
    setMessages((prev: Message[]) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await sendMessage(userMsg.content, sessionId);
      const aiMsg: Message = { id: (Date.now() + 1).toString(), role: "assistant", content: response.answer };
      setMessages((prev: Message[]) => [...prev, aiMsg]);
      
      // Refresh memory panel silently after response
      fetchProfileMemory(sessionId).then(setProfile).catch(console.error);
    } catch (error) {
      console.error("Error sending message:", error);
      const errorMsg: Message = { id: (Date.now() + 1).toString(), role: "assistant", content: "Sorry, there was an error processing your request." };
      setMessages((prev: Message[]) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="flex flex-col h-screen max-h-screen bg-neutral-50 dark:bg-neutral-900 border-x border-neutral-200 dark:border-neutral-800 max-w-4xl mx-auto w-full shadow-lg relative">
      <header className="p-4 border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-black font-semibold flex items-center justify-between">
        <h1 className="text-lg flex items-center gap-3">
          Shopping Assistant
          {activeModel && (
            <button
              onClick={handleToggleMode}
              title={`Switch Mode. Currently running: ${activeModel}`}
              className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-bold rounded-md border transition-all ${
                activeMode === "fast" 
                  ? "bg-amber-100/50 text-amber-700 border-amber-200 hover:bg-amber-100 dark:bg-amber-900/30 dark:text-amber-500 dark:border-amber-800" 
                  : "bg-purple-100/50 text-purple-700 border-purple-200 hover:bg-purple-100 dark:bg-purple-900/30 dark:text-purple-400 dark:border-purple-800"
              }`}
            >
              {activeMode === "fast" ? <Zap size={14} /> : <Star size={14} />}
              {activeMode.toUpperCase()}
            </button>
          )}
        </h1>
        <div className="flex gap-2">
          {sessionId && (
            <div className="text-xs font-mono px-2 py-1 bg-neutral-100 text-neutral-600 rounded dark:bg-neutral-800 dark:text-neutral-400">
              ID: {sessionId}
            </div>
          )}
          <div className="text-xs font-normal px-2 py-1 bg-blue-100 text-blue-800 rounded-full dark:bg-blue-900 dark:text-blue-200">
            Agent Online
          </div>
        </div>
      </header>

      {/* Customer Memory Debug Panel */}
      <div className="border-b border-neutral-200 dark:border-neutral-800 bg-emerald-50 dark:bg-emerald-950/20">
        <button 
          onClick={() => setIsMemoryOpen(!isMemoryOpen)}
          className="w-full flex items-center justify-between p-3 text-sm font-medium text-emerald-800 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-900/40 transition-colors"
        >
          <div className="flex items-center gap-2">
            <User size={16} />
            <span>Customer Profile Memory (Debug)</span>
          </div>
          {isMemoryOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        
        {isMemoryOpen && (
          <div className="p-4 pt-0">
            <div className="mb-4 pb-4 border-b border-emerald-200/50 dark:border-emerald-800/50">
              <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-800 dark:text-emerald-500 mb-3">Experiment Controls</h3>
              <div className="flex flex-col gap-2 sm:flex-row sm:gap-6">
                <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300 cursor-pointer">
                  <input 
                    type="checkbox" 
                    checked={enableMemory} 
                    onChange={(e) => handleToggleExperiment('memory', e.target.checked)}
                    className="rounded border-emerald-500 text-emerald-600 focus:ring-emerald-500 bg-transparent"
                  />
                  <span>Enable Memory Extraction</span>
                </label>
                <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300 cursor-pointer">
                  <input 
                    type="checkbox" 
                    checked={enableRecentContext} 
                    onChange={(e) => handleToggleExperiment('context', e.target.checked)}
                    className="rounded border-emerald-500 text-emerald-600 focus:ring-emerald-500 bg-transparent"
                  />
                  <span>Enable Conversational Context</span>
                </label>
              </div>
            </div>

            {profile ? (
              <div className="grid grid-cols-2 gap-4 text-sm text-neutral-700 dark:text-neutral-300">
                <div>
                  <span className="font-semibold text-neutral-900 dark:text-white">Budget:</span> {profile.budget}
                </div>
                <div>
                  <span className="font-semibold text-neutral-900 dark:text-white">Category:</span> {profile.preferred_category}
                </div>
                <div>
                  <span className="font-semibold text-neutral-900 dark:text-white">Color:</span> {profile.preferred_color}
                </div>
                <div>
                  <span className="font-semibold text-neutral-900 dark:text-white">Priorities:</span> {profile.priorities}
                </div>
                <div className="col-span-2">
                  <span className="font-semibold text-neutral-900 dark:text-white">Dislikes:</span> {profile.dislikes}
                </div>
              </div>
            ) : (
              <div className="text-sm text-neutral-500 italic">No memory profile has been extracted yet.</div>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-neutral-400 text-center">
            <p className="mb-2">Hello! I am your Shopping Assistant.</p>
            <p className="text-sm">Try asking me: "I want a laptop under 20 million for gaming."</p>
          </div>
        ) : (
          messages.map((m: Message) => (
            <div
              key={m.id}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2 overflow-hidden break-words whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-blue-600 text-white rounded-br-none"
                    : "bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-bl-none text-neutral-800 dark:text-neutral-200 [&>p]:mb-2 [&>p:last-child]:mb-0 [&>ul]:list-disc [&>ul]:ml-5 [&>ul]:mb-2 [&>ol]:list-decimal [&>ol]:ml-5 [&>ol]:mb-2 [&>li]:mb-1 [&>h3]:font-bold [&>h3]:text-lg [&>h3]:mb-2 [&>strong]:font-bold"
                }`}
              >
                {m.role === "assistant" ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {m.content}
                  </ReactMarkdown>
                ) : (
                  m.content
                )}
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex justify-start">
             <div className="max-w-[80%] rounded-2xl px-4 py-2 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-bl-none text-neutral-500 flex space-x-2 items-center">
                <div className="w-2 h-2 rounded-full bg-neutral-400 animate-bounce"></div>
                <div className="w-2 h-2 rounded-full bg-neutral-400 animate-bounce" style={{ animationDelay: "150ms" }}></div>
                <div className="w-2 h-2 rounded-full bg-neutral-400 animate-bounce" style={{ animationDelay: "300ms" }}></div>
             </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 bg-white dark:bg-black border-t border-neutral-200 dark:border-neutral-800">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            className="flex-1 rounded-full border border-neutral-300 dark:border-neutral-700 bg-transparent px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim() || !sessionId}
            className="rounded-full bg-blue-600 p-3 text-white transition-colors hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center flex-shrink-0"
          >
            <Send size={20} />
          </button>
        </form>
      </div>
    </main>
  );
}
