export type McpToolName =
  | "get_latest_weather"
  | "search_weather"
  | "get_weather_risk_summary";

export type McpToolCall = {
  tool: McpToolName;
  args: Record<string, unknown>;
};

export type McpToolResult = {
  tool: McpToolName;
  data: unknown;
  source: "mock" | "mcp";
};

type JsonRpcResponse = {
  jsonrpc?: "2.0";
  id?: number | string | null;
  result?: unknown;
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
};

type McpToolContent = {
  type?: string;
  text?: string;
};

type McpToolCallResult = {
  content?: McpToolContent[];
  structuredContent?: unknown;
  isError?: boolean;
};

const mockObservations = [
  {
    location: "신촌",
    temperature_c: 30.8,
    humidity_percent: 73,
    precipitation_mm: 0.0,
    wind_speed_ms: 2.1,
    risk_level: "주의",
    risk_score: 62,
    observed_at: "2026-08-11T10:00:00Z",
    collected_at: "2026-08-11T10:05:00Z",
  },
  {
    location: "강남",
    temperature_c: 32.1,
    humidity_percent: 69,
    precipitation_mm: 0.0,
    wind_speed_ms: 1.7,
    risk_level: "경계",
    risk_score: 76,
    observed_at: "2026-08-11T10:00:00Z",
    collected_at: "2026-08-11T10:05:00Z",
  },
  {
    location: "서울역",
    temperature_c: 31.4,
    humidity_percent: 71,
    precipitation_mm: 0.0,
    wind_speed_ms: 2.4,
    risk_level: "주의",
    risk_score: 66,
    observed_at: "2026-08-11T10:00:00Z",
    collected_at: "2026-08-11T10:05:00Z",
  },
];

function shouldUseMock() {
  return process.env.MCP_USE_MOCK !== "false";
}

async function callMockTool(call: McpToolCall): Promise<McpToolResult> {
  if (call.tool === "get_latest_weather") {
    const location = call.args.location
      ? String(call.args.location)
      : undefined;
    const observations = location
      ? mockObservations.filter((item) => item.location.includes(location))
      : mockObservations;

    return {
      tool: call.tool,
      data: {
        count: observations.length,
        location: location ?? null,
        observations,
      },
      source: "mock",
    };
  }

  if (call.tool === "search_weather") {
    const location = call.args.location
      ? String(call.args.location)
      : undefined;
    const riskLevel = call.args.risk_level
      ? String(call.args.risk_level)
      : undefined;
    const limit = Number(call.args.limit ?? 100);
    const observations = mockObservations
      .filter((item) => !location || item.location.includes(location))
      .filter((item) => !riskLevel || item.risk_level === riskLevel)
      .slice(0, limit);

    return {
      tool: call.tool,
      data: {
        count: observations.length,
        filters: call.args,
        observations,
      },
      source: "mock",
    };
  }

  return {
    tool: call.tool,
    data: {
      filters: call.args,
      summary: [
        {
          risk_level: "주의",
          observation_count: 2,
          avg_risk_score: 64,
          max_risk_score: 66,
        },
        {
          risk_level: "경계",
          observation_count: 1,
          avg_risk_score: 76,
          max_risk_score: 76,
        },
      ],
    },
    source: "mock",
  };
}

function parseServerSentEvents(text: string): unknown {
  const events: string[] = [];
  let currentData: string[] = [];

  for (const line of text.split(/\r?\n/)) {
    if (line.startsWith("data:")) {
      currentData.push(line.slice("data:".length).trim());
      continue;
    }

    if (!line.trim() && currentData.length > 0) {
      events.push(currentData.join("\n"));
      currentData = [];
    }
  }

  if (currentData.length > 0) {
    events.push(currentData.join("\n"));
  }

  const parsedEvents = events
    .filter((event) => event && event !== "[DONE]")
    .map((event) => JSON.parse(event));

  return parsedEvents.at(-1) ?? null;
}

async function parseMcpHttpResponse(response: Response): Promise<unknown> {
  const text = await response.text();

  if (!text.trim()) {
    return null;
  }

  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("text/event-stream")) {
    return parseServerSentEvents(text);
  }

  return JSON.parse(text);
}

function getJsonRpcResult(payload: unknown): unknown {
  const response = Array.isArray(payload)
    ? (payload.find((item) => item && typeof item === "object") as
        | JsonRpcResponse
        | undefined)
    : (payload as JsonRpcResponse);

  if (!response || typeof response !== "object") {
    throw new Error("MCP server returned an empty response.");
  }

  if (response.error) {
    throw new Error(
      `MCP JSON-RPC error ${response.error.code}: ${response.error.message}`,
    );
  }

  return response.result;
}

function normalizeToolResult(result: unknown): unknown {
  if (!result || typeof result !== "object") {
    return result;
  }

  const toolResult = result as McpToolCallResult;

  if (toolResult.isError) {
    throw new Error(JSON.stringify(toolResult.content ?? result));
  }

  if (toolResult.structuredContent !== undefined) {
    return toolResult.structuredContent;
  }

  const textContent = toolResult.content
    ?.filter((item) => item.type === "text" && item.text)
    .map((item) => item.text)
    .join("\n");

  if (!textContent) {
    return result;
  }

  try {
    return JSON.parse(textContent);
  } catch {
    return textContent;
  }
}

async function postMcpJsonRpc(
  method: string,
  params: Record<string, unknown>,
  id: number | null,
  sessionId?: string,
) {
  const baseUrl = process.env.MCP_BASE_URL;
  const token = process.env.MCP_AUTH_TOKEN;

  if (!baseUrl || !token) {
    throw new Error("MCP_BASE_URL and MCP_AUTH_TOKEN are required.");
  }

  const headers: Record<string, string> = {
    Accept: "application/json, text/event-stream",
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  if (sessionId) {
    headers["Mcp-Session-Id"] = sessionId;
  }

  const payload =
    id === null
      ? {
          jsonrpc: "2.0",
          method,
          params,
        }
      : {
          jsonrpc: "2.0",
          id,
          method,
          params,
        };

  let response: Response;

  try {
    response = await fetch(baseUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "unknown network error";

    throw new Error(
      `MCP network request failed. Check MCP_BASE_URL, EC2 Security Group, Nginx, and container port. Detail: ${message}`,
    );
  }

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`MCP call failed: ${response.status} ${detail}`);
  }

  return {
    payload: await parseMcpHttpResponse(response),
    sessionId:
      response.headers.get("mcp-session-id") ??
      response.headers.get("Mcp-Session-Id") ??
      sessionId,
  };
}

async function callStreamableHttpMcp(
  call: McpToolCall,
): Promise<McpToolResult> {
  const initialized = await postMcpJsonRpc(
    "initialize",
    {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: {
        name: "ybigta-nextjs-agent",
        version: "0.1.0",
      },
    },
    1,
  );
  const sessionId = initialized.sessionId;

  await postMcpJsonRpc(
    "notifications/initialized",
    {},
    null,
    sessionId,
  );

  const toolResponse = await postMcpJsonRpc(
    "tools/call",
    {
      name: call.tool,
      arguments: call.args,
    },
    2,
    sessionId,
  );

  return {
    tool: call.tool,
    data: normalizeToolResult(getJsonRpcResult(toolResponse.payload)),
    source: "mcp",
  };
}

export async function callMcpTool(call: McpToolCall): Promise<McpToolResult> {
  if (shouldUseMock()) {
    return callMockTool(call);
  }

  return callStreamableHttpMcp(call);
}
