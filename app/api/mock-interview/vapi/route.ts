import { NextRequest, NextResponse } from "next/server";

import type { MockInterviewBriefResponse } from "../../../../app/lib/types";

const VAPI_BASE_URL = "https://api.vapi.ai";
const POLL_ATTEMPTS = 4;
const POLL_DELAY_MS = 2500;

type VapiMode = "chat" | "eval" | "voice";

type VapiValidationResult = {
  provider: "vapi";
  mode: VapiMode;
  status: "completed" | "queued" | "billing_required" | "error" | "ready";
  summary: string;
  detail?: string;
  assistant_reply?: string | null;
  assistant_id?: string;
  assistant_name?: string;
  run_id?: string;
  workflow_id?: string;
  result_status?: string | null;
  raw?: unknown;
};

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildAssistantPayload(brief: MockInterviewBriefResponse) {
  return {
    name: `Contax · ${brief.contact.name}`,
    firstMessage: brief.assistant.first_message,
    firstMessageMode: "assistant-waits-for-user",
    voice: {
      provider: "vapi",
      voiceId: "Elliot",
    },
    model: {
      provider: "openai",
      model: "gpt-4.1",
      temperature: 0.4,
      messages: [{ role: "system", content: brief.assistant.system_prompt }],
    },
    metadata: {
      source: "contax",
      contactName: brief.contact.name,
      contactCompany: brief.contact.company,
      track: brief.track.id,
    },
  };
}

function assistantMatchesBrief(assistant: unknown, brief: MockInterviewBriefResponse) {
  if (!assistant || typeof assistant !== "object") return false;
  const metadata = (assistant as { metadata?: Record<string, unknown> }).metadata;
  if (!metadata || typeof metadata !== "object") return false;

  return (
    metadata.source === "contax" &&
    metadata.contactName === brief.contact.name &&
    metadata.contactCompany === brief.contact.company &&
    metadata.track === brief.track.id
  );
}

async function upsertAssistant(brief: MockInterviewBriefResponse): Promise<
  | { id: string; name?: string }
  | { error: VapiValidationResult }
> {
  const payload = buildAssistantPayload(brief);

  const listResponse = await vapiFetch("/assistant?limit=100", { method: "GET" });
  const listBody = await parseBody(listResponse);
  if (!listResponse.ok || !Array.isArray(listBody)) {
    return {
      error: {
        provider: "vapi",
        mode: "chat",
        status: "error",
        summary: "Could not load Vapi assistants.",
        detail: errorMessage(listBody, `Vapi returned ${listResponse.status}.`),
        raw: listBody,
      },
    };
  }

  const existing = listBody.find((assistant) => assistantMatchesBrief(assistant, brief)) as
    | { id?: unknown; name?: unknown }
    | undefined;

  if (typeof existing?.id === "string" && existing.id) {
    const updateResponse = await vapiFetch(`/assistant/${existing.id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    const updateBody = await parseBody(updateResponse);
    if (!updateResponse.ok) {
      return {
        error: {
          provider: "vapi",
          mode: "chat",
          status: "error",
          summary: "Could not update the Vapi assistant.",
          detail: errorMessage(updateBody, `Vapi returned ${updateResponse.status}.`),
          raw: updateBody,
        },
      };
    }

    return {
      id: existing.id,
      name: typeof existing.name === "string" ? existing.name : payload.name,
    };
  }

  const createResponse = await vapiFetch("/assistant", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const createBody = await parseBody(createResponse);
  if (!createResponse.ok) {
    return {
      error: {
        provider: "vapi",
        mode: "chat",
        status: createResponse.status === 402 ? "billing_required" : "error",
        summary:
          createResponse.status === 402
            ? "Vapi assistant creation is blocked until this org adds a payment method."
            : "Could not create the Vapi assistant.",
        detail: errorMessage(createBody, `Vapi returned ${createResponse.status}.`),
        raw: createBody,
      },
    };
  }

  const assistantId =
    typeof createBody === "object" && createBody
      ? (createBody as { id?: unknown }).id
      : undefined;
  const assistantName =
    typeof createBody === "object" && createBody
      ? (createBody as { name?: unknown }).name
      : undefined;

  if (typeof assistantId !== "string" || !assistantId) {
    return {
      error: {
        provider: "vapi",
        mode: "chat",
        status: "error",
        summary: "Vapi assistant creation returned no id.",
        detail: "The Vapi response did not include an assistant id.",
        raw: createBody,
      },
    };
  }

  return {
    id: assistantId,
    name: typeof assistantName === "string" ? assistantName : payload.name,
  };
}

async function prepareVoiceSession(brief: MockInterviewBriefResponse): Promise<VapiValidationResult> {
  const assistant = await upsertAssistant(brief);
  if ("error" in assistant) {
    return assistant.error;
  }

  return {
    provider: "vapi",
    mode: "voice",
    status: "ready",
    summary: "Vapi voice assistant is ready.",
    assistant_id: assistant.id,
    assistant_name: assistant.name,
  };
}

function buildEvalPayload(brief: MockInterviewBriefResponse) {
  const evaluationChecklist = brief.simulation.evaluations
    .map((evaluation) => `${evaluation.name}: ${evaluation.description}`)
    .join("; ");

  const judgePrompt = [
    `Judge only the latest assistant reply from a simulation of ${brief.contact.name}.`,
    `Pass only if the reply stays in persona as ${brief.contact.role || "the contact"}${brief.contact.company ? ` at ${brief.contact.company}` : ""}.`,
    `It should advance this objective: ${brief.track.objective}.`,
    "The reply should feel specific and realistic, not generic networking filler.",
    evaluationChecklist ? `Use these checks as guidance: ${evaluationChecklist}.` : "",
    "Respond with only pass or fail.",
  ]
    .filter(Boolean)
    .join(" ");

  return {
    name: `${brief.track.label} with ${brief.contact.name}`,
    description: brief.simulation.tester_instructions,
    type: "chat.mockConversation",
    messages: [
      {
        role: "user",
        content: brief.starter_line,
      },
      {
        role: "assistant",
        judgePlan: {
          type: "ai",
          model: {
            provider: "openai",
            model: "gpt-4.1",
            temperature: 0,
            messages: [{ role: "system", content: judgePrompt }],
          },
        },
        continuePlan: {
          exitOnFailureEnabled: true,
        },
      },
    ],
  };
}

function extractAssistantReply(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const output = (body as { output?: Array<{ role?: string; content?: unknown }> }).output;
  if (!Array.isArray(output)) return null;

  for (let index = output.length - 1; index >= 0; index -= 1) {
    const item = output[index];
    if (item?.role !== "assistant") continue;
    if (typeof item.content === "string" && item.content.trim()) return item.content.trim();
  }

  return null;
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function errorMessage(body: unknown, fallback: string): string {
  if (!body) return fallback;
  if (typeof body === "string") return body;
  if (typeof body === "object") {
    const maybeMessage = (body as { message?: unknown }).message;
    if (typeof maybeMessage === "string") return maybeMessage;
    if (Array.isArray(maybeMessage)) return maybeMessage.join(", ");
  }
  return fallback;
}

async function vapiFetch(path: string, init: RequestInit) {
  const token = process.env.VAPI_API_KEY;
  if (!token) {
    throw new Error("VAPI_API_KEY is not configured on the server.");
  }

  return fetch(`${VAPI_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });
}

async function runChatValidation(brief: MockInterviewBriefResponse): Promise<VapiValidationResult> {
  const assistant = await upsertAssistant(brief);
  if ("error" in assistant) {
    return assistant.error;
  }

  const response = await vapiFetch("/chat", {
    method: "POST",
    body: JSON.stringify({
      name: `Contax assistant chat · ${brief.contact.name}`,
      assistantId: assistant.id,
      input: brief.starter_line,
    }),
  });

  const body = await parseBody(response);
  if (response.status === 402) {
    return {
      provider: "vapi",
      mode: "chat",
      status: "billing_required",
      summary: "Vapi chat is blocked until this org adds a payment method.",
      detail: errorMessage(body, "Add a payment method in Vapi to use chat."),
      raw: body,
    };
  }

  if (!response.ok) {
    return {
      provider: "vapi",
      mode: "chat",
      status: "error",
      summary: "Vapi chat validation failed.",
      detail: errorMessage(body, `Vapi returned ${response.status}.`),
      raw: body,
    };
  }

  const reply = extractAssistantReply(body);
  return {
    provider: "vapi",
    mode: "chat",
    status: "completed",
    summary: reply ? "Vapi assistant replied." : "Vapi chat completed.",
    assistant_reply: reply,
    assistant_id: assistant.id,
    assistant_name: assistant.name,
    raw: body,
  };
}

async function runEvalValidation(brief: MockInterviewBriefResponse): Promise<VapiValidationResult> {
  const createResponse = await vapiFetch("/eval/run", {
    method: "POST",
    body: JSON.stringify({
      type: "eval",
      target: {
        type: "assistant",
        assistant: buildAssistantPayload(brief),
      },
      eval: buildEvalPayload(brief),
    }),
  });

  const createBody = await parseBody(createResponse);
  if (!createResponse.ok) {
    return {
      provider: "vapi",
      mode: "eval",
      status: createResponse.status === 402 ? "billing_required" : "error",
      summary:
        createResponse.status === 402
          ? "Vapi eval is blocked until this org adds a payment method."
          : "Vapi eval could not be started.",
      detail: errorMessage(createBody, `Vapi returned ${createResponse.status}.`),
      raw: createBody,
    };
  }

  const evalRunId =
    typeof createBody === "object" && createBody
      ? (createBody as { evalRunId?: unknown }).evalRunId
      : undefined;
  const workflowId =
    typeof createBody === "object" && createBody
      ? (createBody as { workflowId?: unknown }).workflowId
      : undefined;

  if (typeof evalRunId !== "string" || !evalRunId) {
    return {
      provider: "vapi",
      mode: "eval",
      status: "error",
      summary: "Vapi eval started without a run id.",
      detail: "The Vapi response did not include evalRunId.",
      raw: createBody,
    };
  }

  let latestBody: unknown = createBody;
  for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt += 1) {
    await sleep(POLL_DELAY_MS);
    const pollResponse = await vapiFetch(`/eval/run/${evalRunId}`, { method: "GET" });
    latestBody = await parseBody(pollResponse);

    if (!pollResponse.ok) {
      return {
        provider: "vapi",
        mode: "eval",
        status: "error",
        summary: "Vapi eval polling failed.",
        detail: errorMessage(latestBody, `Vapi returned ${pollResponse.status}.`),
        run_id: evalRunId,
        workflow_id: typeof workflowId === "string" ? workflowId : undefined,
        raw: latestBody,
      };
    }

    const status =
      typeof latestBody === "object" && latestBody
        ? (latestBody as { status?: unknown }).status
        : undefined;
    if (status === "ended") {
      const results =
        typeof latestBody === "object" && latestBody
          ? (latestBody as { results?: Array<{ status?: string }> }).results
          : undefined;
      const firstResult = Array.isArray(results) ? results[0] : undefined;
      const resultStatus = firstResult?.status ?? null;

      return {
        provider: "vapi",
        mode: "eval",
        status: "completed",
        summary: resultStatus ? `Vapi eval finished with ${resultStatus}.` : "Vapi eval finished.",
        run_id: evalRunId,
        workflow_id: typeof workflowId === "string" ? workflowId : undefined,
        result_status: resultStatus,
        raw: latestBody,
      };
    }
  }

  return {
    provider: "vapi",
    mode: "eval",
    status: "queued",
    summary: "Vapi accepted the eval run, but it is still queued.",
    detail: "This usually means the Vapi workflow has not started processing yet.",
    run_id: evalRunId,
    workflow_id: typeof workflowId === "string" ? workflowId : undefined,
    raw: latestBody,
  };
}

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    brief?: MockInterviewBriefResponse;
    mode?: VapiMode;
  };

  if (!body?.brief?.assistant?.system_prompt || !body?.brief?.starter_line) {
    return NextResponse.json({ detail: "A mock interview brief is required." }, { status: 400 });
  }

  if (!process.env.VAPI_API_KEY) {
    return NextResponse.json({ detail: "VAPI_API_KEY is not configured on the server." }, { status: 500 });
  }

  const mode = body.mode === "eval" ? "eval" : body.mode === "voice" ? "voice" : "chat";
  const result =
    mode === "eval"
      ? await runEvalValidation(body.brief)
      : mode === "voice"
        ? await prepareVoiceSession(body.brief)
        : await runChatValidation(body.brief);
  return NextResponse.json(result);
}
