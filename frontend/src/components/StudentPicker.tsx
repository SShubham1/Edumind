import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { api } from "../api";
import type { Student } from "../types";

interface StudentPickerProps {
  selected: Student | null;
  initialStudents: Student[];
  onSelect: (student: Student) => void;
  disabled?: boolean;
}

export function StudentPicker({
  selected,
  initialStudents,
  onSelect,
  disabled = false,
}: StudentPickerProps) {
  const listboxId = useId();
  const inputId = useId();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<Student[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    const trimmed = query.trim();
    if (!trimmed) {
      setOptions(initialStudents.slice(0, 20));
      setActiveIndex(0);
      return;
    }

    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(() => {
      void api
        .listStudents({ q: trimmed, limit: 20 })
        .then((students) => {
          if (!cancelled) {
            setOptions(students);
            setActiveIndex(0);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setOptions([]);
          }
        })
        .finally(() => {
          if (!cancelled) {
            setLoading(false);
          }
        });
    }, 200);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      setLoading(false);
    };
  }, [query, open, initialStudents]);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: MouseEvent) {
      if (!wrapperRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  function choose(student: Student) {
    onSelect(student);
    setOpen(false);
    setQuery("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((index) => Math.min(index + 1, Math.max(options.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      if (open && options[activeIndex]) {
        event.preventDefault();
        choose(options[activeIndex]);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  }

  const value = open ? query : (selected?.name ?? "");
  const activeId = options[activeIndex] ? `${listboxId}-${options[activeIndex].id}` : undefined;

  return (
    <div className="student-picker" ref={wrapperRef}>
      <label htmlFor={inputId}>Student</label>
      <div className="combobox">
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={open ? activeId : undefined}
          autoComplete="off"
          placeholder={disabled ? "Loading…" : "Search by name or email"}
          value={value}
          disabled={disabled}
          onFocus={() => {
            setOpen(true);
            setQuery("");
          }}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
        />
        {open && (
          <ul className="combobox-list" id={listboxId} role="listbox" aria-label="Students">
            {loading && <li className="combobox-note">Searching…</li>}
            {!loading && options.length === 0 && (
              <li className="combobox-note">No matching students</li>
            )}
            {!loading &&
              options.map((student, index) => (
                <li
                  key={student.id}
                  id={`${listboxId}-${student.id}`}
                  role="option"
                  aria-selected={index === activeIndex}
                  className={index === activeIndex ? "combobox-option active" : "combobox-option"}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    choose(student);
                  }}
                  onMouseEnter={() => setActiveIndex(index)}
                >
                  <span className="combobox-name">{student.name}</span>
                  <span className="combobox-email">{student.email}</span>
                </li>
              ))}
          </ul>
        )}
      </div>
    </div>
  );
}
