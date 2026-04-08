from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from check_excel_translations import (
    OllamaClient,
    STATUS_EMPTY,
    STATUS_OK,
    STATUS_SUSPECT,
    default_output_path,
    default_input_path,
    get_workbook_sheet_names,
    process_workbook,
)


class TranslationCheckerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Local Translation Checker")
        self.root.geometry("880x620")
        self.root.minsize(820, 560)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.task_var = tk.StringVar(value="French translation English leak check")
        self.input_var = tk.StringVar(value=str(default_input_path()))
        self.output_var = tk.StringVar(value=str(default_output_path(default_input_path())))
        self.sheet_var = tk.StringVar(value="Sheet1")
        self.source_col_var = tk.StringVar(value="C")
        self.result_col_var = tk.StringVar(value="F")
        self.start_row_var = tk.StringVar(value="2")
        self.model_var = tk.StringVar(value="gemma4:e4b")
        self.api_url_var = tk.StringVar(value="http://127.0.0.1:11434")
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
        task_box = ttk.Combobox(
            top,
            textvariable=self.task_var,
            values=[self.task_var.get()],
            state="readonly",
        )
        task_box.grid(row=0, column=1, sticky="ew")

        config = ttk.LabelFrame(outer, text="Input", padding=12)
        config.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        for column in range(0, 4):
            config.columnconfigure(column, weight=0)
        config.columnconfigure(1, weight=1)
        config.columnconfigure(3, weight=1)

        ttk.Label(config, text="Excel file").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(config, textvariable=self.input_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(config, text="Browse...", command=self._choose_input_file).grid(
            row=0, column=2, sticky="w", padx=(12, 0)
        )
        ttk.Button(config, text="Load sheets", command=self._load_sheets_from_current_file).grid(
            row=0, column=3, sticky="w", padx=(12, 0)
        )

        ttk.Label(config, text="Output file").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(config, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(config, text="Save as...", command=self._choose_output_file).grid(
            row=1, column=2, sticky="w", padx=(12, 0), pady=(10, 0)
        )

        ttk.Label(config, text="Sheet").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        self.sheet_box = ttk.Combobox(config, textvariable=self.sheet_var, state="readonly")
        self.sheet_box.grid(row=2, column=1, sticky="w", pady=(10, 0))

        ttk.Label(config, text="Source col").grid(row=2, column=2, sticky="e", padx=(16, 8), pady=(10, 0))
        ttk.Entry(config, textvariable=self.source_col_var, width=8).grid(
            row=2, column=3, sticky="w", pady=(10, 0)
        )

        ttk.Label(config, text="Output col").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(config, textvariable=self.result_col_var, width=8).grid(
            row=3, column=1, sticky="w", pady=(10, 0)
        )

        ttk.Label(config, text="Start row").grid(row=3, column=2, sticky="e", padx=(16, 8), pady=(10, 0))
        ttk.Entry(config, textvariable=self.start_row_var, width=8).grid(
            row=3, column=3, sticky="w", pady=(10, 0)
        )

        advanced = ttk.LabelFrame(outer, text="Runtime", padding=12)
        advanced.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        advanced.columnconfigure(1, weight=1)

        ttk.Label(advanced, text="Model").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(advanced, textvariable=self.model_var).grid(row=0, column=1, sticky="ew")
        ttk.Label(advanced, text="API URL").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(advanced, textvariable=self.api_url_var).grid(row=1, column=1, sticky="ew", pady=(10, 0))

        activity = ttk.LabelFrame(outer, text="Run", padding=12)
        activity.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(2, weight=1)

        actions = ttk.Frame(activity)
        actions.grid(row=0, column=0, sticky="ew")
        actions.columnconfigure(1, weight=1)

        self.run_button = ttk.Button(actions, text="Run Check", command=self._start_run)
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

    def _validate(self) -> tuple[Path, Path, int] | None:
        input_path = Path(self.input_var.get()).expanduser()
        output_path = Path(self.output_var.get()).expanduser()

        if not input_path.exists():
            messagebox.showerror("Input error", "Please choose an existing Excel file.")
            return None

        for label, value in (
            ("Source column", self.source_col_var.get()),
            ("Output column", self.result_col_var.get()),
        ):
            if not value.strip().isalpha():
                messagebox.showerror("Column error", f"{label} must be letters like C or F.")
                return None

        try:
            start_row = int(self.start_row_var.get())
        except ValueError:
            messagebox.showerror("Row error", "Start row must be an integer.")
            return None

        if start_row < 1:
            messagebox.showerror("Row error", "Start row must be at least 1.")
            return None

        return input_path.resolve(), output_path.resolve(), start_row

    def _set_running(self, running: bool) -> None:
        self.run_button.configure(state="disabled" if running else "normal")

    def _start_run(self) -> None:
        validated = self._validate()
        if validated is None:
            return
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo("Busy", "A check is already running.")
            return

        input_path, output_path, start_row = validated
        self._set_running(True)
        self.progress.configure(value=0, maximum=100)
        self.status_var.set("Running...")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._append_log(f"Input : {input_path}")
        self._append_log(f"Output: {output_path}")
        self._append_log(f"Sheet : {self.sheet_var.get()}")
        self._append_log(f"Model : {self.model_var.get()}")

        self.worker = threading.Thread(
            target=self._run_worker,
            args=(input_path, output_path, start_row),
            daemon=True,
        )
        self.worker.start()

    def _run_worker(self, input_path: Path, output_path: Path, start_row: int) -> None:
        try:
            client = OllamaClient(
                api_url=self.api_url_var.get().strip(),
                model=self.model_var.get().strip(),
                timeout=120.0,
            )
            self.events.put(("log", "Checking local Ollama service..."))
            client.ensure_available()
            self.events.put(("log", "Ollama is ready. Starting workbook processing..."))

            def on_progress(offset: int, total_rows: int, row_idx: int, stats: dict[str, int]) -> None:
                self.events.put(("progress", (offset, total_rows, row_idx, stats)))

            total_rows, stats = process_workbook(
                input_path=input_path,
                output_path=output_path,
                sheet_name=self.sheet_var.get().strip(),
                source_col=self.source_col_var.get().strip().upper(),
                result_col=self.result_col_var.get().strip().upper(),
                start_row=start_row,
                client=client,
                progress_callback=on_progress,
            )
            self.events.put(("done", (output_path, total_rows, stats)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._append_log(str(payload))
            elif kind == "progress":
                offset, total_rows, row_idx, stats = payload  # type: ignore[misc]
                self.progress.configure(maximum=max(total_rows, 1), value=offset)
                self.status_var.set(f"Running... {offset}/{total_rows}")
                if offset % 50 == 0 or offset == total_rows:
                    self._append_log(
                        f"[{offset}/{total_rows}] row={row_idx} "
                        f"OK={stats[STATUS_OK]} "
                        f"SUSPECT={stats[STATUS_SUSPECT]} "
                        f"EMPTY={stats[STATUS_EMPTY]} "
                        f"MODEL={stats['MODEL_CALLS']}"
                    )
            elif kind == "done":
                output_path, total_rows, stats = payload  # type: ignore[misc]
                self._set_running(False)
                self.progress.configure(value=self.progress["maximum"])
                self.status_var.set("Finished")
                self._append_log("")
                self._append_log("Finished.")
                self._append_log(f"Rows processed : {total_rows}")
                self._append_log(f"{STATUS_OK}: {stats[STATUS_OK]}")
                self._append_log(f"{STATUS_SUSPECT}: {stats[STATUS_SUSPECT]}")
                self._append_log(f"{STATUS_EMPTY}: {stats[STATUS_EMPTY]}")
                self._append_log(f"MODEL_CALLS: {stats['MODEL_CALLS']}")
                self._append_log(f"CACHE_HITS : {stats['CACHE_HITS']}")
                self._append_log(f"Saved to   : {output_path}")
                messagebox.showinfo("Done", f"Check finished.\n\nSaved to:\n{output_path}")
            elif kind == "error":
                self._set_running(False)
                self.status_var.set("Failed")
                self._append_log(f"Error: {payload}")
                messagebox.showerror("Run failed", str(payload))

        self.root.after(120, self._poll_events)


def main() -> None:
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    app = TranslationCheckerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
