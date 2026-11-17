import type {
  Flashcard,
  FlashcardBatch,
  MasteryHistoryPoint,
  Progress,
  QuizResult,
  Recommendation,
  Student,
  StudyPlan,
  StudyRecord,
  Topic,
} from "./types";

const BASE_URL = "/api";

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
  listStudents: () => request<Student[]>("/students"),
  listTopics: () => request<Topic[]>("/topics"),
  getProgress: (studentId: number) => request<Progress>(`/students/${studentId}/progress`),
  getRecommendations: (studentId: number, limit = 5) =>
    request<Recommendation[]>(`/students/${studentId}/recommendations?limit=${limit}`),
  getMasteryHistory: (studentId: number) =>
    request<MasteryHistoryPoint[]>(`/students/${studentId}/mastery-history`),
  generateStudyPlan: (studentId: number) =>
    request<StudyPlan>(`/students/${studentId}/study-plan`, { method: "POST" }),
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
  deleteFlashcard: (flashcardId: number) =>
    request<void>(`/flashcards/${flashcardId}`, { method: "DELETE" }),
};
