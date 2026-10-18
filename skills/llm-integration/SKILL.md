---
name: llm-integration
description: LLM integration patterns including API usage, streaming, function calling, RAG pipelines, and cost optimization
---

# LLM Integration

## API Client Pattern

```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();

async function generateResponse(
  systemPrompt: string,
  userMessage: string,
  options?: { maxTokens?: number; temperature?: number }
): Promise<string> {
  const response = await client.messages.create({
    model: "claude-sonnet-5-5",
    max_tokens: options?.maxTokens ?? 1024,
    temperature: options?.temperature ?? 0,
    system: systemPrompt,
    messages: [{ role: "user", content: userMessage }],
  });

  const textBlock = response.content.find(block => block.type === "text");
  return textBlock?.text ?? "";
}
```

## Streaming Responses

```typescript
async function streamResponse(
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  onChunk: (text: string) => void
): Promise<string> {
  const stream = client.messages.stream({
    model: "claude-sonnet-5-5",
    max_tokens: 4096,
    messages,
  });

  let fullText = "";

  for await (const event of stream) {
    if (event.type === "content_block_delta" && event.delta.type === "text_delta") {
      onChunk(event.delta.text);
      fullText += event.delta.text;
    }
  }

  return fullText;
}

const response = await streamResponse(
  [{ role: "user", content: "Explain async/await in TypeScript" }],
  (chunk) => process.stdout.write(chunk)
);
```

## Function Calling (Tool Use)

```typescript
const tools: Anthropic.Tool[] = [
  {
    name: "search_database",
    description: "Search the product database by name, category, or price range",
    input_schema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Search query" },
        category: { type: "string", description: "Product category filter" },
        max_price: { type: "number", description: "Maximum price" },
      },
      required: ["query"],
    },
  },
];

async function agentLoop(userMessage: string, maxSteps = 20): Promise<{ text: string; truncated: boolean }> {
  const messages: Anthropic.MessageParam[] = [
    { role: "user", content: userMessage },
  ];
  const seen = new Map<string, number>();  // 같은 (name, args) 반복 감지

  for (let step = 0; step < maxSteps; step++) {
    const response = await client.messages.create({
      model: "claude-sonnet-5-5",
      max_tokens: 4096,
      tools,
      messages,
    });
    messages.push({ role: "assistant", content: response.content });

    if (response.stop_reason !== "tool_use") {
      const text = response.content.find(b => b.type === "text");
      return { text: text?.type === "text" ? text.text : "", truncated: false };
    }

    // 병렬 tool_use 가 올 수 있다 — 모든 블록에 tool_result 를 붙여야 API 에러가 안 난다
    const results: Anthropic.ToolResultBlockParam[] = [];
    for (const block of response.content) {
      if (block.type !== "tool_use") continue;
      const key = `${block.name}:${JSON.stringify(block.input)}`;
      const n = (seen.get(key) ?? 0) + 1;
      seen.set(key, n);
      if (n >= 3) {
        results.push({ type: "tool_result", tool_use_id: block.id, is_error: true,
          content: "Same call repeated 3 times with identical arguments. Change approach or report what is blocking." });
        continue;
      }
      try {
        results.push({ type: "tool_result", tool_use_id: block.id,
          content: await executeToolCall(block.name, block.input) });
      } catch (e) {
        // throw 하면 루프가 죽는다 — 구조화된 에러로 돌려주면 모델이 복구할 기회가 생긴다
        results.push({ type: "tool_result", tool_use_id: block.id, is_error: true, content: String(e) });
      }
    }
    messages.push({ role: "user", content: results });
  }

  // 상한 도달: 크래시가 아니라 부분 결과 + 플래그
  return { text: "", truncated: true };
}
```

**루프 종료 조건은 프롬프트가 아니라 코드로 강제한다** — 단계 상한, 동일 호출 반복 감지, 부분 결과 플래그.
상한에 걸리면 호출자가 `truncated` 를 보고 재시도·사람 확인·보고 중 하나를 고른다.

## RAG Pipeline

```typescript
import { embed } from "./embeddings";

interface Chunk {
  id: string;
  text: string;
  metadata: Record<string, string>;
  embedding: number[];
}

async function retrieveAndGenerate(query: string): Promise<string> {
  const queryEmbedding = await embed(query);

  const relevantChunks = await vectorDb.search({
    vector: queryEmbedding,
    topK: 5,
    filter: { source: "documentation" },
  });

  const context = relevantChunks
    .map((chunk, i) => `[${i + 1}] ${chunk.text}`)
    .join("\n\n");

  const response = await client.messages.create({
    model: "claude-sonnet-5-5",
    max_tokens: 2048,
    system: `Answer questions using the provided context. Cite sources with [n] notation. If the context doesn't contain the answer, say so.`,
    messages: [
      {
        role: "user",
        content: `Context:\n${context}\n\nQuestion: ${query}`,
      },
    ],
  });

  return response.content[0].type === "text" ? response.content[0].text : "";
}
```

## Document Chunking

```typescript
function chunkDocument(
  text: string,
  options: { chunkSize: number; overlap: number }
): string[] {
  const { chunkSize, overlap } = options;
  const chunks: string[] = [];
  const sentences = text.split(/(?<=[.!?])\s+/);
  let current = "";

  for (const sentence of sentences) {
    if (current.length + sentence.length > chunkSize && current.length > 0) {
      chunks.push(current.trim());
      const words = current.split(" ");
      const overlapWords = words.slice(-Math.floor(overlap / 5));
      current = overlapWords.join(" ") + " " + sentence;
    } else {
      current += (current ? " " : "") + sentence;
    }
  }

  if (current.trim()) chunks.push(current.trim());
  return chunks;
}
```

## Cost Optimization

```typescript
function selectModel(task: TaskType): string {
  switch (task) {
    case "classification":
    case "extraction":
      return "claude-haiku-4-5-20251001";
    case "analysis":
    case "coding":
      return "claude-sonnet-5-5";
    case "complex-reasoning":
      return "claude-opus-5-5";
    default:
      return "claude-sonnet-5-5";
  }
}
```

모델 ID 는 금방 낡는다 — 쓰기 전에 번들 `claude-api` 스킬로 현재 ID 를 확인한다.

Use the smallest model that achieves acceptable quality. **비용은 호출당이 아니라 성공 1건당으로 비교한다** —
싼 모델이 자주 실패해 재시도하면 더 비싸다. Cache embeddings and responses where possible. Batch requests when latency is not critical.

## Anti-Patterns

- Sending entire documents when only relevant chunks are needed
- Not implementing retry logic with exponential backoff for API calls
- Ignoring token usage tracking (leads to unexpected costs)
- Using the most expensive model for simple classification tasks
- Not validating or sanitizing LLM output before using it in code
- Building RAG without evaluating retrieval quality first

## Checklist

- [ ] API calls wrapped with retry logic and error handling
- [ ] Streaming used for user-facing responses
- [ ] Function calling schemas include clear descriptions
- [ ] RAG chunks sized appropriately (500-1000 tokens) with overlap
- [ ] Model selection based on task complexity
- [ ] Token usage tracked and monitored for cost control
- [ ] LLM output validated before downstream use
- [ ] Embeddings cached to avoid redundant API calls
- [ ] Agent loop has a step cap, repeated-call detection, and handles **every** `tool_use` block (tool errors returned as `is_error`, not thrown)
- [ ] LLM-as-judge: measure agreement with 50–100 human labels before trusting it; re-measure when the judge prompt/model changes. Randomize pairwise order; don't let a model grade its own output
