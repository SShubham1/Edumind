import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { EntryForms } from "./components/EntryForms";
import { Flashcards } from "./components/Flashcards";
import { MasteryChart } from "./components/MasteryChart";
import { MasteryTrend } from "./components/MasteryTrend";
import { QuizGenerator } from "./components/QuizGenerator";
import { Recommendations } from "./components/Recommendations";
import { StudentPicker } from "./components/StudentPicker";
import { StudyPlan } from "./components/StudyPlan";
import { formatDate, formatMinutes, percent } from "./format";
import type {
  MasteryHistoryPoint,
  Progress,
  Recommendation,
  Student,
  Subject,
  Topic,
} from "./types";

interface Dashboard {
  progress: Progress;
  recommendations: Recommendation[];
  history: MasteryHistoryPoint[];
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

export default function App() {
  const [studentOptions, setStudentOptions] = useState<Student[]>([]);
  const [selectedStudent, setSelectedStudent] = useState<Student | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectKey, setSubjectKey] = useState<string | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [booting, setBooting] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setBooting(true);
      setError(null);
      try {
        const [subjectList, studentList] = await Promise.all([
          api.listSubjects(),
          api.listStudents({ limit: 50 }),
        ]);
        if (cancelled) return;
        setSubjects(subjectList);
        setStudentOptions(studentList);

        const preferredStudent = studentList[0] ?? null;
        setSelectedStudent(preferredStudent);

        // Prefer the subject with the most content.
        const populated = [...subjectList].sort(
          (a, b) => b.topic_count - a.topic_count,
        );
        setSubjectKey(populated[0]?.key ?? null);
      } catch (err) {
        if (!cancelled) {
          setError(errorMessage(err));
        }
      } finally {
        if (!cancelled) {
          setBooting(false);
        }
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadDashboard = useCallback(async (studentId: number, subject: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const [progress, recommendations, history, topicList] = await Promise.all([
        api.getProgress(studentId, subject),
        api.getRecommendations(studentId, 5, subject),
        api.getMasteryHistory(studentId, subject),
        api.listTopics(subject),
      ]);
      setDashboard({ progress, recommendations, history });
      setTopics(topicList);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedStudent === null) return;
    setDashboard(null);
    void loadDashboard(selectedStudent.id, subjectKey);
  }, [selectedStudent, subjectKey, loadDashboard]);

  const refresh = useCallback(async () => {
    if (selectedStudent === null) return;
    await loadDashboard(selectedStudent.id, subjectKey);
  }, [selectedStudent, subjectKey, loadDashboard]);

  const selectedSubject = subjects.find((subject) => subject.key === subjectKey) ?? null;

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            EM
          </span>
          <div>
            <p className="brand-name">EduMind</p>
            <p className="brand-tag">Adaptive learning</p>
          </div>
        </div>

        <StudentPicker
          selected={selectedStudent}
          initialStudents={studentOptions}
          onSelect={setSelectedStudent}
          disabled={booting}
        />
      </header>

      <main id="main">
        {subjects.length > 0 && (
          <nav className="subject-tabs" aria-label="Subjects">
            {subjects.map((subject) => (
              <button
                key={subject.key}
                type="button"
                className={
                  subject.key === subjectKey ? "subject-tab active" : "subject-tab"
                }
                aria-pressed={subject.key === subjectKey}
                onClick={() => setSubjectKey(subject.key)}
              >
                <span>{subject.name}</span>
                <span className="subject-count">{subject.topic_count}</span>
              </button>
            ))}
          </nav>
        )}

        {error && (
          <div className="alert error page-alert" role="alert">
            <span>{error}</span>
            {selectedStudent !== null && (
              <button type="button" className="button small" onClick={() => void refresh()}>
                Try again
              </button>
            )}
          </div>
        )}

        {booting && <p className="loading-note">Loading students and subjects…</p>}

        {!booting && !selectedStudent && !error && (
          <section className="card empty-card">
            <h2>No students yet</h2>
            <p>
              Import a dataset with the ASSISTments ETL or create a student through
              the API at <a href="/docs">/docs</a>. EduMind never generates
              students or topics on its own.
            </p>
          </section>
        )}

        {selectedStudent && (
          <>
            <section className="overview" aria-labelledby="overview-title">
              <div className="overview-copy">
                <p className="eyebrow">{selectedSubject?.name ?? "Learning"} overview</p>
                <h1 id="overview-title">{selectedStudent.name}</h1>
                <p className="muted">
                  {selectedStudent.email} · joined {formatDate(selectedStudent.created_at)}
                </p>
              </div>
              {loading && <p className="updating" role="status">Updating…</p>}
            </section>

            {dashboard ? (
              dashboard.progress.topics.length === 0 ? (
                <section className="card empty-card">
                  <h2>No topics in {selectedSubject?.name ?? "this subject"}</h2>
                  <p>
                    A subject appears only when an importer, API client or plugin
                    declares content for it. Import the ASSISTments dataset or
                    connect a plugin to add topics.
                  </p>
                </section>
              ) : (
                <>
                  <section className="stats" aria-label="Key metrics">
                    <article className="stat-card">
                      <p className="stat-label">Overall mastery</p>
                      <p className="stat-value">{percent(dashboard.progress.overall_mastery, 1)}</p>
                      <div className="stat-track" aria-hidden="true">
                        <span
                          className="stat-fill"
                          style={{ width: `${Math.max(2, dashboard.progress.overall_mastery * 100)}%` }}
                        />
                      </div>
                    </article>
                    <article className="stat-card">
                      <p className="stat-label">Study time</p>
                      <p className="stat-value">
                        {formatMinutes(dashboard.progress.total_study_minutes)}
                      </p>
                      <p className="stat-foot">Logged sessions</p>
                    </article>
                    <article className="stat-card">
                      <p className="stat-label">Quiz attempts</p>
                      <p className="stat-value">{dashboard.progress.total_attempts}</p>
                      <p className="stat-foot">Across {selectedSubject?.name ?? "all topics"}</p>
                    </article>
                    <article className="stat-card">
                      <p className="stat-label">Topics tracked</p>
                      <p className="stat-value">{dashboard.progress.topics.length}</p>
                      <p className="stat-foot">With mastery estimates</p>
                    </article>
                  </section>

                  <div className="grid two-column">
                    <section className="card" aria-labelledby="mastery-title">
                      <header className="card-head">
                        <div>
                          <h2 id="mastery-title">Mastery by topic</h2>
                          <p className="hint">
                            Estimated with a simplified Bayesian Knowledge Tracing update.
                            The chart shows your weakest attempted topics; the table lists all.
                          </p>
                        </div>
                      </header>
                      <MasteryChart rows={dashboard.progress.topics} />
                    </section>

                    <section className="card" aria-labelledby="recommendations-title">
                      <header className="card-head">
                        <div>
                          <h2 id="recommendations-title">What to study next</h2>
                          <p className="hint">
                            Ranked by mastery, revision urgency, difficulty and recent weakness.
                          </p>
                        </div>
                      </header>
                      <Recommendations recommendations={dashboard.recommendations} />
                    </section>
                  </div>

                  <section className="card" aria-labelledby="trend-title">
                    <header className="card-head">
                      <div>
                        <h2 id="trend-title">Mastery over time</h2>
                        <p className="hint">
                          One average across the topics attempted so far, built from recorded
                          mastery snapshots.
                        </p>
                      </div>
                    </header>
                    <MasteryTrend
                      points={dashboard.history}
                      rows={dashboard.progress.topics}
                    />
                  </section>

                  <section className="card" aria-labelledby="plan-title">
                    <header className="card-head">
                      <div>
                        <h2 id="plan-title">AI study plan</h2>
                        <p className="hint">
                          A short plan built from the ranked topics for this student and subject.
                        </p>
                      </div>
                    </header>
                    <StudyPlan
                      key={`${selectedStudent.id}-${subjectKey ?? "all"}`}
                      studentId={selectedStudent.id}
                      subject={subjectKey}
                    />
                  </section>

                  <section className="card" aria-labelledby="flashcards-title">
                    <header className="card-head">
                      <div>
                        <h2 id="flashcards-title">Flashcards</h2>
                        <p className="hint">
                          Active-recall cards generated per topic, with an offline fallback when no
                          LLM key is configured.
                        </p>
                      </div>
                    </header>
                    <Flashcards studentId={selectedStudent.id} topics={topics} />
                  </section>

                  <section className="card" aria-labelledby="quiz-title">
                    <header className="card-head">
                      <div>
                        <h2 id="quiz-title">AI practice quiz</h2>
                        <p className="hint">
                          Multiple-choice questions generated from your weakest topics plus
                          one relative strength. Graded results update mastery.
                        </p>
                      </div>
                    </header>
                    <QuizGenerator
                      key={`${selectedStudent.id}-${subjectKey ?? "all"}`}
                      studentId={selectedStudent.id}
                      subject={subjectKey}
                      onGraded={refresh}
                    />
                  </section>

                  <section aria-labelledby="log-title">
                    <div className="section-head">
                      <h2 id="log-title">Log learning activity</h2>
                      <p className="hint">New records update mastery and recommendations.</p>
                    </div>
                    <EntryForms
                      key={`${selectedStudent.id}-${subjectKey ?? "all"}`}
                      studentId={selectedStudent.id}
                      topics={topics}
                      onSaved={refresh}
                    />
                  </section>
                </>
              )
            ) : (
              !error &&
              loading && (
                <p className="loading-note">
                  Loading dashboard for {selectedStudent.name}
                  {selectedSubject ? ` · ${selectedSubject.name}` : ""}…
                </p>
              )
            )}
          </>
        )}
      </main>

      <footer className="footer">
        <p>
          EduMind · local-first React + FastAPI · imported ASSISTments history and
          plugin-declared content appear only when a source provides them.
        </p>
      </footer>
    </div>
  );
}
