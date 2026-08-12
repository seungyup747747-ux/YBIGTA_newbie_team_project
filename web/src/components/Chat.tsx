"use client";

import { FormEvent, useMemo, useState } from "react";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type ToolTrace = {
  tool: string;
  args: Record<string, unknown>;
  source: string;
};

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "서울 날씨 데이터를 MCP Tool로 조회해서 답변합니다. 예: 현재 가장 최근 날씨 데이터는 뭐야?",
    },
  ]);
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [toolTrace, setToolTrace] = useState<ToolTrace | null>(null);

  const examples = useMemo(
    () => [
      "현재 가장 최근 날씨 데이터는 뭐야?",
      "최근 일주일 동안 날씨 위험도 집계를 보여줘.",
    ],
    [],
  );

  async function submit(nextQuestion: string) {
    const trimmed = nextQuestion.trim();

    if (!trimmed || isLoading) {
      return;
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
    };

    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: trimmed }),
      });

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.error ?? "요청에 실패했습니다.");
      }

      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: payload.answer,
        },
      ]);
      setToolTrace({
        tool: payload.toolCall.tool,
        args: payload.toolCall.args,
        source: payload.toolResult.source,
      });
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content:
            error instanceof Error
              ? error.message
              : "알 수 없는 오류가 발생했습니다.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(question);
  }

  return (
    <main className="min-h-screen bg-[#f7f7f3] text-[#1f2528]">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <header className="border-b border-[#d9d8cf] pb-5">
          <p className="text-sm font-medium text-[#66746a]">YBIGTA Agent</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-normal">
            Data Analysis Agent
          </h1>
        </header>

        <section className="grid flex-1 gap-4 py-5 lg:grid-cols-[1fr_280px]">
          <div className="flex min-h-[560px] flex-col overflow-hidden border border-[#d9d8cf] bg-white">
            <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={
                    message.role === "user"
                      ? "ml-auto max-w-[78%] bg-[#1f6f64] px-4 py-3 text-white"
                      : "mr-auto max-w-[86%] border border-[#d9d8cf] bg-[#fafaf7] px-4 py-3"
                  }
                >
                  <p className="mb-1 text-xs font-semibold uppercase tracking-normal opacity-70">
                    {message.role === "user" ? "User" : "Agent"}
                  </p>
                  <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6">
                    {message.content}
                  </pre>
                </div>
              ))}
            </div>

            <form
              onSubmit={onSubmit}
              className="border-t border-[#d9d8cf] bg-[#fbfbf8] p-3"
            >
              <div className="flex gap-2">
                <input
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="질문을 입력하세요..."
                  className="min-h-12 flex-1 border border-[#c9c8bf] bg-white px-3 text-sm outline-none focus:border-[#1f6f64]"
                />
                <button
                  type="submit"
                  disabled={isLoading}
                  className="min-h-12 w-24 bg-[#1f2528] px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#9a9a91]"
                >
                  {isLoading ? "분석중" : "전송"}
                </button>
              </div>
            </form>
          </div>

          <aside className="space-y-4">
            <section className="border border-[#d9d8cf] bg-white p-4">
              <h2 className="text-sm font-semibold">캡처용 질문</h2>
              <div className="mt-3 space-y-2">
                {examples.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => submit(example)}
                    className="w-full border border-[#d9d8cf] bg-[#fafaf7] px-3 py-2 text-left text-sm leading-5 hover:border-[#1f6f64]"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </section>

            <section className="border border-[#d9d8cf] bg-white p-4">
              <h2 className="text-sm font-semibold">MCP Tool Trace</h2>
              {toolTrace ? (
                <dl className="mt-3 space-y-3 text-sm">
                  <div>
                    <dt className="text-[#66746a]">Tool</dt>
                    <dd className="font-mono">{toolTrace.tool}</dd>
                  </div>
                  <div>
                    <dt className="text-[#66746a]">Source</dt>
                    <dd className="font-mono">{toolTrace.source}</dd>
                  </div>
                  <div>
                    <dt className="text-[#66746a]">Args</dt>
                    <dd>
                      <pre className="mt-1 overflow-auto bg-[#f4f4ef] p-2 text-xs">
                        {JSON.stringify(toolTrace.args, null, 2)}
                      </pre>
                    </dd>
                  </div>
                </dl>
              ) : (
                <p className="mt-3 text-sm text-[#66746a]">
                  질문을 보내면 호출된 MCP Tool이 표시됩니다.
                </p>
              )}
            </section>
          </aside>
        </section>
      </div>
    </main>
  );
}
