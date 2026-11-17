import type {
  Flashcard,
  FlashcardBatch,
  GeneratedQuiz,
  MasteryHistoryPoint,
  Progress,
  QuizResult,
  Recommendation,
  Student,
  StudyPlan,
  StudyRecord,
  Subject,
  Topic,
} from "./types";

const BASE_URL = "/api";

function withParams(
  path: string,
  params: Record<string, string | number | undefined | null>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : ""))
          .filter(Boolean)
          .join("; ");
      }
    } catch {
      // Keep the generic message when the body is not JSON.
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  listSubjects: () => request<Subject[]>("/subjects"),
  listStudents: (options: { q?: string; limit?: number } = {}) =>
    request<Student[]>(
      withParams("/students", { q: options.q, limit: options.limit }),
    ),
  listTopics: (subject?: string | null) =>
    request<Topic[]>(withParams("/topics", { subject })),
  getProgress: (studentId: number, subject?: string | null) =>
    request<Progress>(withParams(`/students/${studentId}/progress`, { subject })),
  getRecommendations: (studentId: number, limit = 5, subject?: string | null) =>
    request<Recommendation[]>(
      withParams(`/students/${studentId}/recommendations`, { limit, subject }),
    ),
  getMasteryHistory: (studentId: number, subject?: string | null) =>
    request<MasteryHistoryPoint[]>(
      withParams(`/students/${studentId}/mastery-history`, { subject, limit: 2000 }),
    ),
  generateStudyPlan: (studentId: number, subject?: string | null) =>
    request<StudyPlan>(withParams(`/students/${studentId}/study-plan`, { subject }), {
      method: "POST",
    }),
  addStudyRecord: (payload: {
    student_id: number;
    topic_id: number;
    duration_minutes: number;
    notes?: string;
  }) =>
    request<StudyRecord>("/study-records", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitQuizResult: (payload: {
    student_id: number;
    topic_id: number;
    correct_answers: number;
    total_questions: number;
  }) =>
    request<QuizResult>("/quiz-results", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listFlashcards: (studentId: number) =>
    request<Flashcard[]>(`/students/${studentId}/flashcards`),
  generateFlashcards: (studentId: number, topicId: number, count: number) =>
    request<FlashcardBatch>(`/students/${studentId}/flashcards/generate`, {
      method: "POST",
      body: JSON.stringify({ topic_id: topicId, count }),
    }),
  generateQuiz: (studentId: number, count: number, subject?: string | null) =>
    request<GeneratedQuiz>(
      withParams(`/students/${studentId}/quiz/generate`, { subject }),
      {
        method: "POST",
        body: JSON.stringify({ count }),
      },
    ),
  deleteFlashcard: (flashcardId: number) =>
    request<void>(`/flashcards/${flashcardId}`, { method: "DELETE" }),
};
