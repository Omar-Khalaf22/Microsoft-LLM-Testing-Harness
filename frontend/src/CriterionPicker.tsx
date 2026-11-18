import { useEffect, useId, useState } from "react";
import type { KeyboardEvent } from "react";
import type { CriterionDefinition } from "./api";

const searchText = (value: string) => value.toLowerCase().replace(/[_-]+/g, " ");

export default function CriterionPicker({
  options,
  selectedId,
  onSelect,
  disabled,
}: {
  options: CriterionDefinition[];
  selectedId: string;
  onSelect: (id: string) => void;
  disabled: boolean;
}) {
  const id = useId();
  const listId = `${id}-options`;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState("");
  const words = searchText(query).trim().split(/\s+/).filter(Boolean);
  const matches = options.filter((option) => {
    const text = searchText(`${option.name} ${option.id} ${option.category}`);
    return words.every((word) => text.includes(word));
  });
  const selected = options.find((option) => option.id === selectedId);
  const activeIndex = matches.findIndex((option) => option.id === activeId);
  const activeOptionId = open && activeIndex >= 0 ? `${listId}-${activeId}` : undefined;

  useEffect(() => {
    if (activeOptionId) document.getElementById(activeOptionId)?.scrollIntoView({ block: "nearest" });
  }, [activeOptionId]);

  function close() {
    setOpen(false);
    setQuery("");
    setActiveId("");
  }

  function select(optionId: string) {
    onSelect(optionId);
    close();
  }

  function handleKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      close();
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = matches[activeIndex] ?? (matches.length === 1 ? matches[0] : undefined);
      if (open && option) select(option.id);
      else setOpen(true);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      if (matches.length === 0) return;
      const last = matches.length - 1;
      const next = event.key === "ArrowDown"
        ? (activeIndex === last ? 0 : activeIndex + 1)
        : (activeIndex <= 0 ? last : activeIndex - 1);
      setActiveId(matches[next].id);
    }
  }

  return (
    <div className="field criterion-picker">
      <label htmlFor={id}>Add a Supported Criterion</label>
      <input
        id={id}
        type="search"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open && !disabled}
        aria-controls={listId}
        aria-activedescendant={disabled ? undefined : activeOptionId}
        autoComplete="off"
        placeholder={open ? "Search criteria" : "Choose a criterion"}
        value={open ? query : selected?.name ?? ""}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        onBlur={close}
        onChange={(event) => {
          setQuery(event.target.value);
          setActiveId("");
          if (selectedId) onSelect("");
          setOpen(true);
        }}
        onKeyDown={handleKey}
      />
      <div className="criterion-picker-menu" hidden={!open || disabled}>
        <ul id={listId} role="listbox" aria-label="Supported criteria">
          {matches.map((option) => (
            <li
              key={option.id}
              id={`${listId}-${option.id}`}
              role="option"
              aria-selected={option.id === activeId}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => select(option.id)}
            >
              {option.name} · {option.category}
            </li>
          ))}
        </ul>
        {matches.length === 0 && <p role="status">No matching criteria.</p>}
      </div>
    </div>
  );
}
