import { callMcpTool, McpToolCall, McpToolResult } from "./mcpClient";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type AgentResponse = {
  answer: string;
  toolCall: McpToolCall;
  toolResult: McpToolResult;
};

type WeatherObservation = {
  location?: string;
  observed_at?: string;
  temperature?: number;
  apparent_temperature?: number;
  relative_humidity?: number;
  precipitation?: number;
  wind_speed?: number;
  risk_score?: number;
  risk_level?: string;
  collected_at?: string;
};

type LatestWeatherData = {
  count?: number;
  observations?: WeatherObservation[];
};

type RiskSummaryRow = {
  risk_level?: string;
  observation_count?: number;
  average_risk_score?: number;
  avg_risk_score?: number;
  maximum_risk_score?: number;
  max_risk_score?: number;
};

type RiskSummaryData = {
  summary?: RiskSummaryRow[];
};

function selectTool(question: string): McpToolCall {
  const normalized = question.toLowerCase();
  const now = new Date();
  const endAt = now.toISOString();
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const startAt = sevenDaysAgo.toISOString();

  if (
    normalized.includes("평균") ||
    normalized.includes("비교") ||
    normalized.includes("집계") ||
    normalized.includes("위험") ||
    normalized.includes("risk") ||
    normalized.includes("summary")
  ) {
    return {
      tool: "get_weather_risk_summary",
      args: {
        start_at: startAt,
        end_at: endAt,
      },
    };
  }

  if (
    normalized.includes("검색") ||
    normalized.includes("찾아") ||
    normalized.includes("기간") ||
    normalized.includes("기록")
  ) {
    return {
      tool: "search_weather",
      args: {
        start_at: startAt,
        end_at: endAt,
        limit: 50,
      },
    };
  }

  return {
    tool: "get_latest_weather",
    args: {},
  };
}

function buildDeterministicAnswer(
  question: string,
  toolResult: McpToolResult,
) {
  if (toolResult.tool === "get_latest_weather") {
    return buildLatestWeatherAnswer(question, toolResult);
  }

  if (toolResult.tool === "get_weather_risk_summary") {
    return buildRiskSummaryAnswer(question, toolResult);
  }

  if (toolResult.tool === "search_weather") {
    return buildSearchWeatherAnswer(question, toolResult);
  }

  return [
    `질문에 답하기 위해 MCP Tool \`${toolResult.tool}\`을 호출했습니다.`,
    `현재 응답은 ${toolResult.source === "mock" ? "mock 데이터" : "실제 MCP 서버 데이터"}를 기반으로 생성되었습니다.`,
    `사용자 질문: ${question}`,
  ].join("\n");
}

function formatNumber(value: number | undefined, unit = "") {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }

  return `${Number.isInteger(value) ? value : value.toFixed(1)}${unit}`;
}

function formatRiskLevel(level: string | undefined) {
  const labels: Record<string, string> = {
    LOW: "낮음",
    MEDIUM: "주의",
    HIGH: "높음",
    CRITICAL: "매우 높음",
  };

  return level ? (labels[level] ?? level) : "-";
}

function formatDateTime(value: string | undefined) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Seoul",
  }).format(date);
}

function getDataSourceLabel(source: McpToolResult["source"]) {
  return source === "mock" ? "mock 데이터" : "실제 MCP 서버 데이터";
}

function buildLatestWeatherAnswer(
  question: string,
  toolResult: McpToolResult,
) {
  const data = toolResult.data as LatestWeatherData;
  const observations = data.observations ?? [];
  const observedAt = observations[0]?.observed_at;
  const collectedAt = observations[0]?.collected_at;
  const lines = observations.map((item) => {
    return `- ${item.location ?? "지역 미상"}: 기온 ${formatNumber(item.temperature, "°C")}, 체감 ${formatNumber(item.apparent_temperature, "°C")}, 습도 ${formatNumber(item.relative_humidity, "%")}, 강수량 ${formatNumber(item.precipitation, "mm")}, 풍속 ${formatNumber(item.wind_speed, "m/s")}, 위험도 ${formatRiskLevel(item.risk_level)}(${formatNumber(item.risk_score)}점)`;
  });

  return [
    `MCP Tool \`${toolResult.tool}\`로 최신 날씨 데이터를 조회했습니다.`,
    `응답 기준: ${getDataSourceLabel(toolResult.source)}`,
    observedAt ? `관측 시각: ${formatDateTime(observedAt)}` : null,
    collectedAt ? `수집 시각: ${formatDateTime(collectedAt)}` : null,
    "",
    observations.length > 0
      ? `총 ${data.count ?? observations.length}개 지역의 최신 관측값입니다.`
      : "조회된 최신 날씨 데이터가 없습니다.",
    ...lines,
    "",
    `요약하면, 현재 조회된 지역들은 대체로 ${summarizeRiskLevels(observations)} 상태입니다.`,
    `질문: ${question}`,
  ]
    .filter((line): line is string => line !== null)
    .join("\n");
}

function summarizeRiskLevels(observations: WeatherObservation[]) {
  const counts = observations.reduce<Record<string, number>>((acc, item) => {
    const label = formatRiskLevel(item.risk_level);
    acc[label] = (acc[label] ?? 0) + 1;
    return acc;
  }, {});

  const summary = Object.entries(counts)
    .map(([level, count]) => `${level} ${count}곳`)
    .join(", ");

  return summary || "데이터 없음";
}

function buildRiskSummaryAnswer(
  question: string,
  toolResult: McpToolResult,
) {
  const data = toolResult.data as RiskSummaryData;
  const summary = data.summary ?? [];
  const lines = summary.map((item) => {
    const average = item.average_risk_score ?? item.avg_risk_score;
    const maximum = item.maximum_risk_score ?? item.max_risk_score;

    return `- ${formatRiskLevel(item.risk_level)}: ${item.observation_count ?? 0}건, 평균 위험점수 ${formatNumber(average)}점, 최대 ${formatNumber(maximum)}점`;
  });

  return [
    `MCP Tool \`${toolResult.tool}\`로 최근 기간의 날씨 위험도 집계를 조회했습니다.`,
    `응답 기준: ${getDataSourceLabel(toolResult.source)}`,
    "",
    summary.length > 0
      ? "위험등급별 집계 결과는 다음과 같습니다."
      : "조회된 위험도 집계 데이터가 없습니다.",
    ...lines,
    "",
    buildRiskSummaryInsight(summary),
    `질문: ${question}`,
  ].join("\n");
}

function buildRiskSummaryInsight(summary: RiskSummaryRow[]) {
  if (summary.length === 0) {
    return "분석할 집계 데이터가 없습니다.";
  }

  const sorted = [...summary].sort(
    (a, b) => (b.observation_count ?? 0) - (a.observation_count ?? 0),
  );
  const top = sorted[0];

  return `가장 많이 관측된 위험등급은 ${formatRiskLevel(top.risk_level)}이며, 총 ${top.observation_count ?? 0}건입니다.`;
}

function buildSearchWeatherAnswer(
  question: string,
  toolResult: McpToolResult,
) {
  const data = toolResult.data as LatestWeatherData;
  const observations = data.observations ?? [];

  return [
    `MCP Tool \`${toolResult.tool}\`로 조건에 맞는 날씨 기록을 검색했습니다.`,
    `응답 기준: ${getDataSourceLabel(toolResult.source)}`,
    "",
    `총 ${data.count ?? observations.length}건이 조회되었습니다.`,
    ...observations.slice(0, 5).map((item) => {
      return `- ${formatDateTime(item.observed_at)} ${item.location ?? "지역 미상"}: 기온 ${formatNumber(item.temperature, "°C")}, 위험도 ${formatRiskLevel(item.risk_level)}(${formatNumber(item.risk_score)}점)`;
    }),
    observations.length > 5 ? `- 외 ${observations.length - 5}건` : "",
    "",
    `질문: ${question}`,
  ]
    .filter(Boolean)
    .join("\n");
}

async function generateLlmAnswer(
  question: string,
  toolResult: McpToolResult,
) {
  const apiKey = process.env.OPENAI_API_KEY;
  const model = process.env.LLM_MODEL;

  if (!apiKey || !model) {
    return buildDeterministicAnswer(question, toolResult);
  }

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      input: [
        {
          role: "system",
          content:
            "You are a data analysis assistant. Answer in Korean using only the provided MCP tool result. Do not invent data.",
        },
        {
          role: "user",
          content: JSON.stringify({
            question,
            mcp_tool: toolResult.tool,
            mcp_result: toolResult.data,
          }),
        },
      ],
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`LLM call failed: ${response.status} ${detail}`);
  }

  const result = await response.json();
  const text =
    result.output_text ??
    result.output
      ?.flatMap((item: { content?: Array<{ text?: string }> }) =>
        item.content?.map((content) => content.text).filter(Boolean) ?? [],
      )
      .join("\n");

  return text || buildDeterministicAnswer(question, toolResult);
}

export async function runAgent(question: string): Promise<AgentResponse> {
  const toolCall = selectTool(question);
  const toolResult = await callMcpTool(toolCall);
  const answer = await generateLlmAnswer(question, toolResult);

  return {
    answer,
    toolCall,
    toolResult,
  };
}
