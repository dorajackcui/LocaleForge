from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config.tasks import TaskConfig, get_task_config, get_task_config_by_display_name, get_task_display_names
from ..prompts import default_prompt_path, resolve_prompt_path_for_task_switch
from ..runtime import TaskRunRequest, TaskRunResult, run_task
from ..workbook import default_output_path, get_workbook_sheet_names
from .helpers import ValidationError, build_run_request, format_completion_lines, format_progress_message


class TranslationCheckerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Local Translation Checker")
        self.root.geometry("880x620")
        self.root.minsize(820, 560)

        default_task = get_task_config()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self._selected_task_id = default_task.task_id
        self._running_task: TaskConfig | None = None

        self.task_var = tk.StringVar(value=default_task.display_name)
        self.input_var = tk.StringVar(value="")
        self.output_var = tk.StringVar(value="")
        self.sheet_var = tk.StringVar(value="Sheet1")
        self.source_col_var = tk.StringVar(value="C")
        self.result_col_var = tk.StringVar(value="F")
        self.start_row_var = tk.StringVar(value="2")
        self.model_var = tk.StringVar(value="gemma4:e4b")
        self.api_url_var = tk.StringVar(value="http://127.0.0.1:11434")
        self.prompt_file_var = tk.StringVar(value=str(default_prompt_path(default_task.task_id)))
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._load_sheets_from_current_file()
        self.root.after(120, self._poll_events)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        top = ttk.LabelFrame(outer, text="Task", padding=12)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Task").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.task_box = ttk.Combobox(
            top,
            textvariable=self.task_var,
            values=get_task_display_names(),
            state="readonly",
        )
        self.task_box.grid(row=0, column=1, sticky="ew")
        self.task_box.bind("<<ComboboxSelected>>", self._on_task_changed)

        config = ttk.LabelFrame(outer, text="Input", padding=12)
        config.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        for column in range(0, 4):
            config.columnconfigure(column, weight=0)
        config.columnconfigure(1, weight=1)
        config.columnconfigure(3, weight=1)

        ttk.Label(config, text="Excel file").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(config, textvariable=self.input_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(config, text="Browse...", command=self._choose_input_file).grid(
            row=0,
            column=2,
            sticky="w",
            padx=(12, 0),
        )
        ttk.Button(config, text="Load sheets", command=self._load_sheets_from_current_file).grid(
            row=0,
            column=3,
            sticky="w",
            padx=(12, 0),
        )

        ttk.Label(config, text="Output file").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(config, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(config, text="Save as...", command=self._choose_output_file).grid(
            row=1,
            column=2,
            sticky="w",
            padx=(12, 0),
            pady=(10, 0),
        )

        ttk.Label(config, text="Sheet").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        self.sheet_box = ttk.Combobox(config, textvariable=self.sheet_var, state="readonly")
        self.sheet_box.grid(row=2, column=1, sticky="w", pady=(10, 0))

        ttk.Label(config, text="Source col").grid(row=2, column=2, sticky="e", padx=(16, 8), pady=(10, 0))
        ttk.Entry(config, textvariable=self.source_col_var, width=8).grid(
            row=2,
            column=3,
            sticky="w",
            pady=(10, 0),
        )

        ttk.Label(config, text="Output col").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(config, textvariable=self.result_col_var, width=8).grid(
            row=3,
            column=1,
            sticky="w",
            pady=(10, 0),
        )

        ttk.Label(config, text="Start row").grid(row=3, column=2, sticky="e", padx=(16, 8), pady=(10, 0))
        ttk.Entry(config, textvariable=self.start_row_var, width=8).grid(
            row=3,
            column=3,
            sticky="w",
            pady=(10, 0),
        )

        advanced = ttk.LabelFrame(outer, text="Runtime", padding=12)
        advanced.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        advanced.columnconfigure(1, weight=1)

        ttk.Label(advanced, text="Model").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(advanced, textvariable=self.model_var).grid(row=0, column=1, sticky="ew")
        ttk.Label(advanced, text="API URL").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(advanced, textvariable=self.api_url_var).grid(row=1, column=1, sticky="ew", pady=(10, 0))
        ttk.Label(advanced, text="Prompt file").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(advanced, textvariable=self.prompt_file_var).grid(row=2, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(advanced, text="Browse...", command=self._choose_prompt_file).grid(
            row=2,
            column=2,
            sticky="w",
            padx=(12, 0),
            pady=(10, 0),
        )

        activity = ttk.LabelFrame(outer, text="Run", padding=12)
        activity.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(2, weight=1)

        actions = ttk.Frame(activity)
        actions.grid(row=0, column=0, sticky="ew")
        actions.columnconfigure(1, weight=1)

        self.run_button = ttk.Button(actions, text="Run Task", command=self._start_run)
        self.run_button.grid(row=0, column=0, sticky="w")
        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=1, sticky="e")

        self.progress = ttk.Progressbar(activity, mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        self.log_text = tk.Text(activity, height=18, wrap="word")
        self.log_text.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self.log_text.configure(state="disabled")

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _current_task_config(self) -> TaskConfig:
        return get_task_config_by_display_name(self.task_var.get())

    def _on_task_changed(self, _event: object = None) -> None:
        previous_task = get_task_config(self._selected_task_id)
        new_task = self._current_task_config()
        self.prompt_file_var.set(
            resolve_prompt_path_for_task_switch(
                self.prompt_file_var.get(),
                previous_task,
                new_task,
            )
        )
        self._selected_task_id = new_task.task_id

    def _choose_input_file(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Select Excel file",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if not chosen:
            return
        self.input_var.set(chosen)
        self.output_var.set(str(default_output_path(Path(chosen))))
        self._load_sheets_from_current_file()

    def _choose_output_file(self) -> None:
        current_input = Path(self.input_var.get()).expanduser()
        initial = default_output_path(current_input) if current_input.name else Path("result_checked.xlsx")
        chosen = filedialog.asksaveasfilename(
            title="Select output file",
            defaultextension=".xlsx",
            initialfile=initial.name,
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if chosen:
            self.output_var.set(chosen)

    def _load_sheets_from_current_file(self) -> None:
        path = Path(self.input_var.get()).expanduser()
        if not path.exists():
            self.sheet_box["values"] = ()
            return
        try:
            sheets = get_workbook_sheet_names(path)
        except Exception as exc:
            self.sheet_box["values"] = ()
            self._append_log(f"Failed to load sheets: {exc}")
            return

        self.sheet_box["values"] = sheets
        if self.sheet_var.get() not in sheets and sheets:
            self.sheet_var.set(sheets[0])

    def _choose_prompt_file(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Select prompt file",
            filetypes=[("Text files", "*.txt"), ("Markdown files", "*.md"), ("All files", "*.*")],
        )
        if chosen:
            self.prompt_file_var.set(chosen)

    def _validate(self) -> TaskRunRequest | None:
        try:
            return build_run_request(
                task_config=self._current_task_config(),
                input_text=self.input_var.get(),
                output_text=self.output_var.get(),
                prompt_text=self.prompt_file_var.get(),
                source_col_text=self.source_col_var.get(),
                result_col_text=self.result_col_var.get(),
                start_row_text=self.start_row_var.get(),
                sheet_name=self.sheet_var.get(),
                model=self.model_var.get(),
                api_url=self.api_url_var.get(),
            )
        except ValidationError as exc:
            message = str(exc)
            if "Excel file" in message:
                messagebox.showerror("Input error", message)
            elif "prompt file" in message:
                messagebox.showerror("Prompt error", message)
            elif "column" in message.lower():
                messagebox.showerror("Column error", message)
            else:
                messagebox.showerror("Row error", message)
            return None

    def _set_running(self, running: bool) -> None:
        self.run_button.configure(state="disabled" if running else "normal")
        self.task_box.configure(state="disabled" if running else "readonly")

    def _start_run(self) -> None:
        request = self._validate()
        if request is None:
            return
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo("Busy", "A task is already running.")
            return

        self._running_task = request.task_config
        self._set_running(True)
        self.progress.configure(value=0, maximum=100)
        self.status_var.set("Running...")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._append_log(f"Task  : {request.task_config.task_id}")
        self._append_log(f"Input : {request.input_path}")
        self._append_log(f"Output: {request.output_path}")
        self._append_log(f"Sheet : {request.sheet_name}")
        self._append_log(f"Model : {request.model}")
        self._append_log(f"Prompt: {request.prompt_path}")

        self.worker = threading.Thread(target=self._run_worker, args=(request,), daemon=True)
        self.worker.start()

    def _run_worker(self, request: TaskRunRequest) -> None:
        try:
            result = run_task(
                request,
                progress_callback=lambda offset, total_rows, row_idx, stats: self.events.put(
                    ("progress", (offset, total_rows, row_idx, stats))
                ),
                log_callback=lambda message: self.events.put(("log", message)),
            )
            self.events.put(("done", result))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break

            running_task = self._running_task or get_task_config()
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "progress":
                offset, total_rows, row_idx, stats = payload  # type: ignore[misc]
                self.progress.configure(maximum=max(total_rows, 1), value=offset)
                self.status_var.set(f"Running... {offset}/{total_rows}")
                if offset % 50 == 0 or offset == total_rows:
                    self._append_log(
                        format_progress_message(offset, total_rows, row_idx, stats, running_task)
                    )
            elif kind == "done":
                result = payload  # type: ignore[assignment]
                if not isinstance(result, TaskRunResult):
                    raise RuntimeError("Unexpected worker result payload.")
                self._set_running(False)
                self.progress.configure(value=self.progress["maximum"])
                self.status_var.set("Finished")
                self._append_log("")
                for line in format_completion_lines(
                    result.total_rows,
                    result.stats,
                    result.output_path,
                    running_task,
                ):
                    self._append_log(line)
                self._running_task = None
                messagebox.showinfo("Done", f"Task finished.\n\nSaved to:\n{result.output_path}")
            elif kind == "error":
                self._set_running(False)
                self.status_var.set("Failed")
                self._append_log(f"Error: {payload}")
                self._running_task = None
                messagebox.showerror("Run failed", str(payload))

        self.root.after(120, self._poll_events)


def main() -> None:
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    TranslationCheckerApp(root)
    root.mainloop()
