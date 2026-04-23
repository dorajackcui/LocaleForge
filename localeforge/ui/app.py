from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config.settings import DEFAULT_LOCAL_BASE_URL, DEFAULT_LOCAL_MODEL, AppSettings, load_settings, save_settings
from ..config.tasks import TaskConfig, get_task_config, get_task_config_by_display_name, get_task_display_names
from ..prompts import default_prompt_path, resolve_prompt_path_for_task_switch
from ..runtime import TaskRunRequest, TaskRunResult, run_task
from ..workbook import default_output_path, get_workbook_sheet_names
from .helpers import (
    ValidationError,
    api_provider_is_ready,
    build_run_request,
    format_completion_lines,
    format_progress_message,
    get_api_provider_models,
)
from .settings_dialog import LLMSettingsWindow


class TranslationCheckerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LocaleForge")
        self.root.geometry("960x700")
        self.root.minsize(900, 620)

        default_task = get_task_config()
        self.settings = load_settings()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self._selected_task_id = default_task.task_id
        self._running_task: TaskConfig | None = None
        self._sync_suspended = False

        self.task_var = tk.StringVar(value=default_task.display_name)
        self.input_var = tk.StringVar(value="")
        self.output_var = tk.StringVar(value="")
        self.sheet_var = tk.StringVar(value="Sheet1")
        self.source_col_var = tk.StringVar(value="C")
        self.result_col_var = tk.StringVar(value="F")
        self.start_row_var = tk.StringVar(value="2")
        self.execution_mode_var = tk.StringVar(value=self.settings.defaults.execution_mode)
        self.local_model_var = tk.StringVar(value=self.settings.defaults.local.model or DEFAULT_LOCAL_MODEL)
        self.local_api_url_var = tk.StringVar(value=self.settings.defaults.local.base_url or DEFAULT_LOCAL_BASE_URL)
        self.local_concurrency_var = tk.StringVar(value=str(self.settings.defaults.local.concurrency))
        self.api_provider_var = tk.StringVar(value=self.settings.defaults.api.provider_id or "")
        self.api_model_var = tk.StringVar(value=self.settings.defaults.api.model)
        self.api_concurrency_var = tk.StringVar(value=str(self.settings.defaults.api.concurrency))
        self.prompt_file_var = tk.StringVar(value=str(default_prompt_path(default_task.task_id)))
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._bind_runtime_events()
        self._refresh_provider_options()
        self._refresh_runtime_mode_ui()
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

        ttk.Label(advanced, text="Run with").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.execution_mode_box = ttk.Combobox(
            advanced,
            textvariable=self.execution_mode_var,
            values=("local", "api"),
            state="readonly",
        )
        self.execution_mode_box.grid(row=0, column=1, sticky="w")
        self.settings_button = ttk.Button(advanced, text="LLM Settings...", command=self._open_llm_settings)
        self.settings_button.grid(row=0, column=2, sticky="e")

        self.local_runtime = ttk.Frame(advanced)
        self.local_runtime.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.local_runtime.columnconfigure(1, weight=1)

        ttk.Label(self.local_runtime, text="Model").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.local_model_entry = ttk.Entry(self.local_runtime, textvariable=self.local_model_var)
        self.local_model_entry.grid(row=0, column=1, sticky="ew")
        ttk.Label(self.local_runtime, text="Concurrency").grid(row=0, column=2, sticky="e", padx=(16, 8))
        self.local_concurrency_entry = ttk.Entry(self.local_runtime, textvariable=self.local_concurrency_var, width=8)
        self.local_concurrency_entry.grid(row=0, column=3, sticky="w")
        ttk.Label(self.local_runtime, text="API URL").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        self.local_api_url_entry = ttk.Entry(self.local_runtime, textvariable=self.local_api_url_var)
        self.local_api_url_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(10, 0))

        self.api_runtime = ttk.Frame(advanced)
        self.api_runtime.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.api_runtime.columnconfigure(1, weight=1)

        ttk.Label(self.api_runtime, text="Provider").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.api_provider_box = ttk.Combobox(
            self.api_runtime,
            textvariable=self.api_provider_var,
            state="readonly",
        )
        self.api_provider_box.grid(row=0, column=1, sticky="ew")
        ttk.Label(self.api_runtime, text="Concurrency").grid(row=0, column=2, sticky="e", padx=(16, 8))
        self.api_concurrency_entry = ttk.Entry(self.api_runtime, textvariable=self.api_concurrency_var, width=8)
        self.api_concurrency_entry.grid(row=0, column=3, sticky="w")
        ttk.Label(self.api_runtime, text="Model").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        self.api_model_box = ttk.Combobox(
            self.api_runtime,
            textvariable=self.api_model_var,
            state="readonly",
        )
        self.api_model_box.grid(row=1, column=1, sticky="ew", pady=(10, 0))

        ttk.Label(advanced, text="Prompt file").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(advanced, textvariable=self.prompt_file_var).grid(row=2, column=1, sticky="ew", pady=(10, 0))
        self.prompt_button = ttk.Button(advanced, text="Browse...", command=self._choose_prompt_file)
        self.prompt_button.grid(
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

    def _bind_runtime_events(self) -> None:
        self.execution_mode_box.bind("<<ComboboxSelected>>", self._on_execution_mode_changed)
        self.api_provider_box.bind("<<ComboboxSelected>>", self._on_api_provider_changed)
        self.api_model_box.bind("<<ComboboxSelected>>", lambda _event: self._persist_runtime_defaults())
        for widget in (
            self.local_model_entry,
            self.local_api_url_entry,
            self.local_concurrency_entry,
            self.api_concurrency_entry,
        ):
            widget.bind("<FocusOut>", lambda _event: self._persist_runtime_defaults())
            widget.bind("<Return>", lambda _event: self._persist_runtime_defaults())

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

    def _open_llm_settings(self) -> None:
        dialog = LLMSettingsWindow(self.root, self.settings)
        self.root.wait_window(dialog.window)
        self._reload_settings()

    def _reload_settings(self) -> None:
        self.settings = load_settings()
        self._sync_suspended = True
        self.execution_mode_var.set(self.settings.defaults.execution_mode)
        self.local_model_var.set(self.settings.defaults.local.model or DEFAULT_LOCAL_MODEL)
        self.local_api_url_var.set(self.settings.defaults.local.base_url or DEFAULT_LOCAL_BASE_URL)
        self.local_concurrency_var.set(str(self.settings.defaults.local.concurrency))
        self.api_provider_var.set(self.settings.defaults.api.provider_id or "")
        self.api_model_var.set(self.settings.defaults.api.model)
        self.api_concurrency_var.set(str(self.settings.defaults.api.concurrency))
        self._sync_suspended = False
        self._refresh_provider_options()
        self._refresh_runtime_mode_ui()

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

    def _refresh_provider_options(self) -> None:
        provider_ids = [provider.provider_id for provider in self.settings.providers]
        self.api_provider_box["values"] = provider_ids
        if self.api_provider_var.get() not in provider_ids:
            self.api_provider_var.set(provider_ids[0] if provider_ids else "")
        self._refresh_api_model_options()

    def _refresh_api_model_options(self) -> None:
        models = get_api_provider_models(self.settings, self.api_provider_var.get().strip() or None)
        self.api_model_box["values"] = models
        if self.api_model_var.get() not in models:
            self.api_model_var.set(models[0] if models else "")

    def _safe_concurrency_value(self, raw: str, fallback: int) -> int:
        try:
            return int(raw)
        except ValueError:
            return fallback

    def _persist_runtime_defaults(self) -> None:
        if self._sync_suspended:
            return

        self.settings.defaults.execution_mode = self.execution_mode_var.get().strip() or "local"
        self.settings.defaults.local.base_url = self.local_api_url_var.get().strip() or DEFAULT_LOCAL_BASE_URL
        self.settings.defaults.local.model = self.local_model_var.get().strip() or DEFAULT_LOCAL_MODEL
        self.settings.defaults.local.concurrency = self._safe_concurrency_value(
            self.local_concurrency_var.get(),
            self.settings.defaults.local.concurrency,
        )

        provider_id = self.api_provider_var.get().strip() or None
        models = get_api_provider_models(self.settings, provider_id)
        if self.api_model_var.get().strip() not in models:
            self._sync_suspended = True
            self.api_model_var.set(models[0] if models else "")
            self._sync_suspended = False

        self.settings.defaults.api.provider_id = provider_id
        self.settings.defaults.api.model = self.api_model_var.get().strip()
        self.settings.defaults.api.concurrency = self._safe_concurrency_value(
            self.api_concurrency_var.get(),
            self.settings.defaults.api.concurrency,
        )
        save_settings(self.settings)
        self._refresh_runtime_mode_ui()

    def _on_execution_mode_changed(self, _event: object = None) -> None:
        self._persist_runtime_defaults()

    def _on_api_provider_changed(self, _event: object = None) -> None:
        self._refresh_api_model_options()
        self._persist_runtime_defaults()

    def _refresh_runtime_mode_ui(self) -> None:
        if self.execution_mode_var.get() == "api":
            self.local_runtime.grid_remove()
            self.api_runtime.grid()
        else:
            self.api_runtime.grid_remove()
            self.local_runtime.grid()
        self._update_run_button_state()
        self._set_idle_status()

    def _set_idle_status(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        if self.execution_mode_var.get() == "api" and not api_provider_is_ready(
            self.settings,
            self.api_provider_var.get().strip() or None,
        ):
            self.status_var.set("Configure API provider")
        else:
            self.status_var.set("Ready")

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
                settings=self.settings,
                execution_mode=self.execution_mode_var.get(),
                provider_id=self.api_provider_var.get(),
                model=self.local_model_var.get() if self.execution_mode_var.get() == "local" else self.api_model_var.get(),
                api_url=self.local_api_url_var.get() if self.execution_mode_var.get() == "local" else "",
                concurrency_text=(
                    self.local_concurrency_var.get()
                    if self.execution_mode_var.get() == "local"
                    else self.api_concurrency_var.get()
                ),
            )
        except ValidationError as exc:
            message = str(exc)
            if "Excel file" in message:
                messagebox.showerror("Input error", message)
            elif "prompt file" in message:
                messagebox.showerror("Prompt error", message)
            elif "column" in message.lower():
                messagebox.showerror("Column error", message)
            elif "row" in message.lower():
                messagebox.showerror("Row error", message)
            else:
                messagebox.showerror("Runtime error", message)
            return None

    def _set_running(self, running: bool) -> None:
        self.task_box.configure(state="disabled" if running else "readonly")
        self.execution_mode_box.configure(state="disabled" if running else "readonly")
        self.api_provider_box.configure(state="disabled" if running else "readonly")
        self.api_model_box.configure(state="disabled" if running else "readonly")
        self.local_model_entry.configure(state="disabled" if running else "normal")
        self.local_api_url_entry.configure(state="disabled" if running else "normal")
        self.local_concurrency_entry.configure(state="disabled" if running else "normal")
        self.api_concurrency_entry.configure(state="disabled" if running else "normal")
        self.settings_button.configure(state="disabled" if running else "normal")
        self.prompt_button.configure(state="disabled" if running else "normal")
        self._update_run_button_state()

    def _update_run_button_state(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.run_button.configure(state="disabled")
            return
        if self.execution_mode_var.get() == "api":
            provider_id = self.api_provider_var.get().strip() or None
            ready = api_provider_is_ready(self.settings, provider_id) and bool(self.api_model_var.get().strip())
            self.run_button.configure(state="normal" if ready else "disabled")
            return
        self.run_button.configure(state="normal")

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
        self._append_log(f"Mode  : {request.execution_mode}")
        if request.provider_id:
            self._append_log(f"Provider: {request.provider_id}")
        self._append_log(f"Input : {request.input_path}")
        self._append_log(f"Output: {request.output_path}")
        self._append_log(f"Sheet : {request.sheet_name}")
        self._append_log(f"Model : {request.model}")
        self._append_log(f"Concurrency: {request.concurrency}")
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
