export interface Student {
  id: number;
  name: string;
  email: string;
  created_at: string;
}

export interface Topic {
  id: number;
  name: string;
  description: string | null;
  difficulty: number;
}

export interface MasteryRow {
  topic_id: number;
  topic_name: string;
  difficulty: number;
  mastery: number;
  attempts: number;
  last_attempt_at: string | null;
}

export interface Progress {
  student: Student;
  overall_mastery: number;
  total_study_minutes: number;
  total_attempts: number;
  topics: MasteryRow[];
}

export interface Recommendation {
  topic_id: number;
  topic_name: string;
  score: number;
  mastery: number;
  reason: string;
  contributions: Record<string, number>;
}

export interface MasteryHistoryPoint {
  topic_id: number;
  mastery: number;
  source: string;
  created_at: string;
}

export type StudyPlanSource = "llm" | "fallback";

export interface StudyPlan {
  plan: string;
  source: StudyPlanSource;
  generated_at: string;
}

export interface StudyRecord {
  id: number;
  student_id: number;
  topic_id: number;
  duration_minutes: number;
  studied_at: string;
  notes: string | null;
}

export interface QuizResult {
  attempt: {
    id: number;
    student_id: number;
    topic_id: number;
    correct_answers: number;
    total_questions: number;
    score: number;
    attempted_at: string;
  };
  mastery: number;
}

export interface Flashcard {
  id: number;
  student_id: number;
  topic_id: number;
  question: string;
  answer: string;
  source: string;
  created_at: string;
}

export interface FlashcardBatch {
  flashcards: Flashcard[];
  source: "llm" | "fallback";
}
