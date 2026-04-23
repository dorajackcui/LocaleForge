from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..config.settings import (
    MAX_CONCURRENCY,
    MIN_CONCURRENCY,
    AppSettings,
    ProviderConfig,
    ProviderMutationError,
    delete_provider,
    get_provider,
    save_settings,
    upsert_provider,
)
from ..config.tasks import get_task_config
from ..model.openai_compatible import OpenAICompatibleClient
from .helpers import get_api_provider_models


class LLMSettingsWindow:
    def __init__(self, root: tk.Tk, settings: AppSettings) -> None:
        self.settings = settings
        self.window = tk.Toplevel(root)
        self.window.title("LLM Settings")
        self.window.geometry("920x700")
        self.window.minsize(860, 620)
        self.window.transient(root)
        self.window.grab_set()

        self._loading_provider = False
        self._provider_ids: list[str] = []
        self._selected_provider_id: str | None = None
        self._tested_models: list[str] | None = None
        self._last_tested_identity: tuple[str, str, str] | None = None

        self.provider_id_var = tk.StringVar(value="")
        self.provider_name_var = tk.StringVar(value="")
        self.provider_base_url_var = tk.StringVar(value="")
        self.provider_api_key_var = tk.StringVar(value="")
        self.provider_models_var = tk.StringVar(value="")
        self.provider_status_var = tk.StringVar(value="Create or select a provider, then test it before saving.")

        self.default_execution_mode_var = tk.StringVar(value=self.settings.defaults.execution_mode)
        self.default_local_base_url_var = tk.StringVar(value=self.settings.defaults.local.base_url)
        self.default_local_model_var = tk.StringVar(value=self.settings.defaults.local.model)
        self.default_local_concurrency_var = tk.StringVar(value=str(self.settings.defaults.local.concurrency))
        self.default_api_provider_var = tk.StringVar(value=self.settings.defaults.api.provider_id or "")
        self.default_api_model_var = tk.StringVar(value=self.settings.defaults.api.model)
        self.default_api_concurrency_var = tk.StringVar(value=str(self.settings.defaults.api.concurrency))

        self._build_ui()
        self._refresh_provider_list()
        self._refresh_default_provider_values()
        self._refresh_default_api_models()
        self.provider_id_var.trace_add("write", self._on_provider_identity_changed)
        self.provider_base_url_var.trace_add("write", self._on_provider_identity_changed)
        self.provider_api_key_var.trace_add("write", self._on_provider_identity_changed)

    def _build_ui(self) -> None:
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        outer = ttk.Frame(self.window, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        provider_frame = ttk.LabelFrame(outer, text="Providers", padding=12)
        provider_frame.grid(row=0, column=0, sticky="nsew")
        provider_frame.columnconfigure(1, weight=1)
        provider_frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(provider_frame)
        list_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        list_frame.rowconfigure(0, weight=1)

        self.provider_list = tk.Listbox(list_frame, exportselection=False, height=14)
        self.provider_list.grid(row=0, column=0, sticky="ns")
        self.provider_list.bind("<<ListboxSelect>>", self._on_provider_selected)

        form = ttk.Frame(provider_frame)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Provider ID").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(form, textvariable=self.provider_id_var).grid(row=0, column=1, sticky="ew")

        ttk.Label(form, text="Name").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(form, textvariable=self.provider_name_var).grid(row=1, column=1, sticky="ew", pady=(10, 0))

        ttk.Label(form, text="Base URL").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(form, textvariable=self.provider_base_url_var).grid(row=2, column=1, sticky="ew", pady=(10, 0))

        ttk.Label(form, text="API Key").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(form, textvariable=self.provider_api_key_var, show="*").grid(row=3, column=1, sticky="ew", pady=(10, 0))

        ttk.Label(form, text="Tested Models").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(form, textvariable=self.provider_models_var, state="readonly").grid(
            row=4,
            column=1,
            sticky="ew",
            pady=(10, 0),
        )

        ttk.Label(form, textvariable=self.provider_status_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))

        provider_actions = ttk.Frame(form)
        provider_actions.grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 0))

        ttk.Button(provider_actions, text="New", command=self._new_provider).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(provider_actions, text="Test", command=self._test_provider).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(provider_actions, text="Save", command=self._save_provider).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(provider_actions, text="Delete", command=self._delete_provider).grid(row=0, column=3)

        defaults_frame = ttk.LabelFrame(outer, text="Defaults", padding=12)
        defaults_frame.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        defaults_frame.columnconfigure(1, weight=1)
        defaults_frame.columnconfigure(3, weight=1)

        ttk.Label(defaults_frame, text="Execution mode").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Combobox(
            defaults_frame,
            textvariable=self.default_execution_mode_var,
            values=("local", "api"),
            state="readonly",
        ).grid(row=0, column=1, sticky="w")

        ttk.Label(defaults_frame, text="Local base URL").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(defaults_frame, textvariable=self.default_local_base_url_var).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=(10, 0),
        )

        ttk.Label(defaults_frame, text="Local model").grid(row=1, column=2, sticky="w", padx=(16, 12), pady=(10, 0))
        ttk.Entry(defaults_frame, textvariable=self.default_local_model_var).grid(
            row=1,
            column=3,
            sticky="ew",
            pady=(10, 0),
        )

        ttk.Label(defaults_frame, text="Local concurrency").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(defaults_frame, textvariable=self.default_local_concurrency_var, width=8).grid(
            row=2,
            column=1,
            sticky="w",
            pady=(10, 0),
        )

        ttk.Label(defaults_frame, text="API provider").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        self.default_api_provider_box = ttk.Combobox(
            defaults_frame,
            textvariable=self.default_api_provider_var,
            state="readonly",
        )
        self.default_api_provider_box.grid(row=3, column=1, sticky="ew", pady=(10, 0))
        self.default_api_provider_box.bind("<<ComboboxSelected>>", self._on_default_api_provider_changed)

        ttk.Label(defaults_frame, text="API model").grid(row=3, column=2, sticky="w", padx=(16, 12), pady=(10, 0))
        self.default_api_model_box = ttk.Combobox(
            defaults_frame,
            textvariable=self.default_api_model_var,
            state="readonly",
        )
        self.default_api_model_box.grid(row=3, column=3, sticky="ew", pady=(10, 0))

        ttk.Label(defaults_frame, text="API concurrency").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ttk.Entry(defaults_frame, textvariable=self.default_api_concurrency_var, width=8).grid(
            row=4,
            column=1,
            sticky="w",
            pady=(10, 0),
        )

        defaults_actions = ttk.Frame(defaults_frame)
        defaults_actions.grid(row=5, column=0, columnspan=4, sticky="w", pady=(12, 0))
        ttk.Button(defaults_actions, text="Save Defaults", command=self._save_defaults).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(defaults_actions, text="Close", command=self.window.destroy).grid(row=0, column=1)

    def _refresh_provider_list(self, selected_provider_id: str | None = None) -> None:
        self.provider_list.delete(0, "end")
        sorted_providers = sorted(self.settings.providers, key=lambda item: (item.name.lower(), item.provider_id.lower()))
        self._provider_ids = [provider.provider_id for provider in sorted_providers]
        for provider in sorted_providers:
            self.provider_list.insert("end", f"{provider.name} ({provider.provider_id})")

        if selected_provider_id and selected_provider_id in self._provider_ids:
            index = self._provider_ids.index(selected_provider_id)
            self.provider_list.selection_clear(0, "end")
            self.provider_list.selection_set(index)
            self.provider_list.activate(index)
            self._load_provider(get_provider(self.settings, selected_provider_id))
        elif not self._provider_ids:
            self._new_provider()

        self._refresh_default_provider_values()

    def _new_provider(self) -> None:
        self._selected_provider_id = None
        self._tested_models = None
        self._last_tested_identity = None
        self._loading_provider = True
        self.provider_list.selection_clear(0, "end")
        self.provider_id_var.set("")
        self.provider_name_var.set("")
        self.provider_base_url_var.set("")
        self.provider_api_key_var.set("")
        self.provider_models_var.set("")
        self.provider_status_var.set("New provider. Test it before saving.")
        self._loading_provider = False

    def _on_provider_selected(self, _event: object = None) -> None:
        selection = self.provider_list.curselection()
        if not selection:
            return
        provider_id = self._provider_ids[selection[0]]
        self._load_provider(get_provider(self.settings, provider_id))

    def _load_provider(self, provider: ProviderConfig | None) -> None:
        if provider is None:
            self._new_provider()
            return
        self._loading_provider = True
        self._selected_provider_id = provider.provider_id
        self._tested_models = None
        self._last_tested_identity = None
        self.provider_id_var.set(provider.provider_id)
        self.provider_name_var.set(provider.name)
        self.provider_base_url_var.set(provider.base_url)
        self.provider_api_key_var.set(provider.api_key)
        self.provider_models_var.set(", ".join(provider.models))
        if provider.last_tested_at:
            self.provider_status_var.set(f"Last tested at {provider.last_tested_at}")
        else:
            self.provider_status_var.set("Saved provider loaded.")
        self._loading_provider = False

    def _form_identity(self) -> tuple[str, str, str]:
        return (
            self.provider_id_var.get().strip(),
            self.provider_base_url_var.get().strip().rstrip("/"),
            self.provider_api_key_var.get().strip(),
        )

    def _on_provider_identity_changed(self, *_args: object) -> None:
        if self._loading_provider:
            return
        if self._last_tested_identity == self._form_identity():
            return
        self._tested_models = None
        self.provider_models_var.set("")
        if self.provider_id_var.get().strip() or self.provider_base_url_var.get().strip():
            self.provider_status_var.set("Provider details changed. Run Test before saving.")

    def _build_candidate_provider(self) -> ProviderConfig:
        return ProviderConfig(
            provider_id=self.provider_id_var.get().strip(),
            name=self.provider_name_var.get().strip(),
            base_url=self.provider_base_url_var.get().strip().rstrip("/"),
            api_key=self.provider_api_key_var.get().strip(),
        )

    def _test_provider(self) -> None:
        candidate = self._build_candidate_provider()
        if not candidate.base_url or not candidate.api_key:
            messagebox.showerror("Provider error", "Base URL and API key are required before testing.")
            return

        try:
            client = OpenAICompatibleClient(
                api_url=candidate.base_url,
                api_key=candidate.api_key,
                model="provider-test",
                timeout=30.0,
                prompt_template="{{TEXT}}",
                task_config=get_task_config(),
            )
            models = client.ensure_available()
        except Exception as exc:
            self.provider_status_var.set(f"Test failed: {exc}")
            messagebox.showerror("Provider test failed", str(exc))
            return

        self._tested_models = models
        self._last_tested_identity = self._form_identity()
        self.provider_models_var.set(", ".join(models))
        self.provider_status_var.set(f"Test passed. {len(models)} models available.")

    def _save_provider(self) -> None:
        candidate = self._build_candidate_provider()
        tested_models = self._tested_models if self._last_tested_identity == self._form_identity() else None

        try:
            saved = upsert_provider(self.settings, candidate, tested_models=tested_models)
        except ProviderMutationError as exc:
            messagebox.showerror("Provider error", str(exc))
            return

        if self.settings.defaults.api.provider_id == saved.provider_id and self.settings.defaults.api.model not in saved.models:
            self.settings.defaults.api.model = saved.models[0] if saved.models else ""
        if self.settings.defaults.api.provider_id is None:
            self.settings.defaults.api.provider_id = saved.provider_id
            self.settings.defaults.api.model = saved.models[0] if saved.models else ""

        save_settings(self.settings)
        self._refresh_provider_list(saved.provider_id)
        self.default_api_provider_var.set(saved.provider_id)
        self._refresh_default_api_models()
        self.provider_status_var.set("Provider saved.")

    def _delete_provider(self) -> None:
        provider_id = self.provider_id_var.get().strip()
        if not provider_id:
            return
        if not messagebox.askyesno("Delete provider", f"Delete provider `{provider_id}`?"):
            return
        delete_provider(self.settings, provider_id)
        save_settings(self.settings)
        self._refresh_provider_list()
        self._refresh_default_api_models()
        self._new_provider()

    def _refresh_default_provider_values(self) -> None:
        provider_ids = [provider.provider_id for provider in self.settings.providers]
        self.default_api_provider_box["values"] = provider_ids
        if self.default_api_provider_var.get() not in provider_ids:
            self.default_api_provider_var.set(self.settings.defaults.api.provider_id or "")

    def _on_default_api_provider_changed(self, _event: object = None) -> None:
        self._refresh_default_api_models()

    def _refresh_default_api_models(self) -> None:
        models = get_api_provider_models(self.settings, self.default_api_provider_var.get().strip() or None)
        self.default_api_model_box["values"] = models
        if self.default_api_model_var.get() not in models:
            self.default_api_model_var.set(models[0] if models else "")

    def _parse_concurrency(self, text: str) -> int:
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError("Concurrency must be an integer.") from exc
        if value < MIN_CONCURRENCY or value > MAX_CONCURRENCY:
            raise ValueError(f"Concurrency must be between {MIN_CONCURRENCY} and {MAX_CONCURRENCY}.")
        return value

    def _save_defaults(self) -> None:
        try:
            local_concurrency = self._parse_concurrency(self.default_local_concurrency_var.get())
            api_concurrency = self._parse_concurrency(self.default_api_concurrency_var.get())
        except ValueError as exc:
            messagebox.showerror("Defaults error", str(exc))
            return

        self.settings.defaults.execution_mode = self.default_execution_mode_var.get().strip() or "local"
        self.settings.defaults.local.base_url = self.default_local_base_url_var.get().strip()
        self.settings.defaults.local.model = self.default_local_model_var.get().strip()
        self.settings.defaults.local.concurrency = local_concurrency
        provider_id = self.default_api_provider_var.get().strip() or None
        self.settings.defaults.api.provider_id = provider_id if get_provider(self.settings, provider_id) else None
        self.settings.defaults.api.model = self.default_api_model_var.get().strip()
        self.settings.defaults.api.concurrency = api_concurrency
        save_settings(self.settings)
        messagebox.showinfo("Defaults saved", "LLM defaults have been saved.")
