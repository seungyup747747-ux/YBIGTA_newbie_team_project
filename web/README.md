# Seoul Weather Data Analysis Agent

Next.js Agent UI for the AI Agent assignment.

## Local Start

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Environment Variables

Create `.env.local` from `.env.example`.

```env
OPENAI_API_KEY=
LLM_MODEL=
MCP_BASE_URL=
MCP_AUTH_TOKEN=
MCP_USE_MOCK=true
```

Do not prefix secret values with `NEXT_PUBLIC_`.

For Vercel deployment, add the same values in Project Settings > Environment Variables. Keep `MCP_USE_MOCK=false` for the final deployed version after the MCP server endpoint is ready.

## Current Flow

```text
Browser
-> POST /api/chat
-> Next.js Route Handler
-> Agent tool selection
-> MCP Tool call
-> Agent answer
```

The browser never calls the MCP server directly.
The Next.js client only sends the user question to `/api/chat`; `OPENAI_API_KEY` and `MCP_AUTH_TOKEN` stay on the server side.

## MCP Mock Mode

The app starts with `MCP_USE_MOCK=true`, so the UI can be tested before the real MCP server is deployed.

To connect the real MCP server:

```env
MCP_USE_MOCK=false
MCP_BASE_URL=http://15.165.237.123/mcp
MCP_AUTH_TOKEN=your-token
```

The MCP server uses Streamable HTTP MCP. All tools use the same endpoint, and the tool name is passed through `tools/call`.

```text
POST /mcp
method: tools/call
params.name: get_latest_weather | search_weather | get_weather_risk_summary
```

The implementation is in `src/lib/mcpClient.ts`.

## Vercel Settings

Use these settings when importing the GitHub repository into Vercel:

```text
Root Directory: web
Install Command: npm install
Build Command: npm run build
Output Directory: .next
```

Required production environment variables:

```env
OPENAI_API_KEY=
LLM_MODEL=
MCP_BASE_URL=
MCP_AUTH_TOKEN=
MCP_USE_MOCK=false
```

## Capture Questions

Use these two questions for the assignment screenshots:

```text
현재 가장 최근 날씨 데이터는 뭐야?
```

```text
최근 일주일 동안 날씨 위험도 집계를 보여줘.
```

Expected tool mapping:

```text
현재 가장 최근 날씨 데이터는 뭐야?
-> get_latest_weather

최근 일주일 동안 날씨 위험도 집계를 보여줘.
-> get_weather_risk_summary
```

## Checks

```bash
npm run lint
npm run build
```
