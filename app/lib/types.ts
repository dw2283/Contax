import type { Node } from "@xyflow/react";

export type Source = "wechat" | "linkedin" | "whatsapp";

export type Person = {
  id: string;
  name: string;
  company: string;
  role: string;
  location: string;
  interests: string[];
  how_we_met: string;
  source: string;
  embedding: number[];
  raw_screenshot_ref: string;
  dataset?: "demo" | "real" | string;
  is_demo?: boolean;
  imported_at?: number;
  updated_at?: number;
  source_profiles?: SourceProfile[];
  duplicate_status?: "needs_review" | string;
  duplicate_candidates?: DuplicateReview[];
  merge_log?: Array<Record<string, unknown>>;
};

export type SourceProfile = {
  id: string;
  source: string;
  raw_screenshot_ref: string;
  name: string;
  company: string;
  role: string;
  location: string;
  interests: string[];
  how_we_met: string;
  imported_at: number;
  confidence: number;
};

export type DuplicateReview = {
  id: string;
  candidate_id: string;
  existing_id: string;
  candidate_name: string;
  existing_name: string;
  score: number;
  reasons: string[];
  conflicts: string[];
  decision: "needs_review" | string;
};

export type UploadItem = {
  id: string;
  file_name: string;
  source: Source;
  raw_screenshot_ref: string;
  image_base64: string;
};

export type Recommendation = {
  person: Person;
  score: number;
  reason: string;
  draft_message: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
};

/** rank (1-based) + score for a person that matched the latest query. */
export type HighlightMatch = {
  rank: number;
  score: number;
};

export type TagKind = "company" | "topic" | "role" | "location" | "source";

export type GraphLod = "overview" | "cluster" | "detail";

/** A company or interest tag — the primary node in the tag-centric graph. */
export type Tag = {
  id: string;
  kind: TagKind;
  label: string;
  count: number;
};

export type TagNodeData = {
  nodeKind: "tag";
  kind: TagKind;
  label: string;
  categoryLabel: string;
  count: number;
  updatedCount?: number;
  size: number;
  accent: string;
  tint: string;
  highlighted?: boolean;
  selected?: boolean;
};

export type PersonNodeData = {
  nodeKind: "person";
  person: Person;
  label: string;
  subtitle: string;
  sourceLabel: string;
  size: number;
  highlighted?: boolean;
  selected?: boolean;
  updated?: boolean;
};

export type GraphNodeData = TagNodeData | PersonNodeData;

export type PRMNode = Node<GraphNodeData>;

export type IngestResponse = {
  weave_mode: string;
  weave_call_url?: string | null;
  local_screenshot_count?: number;
  result: {
    people: Person[];
    storage: {
      count: number;
      keys: string[];
      saved_ids?: string[];
      merged?: Array<Record<string, unknown>>;
      pending_reviews?: DuplicateReview[];
      duplicate_review_count?: number;
      redis_status: string;
      vector_index_ready: boolean;
    };
  };
};

export type SeedResponse = {
  people: Person[];
  storage: {
    count: number;
    keys: string[];
    saved_ids?: string[];
    merged?: Array<Record<string, unknown>>;
    pending_reviews?: DuplicateReview[];
    duplicate_review_count?: number;
    redis_status: string;
    vector_index_ready: boolean;
  };
  warning?: string;
};

export type PeopleResponse = {
  redis_status: string;
  people: Person[];
};

export type PeopleExportResponse = {
  exported_at: number;
  redis_status: string;
  person_count: number;
  people: Person[];
  duplicate_reviews: DuplicateReview[];
};

export type DeleteDemoResponse = {
  deleted_count: number;
  deleted_ids: string[];
  remaining_count: number;
  redis_status: string;
};

export type MatchResponse = {
  weave_mode: string;
  weave_call_url?: string | null;
  redis_status: string;
  people: Person[];
  result: {
    query: string;
    recommendations: Recommendation[];
  };
};

export type MockInterviewEvaluation = {
  name: string;
  schema_type: "boolean" | "number" | string;
  comparator: "=" | ">=" | "<=" | ">" | "<" | string;
  expected_value: boolean | number | string;
  required: boolean;
  description: string;
};

export type MockInterviewBriefResponse = {
  contact: {
    id?: string | null;
    name: string;
    company: string;
    role: string;
    location: string;
    interests: string[];
    how_we_met: string;
    source: string;
  };
  recommended_mode: "voice" | "chat" | string;
  supported_modes: Array<"voice" | "chat" | string>;
  track: {
    id: string;
    label: string;
    objective: string;
  };
  assistant: {
    suggested_name: string;
    first_message: string;
    system_prompt: string;
    variable_values: Record<string, string>;
  };
  simulation: {
    scenario_name: string;
    personality_name: string;
    personality_description: string;
    tester_instructions: string;
    evaluations: MockInterviewEvaluation[];
  };
  starter_line: string;
  validation_plan: string[];
};

export type MockInterviewVapiMode = "chat" | "eval" | "voice";

export type MockInterviewVapiResponse = {
  provider: "vapi";
  mode: MockInterviewVapiMode;
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
