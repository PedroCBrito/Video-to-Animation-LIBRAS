"""Small Tkinter frontend for the ingestion workflow.

The window deliberately exposes only the choices needed by a first-time user:
an input video or folder, an output folder and the processing controls. The
worker calls the same application service as the CLI and communicates with Tk
through a queue, keeping the interface responsive during media operations.
"""

from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any
import webbrowser

from src.application import IngestionCancelled, IngestionRun, run_ingestion
from src.ingestion.contracts import InputPaths, SUPPORTED_EXTENSIONS, validate_paths
from src.ui.dependencies import DependencyStatus, check_dependencies, missing_dependencies


STAGE_LABELS = {
    "inventory": "Inventário",
    "inspect": "Inspeção dos vídeos",
    "prepare": "Preparação dos vídeos",
    "session": "Organização das sessões",
    "verify": "Verificação final",
    "extract": "Extração e esqueleto de origem",
}
STAGE_ORDER = tuple(STAGE_LABELS)


def validate_selection(source_text: str, output_text: str) -> InputPaths:
    """Validate the two paths entered in the UI before starting a worker."""
    source_text = source_text.strip()
    output_text = output_text.strip()
    if not source_text:
        raise ValueError("Selecione um vídeo ou uma pasta de vídeos.")
    if not output_text:
        raise ValueError("Selecione a pasta onde os resultados serão salvos.")
    source = Path(source_text).expanduser()
    output = Path(output_text).expanduser()
    return validate_paths(source, output, directory=source.is_dir())


def progress_text(event: dict[str, Any]) -> str:
    """Translate a service progress event into a short user-facing message."""
    stage = STAGE_LABELS.get(event.get("stage", ""), "Processamento")
    entries = event.get("entries")
    suffix = f" ({entries} vídeo(s))" if entries is not None else ""
    current = event.get("current_entry")
    current_suffix = f" Vídeo atual: {current}." if current else ""
    entry_status = event.get("entry_status")
    entry_suffix = f" Resultado: {entry_status}." if entry_status else ""
    reason = event.get("entry_reason")
    reason_suffix = f" Motivo: {reason}." if reason else ""
    return f"{stage}: {event.get('message', '')}{suffix}{current_suffix}{entry_suffix}{reason_suffix}"


class IngestionApp:
    """Tkinter application that runs one verification workflow at a time."""

    def __init__(self, root: tk.Tk | None = None):
        self.root = root or tk.Tk()
        self.root.title("Video-to-Animation LIBRAS")
        self.root.minsize(700, 760)
        self.root.geometry("780x820")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str((Path.cwd() / "output").resolve()))
        self.status_var = tk.StringVar(value="Escolha um vídeo ou uma pasta para começar.")
        self.detail_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0)
        self._dependency_statuses: tuple[DependencyStatus, ...] = ()
        self._dependency_overrides: dict[str, str] = {}
        self._dependency_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
        self._dependency_buttons: list[ttk.Button] = []
        self._stage_vars: dict[str, tk.StringVar] = {}
        self._active_stage: str | None = None
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._build()
        self._refresh_dependencies()
        self.root.after(100, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        container = ttk.Frame(self.root, padding=24)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(1, weight=1)

        title = ttk.Label(container, text="Preparar vídeo para animação", font=("Segoe UI", 18, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w")
        description = ttk.Label(
            container,
            text=("Selecione um vídeo ou uma pasta. O aplicativo prepara e verifica os arquivos "
                   "automaticamente usando as configurações recomendadas."),
            wraplength=620,
        )
        description.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 22))

        dependency_frame = ttk.LabelFrame(container, text="Antes de iniciar: dependências", padding=12)
        dependency_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        dependency_frame.columnconfigure(1, weight=1)
        dependency_frame.columnconfigure(2, weight=1)
        ttk.Label(
            dependency_frame,
            text="Instale os itens marcados antes de processar. O botão abre a página oficial de download.",
            foreground="#555555",
            wraplength=620,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        for row, definition in enumerate((
            {"key": "ffmpeg", "label": "FFmpeg"},
            {"key": "ffprobe", "label": "FFprobe"},
            {"key": "freemocap", "label": "FreeMoCap (pacote Python)"},
            {"key": "blender", "label": "Blender"},
        ), start=1):
            key = definition["key"]
            status_var = tk.StringVar(value="Verificando...")
            detail_var = tk.StringVar(value="")
            self._dependency_vars[key] = (status_var, detail_var)
            ttk.Label(dependency_frame, text=f"{definition['label']}:").grid(row=row, column=0, sticky="w")
            ttk.Label(dependency_frame, textvariable=status_var).grid(row=row, column=1, sticky="w", padx=(10, 8))
            ttk.Label(dependency_frame, textvariable=detail_var, foreground="#555555").grid(
                row=row, column=2, sticky="w", padx=(0, 8)
            )
            button = ttk.Button(
                dependency_frame, text="Baixar", command=lambda dependency_key=key: self._download_dependency(dependency_key)
            )
            button.grid(row=row, column=3, sticky="e")
            self._dependency_buttons.append(button)
            if key == "blender":
                locate_button = ttk.Button(dependency_frame, text="Localizar", command=self._locate_blender)
                locate_button.grid(row=row, column=4, sticky="e", padx=(6, 0))
                self._dependency_buttons.append(locate_button)
        self.refresh_dependencies_button = ttk.Button(
            dependency_frame, text="Atualizar verificações", command=self._refresh_dependencies
        )
        self.refresh_dependencies_button.grid(row=5, column=3, sticky="e", pady=(8, 0))

        input_frame = ttk.LabelFrame(container, text="1. Entrada", padding=14)
        input_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        input_frame.columnconfigure(1, weight=1)
        ttk.Label(input_frame, text="Vídeo ou pasta:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.source_entry = ttk.Entry(input_frame, textvariable=self.source_var)
        self.source_entry.grid(row=0, column=1, sticky="ew")
        self.video_button = ttk.Button(input_frame, text="Selecionar vídeo", command=self._choose_video)
        self.video_button.grid(row=0, column=2, padx=(8, 0))
        self.folder_button = ttk.Button(input_frame, text="Selecionar pasta", command=self._choose_folder)
        self.folder_button.grid(row=1, column=2, padx=(8, 0), pady=(8, 0))
        ttk.Label(
            input_frame,
            text="Uma pasta é percorrida automaticamente, incluindo subpastas.",
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        output_frame = ttk.LabelFrame(container, text="2. Onde salvar", padding=14)
        output_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=14)
        output_frame.columnconfigure(1, weight=1)
        ttk.Label(output_frame, text="Pasta de saída:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_var)
        self.output_entry.grid(row=0, column=1, sticky="ew")
        self.output_button = ttk.Button(output_frame, text="Selecionar pasta", command=self._choose_output)
        self.output_button.grid(row=0, column=2, padx=(8, 0))

        progress_frame = ttk.LabelFrame(container, text="3. Progresso", padding=14)
        progress_frame.grid(row=5, column=0, columnspan=3, sticky="ew")
        progress_frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.status_var).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(progress_frame, textvariable=self.detail_var, foreground="#555555").grid(
            row=2, column=0, sticky="w", pady=(4, 0)
        )
        stage_frame = ttk.LabelFrame(progress_frame, text="Etapas", padding=8)
        stage_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        stage_frame.columnconfigure(1, weight=1)
        for row, (stage, label) in enumerate(STAGE_LABELS.items()):
            ttk.Label(stage_frame, text=f"{label}:").grid(row=row, column=0, sticky="w")
            self._stage_vars[stage] = tk.StringVar(value="Aguardando")
            ttk.Label(stage_frame, textvariable=self._stage_vars[stage]).grid(row=row, column=1, sticky="w", padx=(8, 0))

        controls = ttk.Frame(container)
        controls.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        controls.columnconfigure(0, weight=1)
        self.start_button = ttk.Button(controls, text="Iniciar processamento", command=self._start)
        self.start_button.grid(row=0, column=1, padx=(8, 0))
        self.cancel_button = ttk.Button(controls, text="Cancelar", command=self._cancel, state="disabled")
        self.cancel_button.grid(row=0, column=2, padx=(8, 0))
        self.open_button = ttk.Button(controls, text="Abrir pasta de saída", command=self._open_output, state="disabled")
        self.open_button.grid(row=0, column=3, padx=(8, 0))

        ttk.Label(
            container,
            text=("Modo simples: prepara e verifica os arquivos. A geração da animação 3D "
                   "será habilitada nos próximos checkpoints."),
            foreground="#555555",
            wraplength=620,
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(18, 0))

    def _refresh_dependencies(self) -> None:
        environment = dict(os.environ)
        environment.update(self._dependency_overrides)
        self._dependency_statuses = check_dependencies(environment=environment)
        statuses = {status.key: status for status in self._dependency_statuses}
        for key, (status_var, detail_var) in self._dependency_vars.items():
            status = statuses[key]
            status_var.set("OK" if status.available else "FALTA")
            detail_var.set(status.detail)
        ready = not missing_dependencies(self._dependency_statuses)
        if self._worker is None or not self._worker.is_alive():
            self.start_button.configure(state="normal" if ready else "disabled")
        if ready:
            self.status_var.set("Dependências prontas. Escolha a entrada e a pasta de saída.")
            self.detail_var.set("")
        else:
            missing = ", ".join(status.label for status in missing_dependencies(self._dependency_statuses))
            self.status_var.set("Dependências pendentes: o processamento está bloqueado.")
            self.detail_var.set(f"Instale ou configure: {missing}.")

    def _download_dependency(self, key: str) -> None:
        status = next((item for item in self._dependency_statuses if item.key == key), None)
        if status is None:
            return
        try:
            webbrowser.open(status.download_url, new=2)
        except OSError as error:
            messagebox.showerror("Não foi possível abrir o download", str(error), parent=self.root)

    def _locate_blender(self) -> None:
        path = filedialog.askopenfilename(
            title="Localize o executável do Blender",
            filetypes=[("Blender", "blender.exe"), ("Executáveis", "*.exe"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self._dependency_overrides["BLENDER_BIN"] = str(Path(path).resolve())
            self._refresh_dependencies()

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecione um vídeo",
            filetypes=[("Vídeos", " ".join(f"*{extension}" for extension in sorted(SUPPORTED_EXTENSIONS))),
                       ("Todos os arquivos", "*.*")],
        )
        if path:
            self.source_var.set(path)

    def _choose_folder(self) -> None:
        path = filedialog.askdirectory(title="Selecione uma pasta de vídeos")
        if path:
            self.source_var.set(path)

    def _choose_output(self) -> None:
        path = filedialog.askdirectory(title="Selecione a pasta de saída", mustexist=False)
        if path:
            self.output_var.set(path)

    def _start(self) -> None:
        self._refresh_dependencies()
        missing = missing_dependencies(self._dependency_statuses)
        if missing:
            messagebox.showwarning(
                "Dependências obrigatórias",
                "Instale as dependências pendentes antes de iniciar:\n\n" +
                "\n".join(f"• {status.label}: {status.detail}" for status in missing),
                parent=self.root,
            )
            return
        try:
            paths = validate_selection(self.source_var.get(), self.output_var.get())
        except (OSError, ValueError) as error:
            messagebox.showerror("Entrada inválida", str(error), parent=self.root)
            return

        self._set_running(True)
        self._reset_stage_statuses()
        self.progress_var.set(0)
        self.status_var.set("Iniciando processamento...")
        self.detail_var.set("A janela continuará disponível enquanto o lote é processado.")
        self._cancel_event = threading.Event()
        self._worker = threading.Thread(
            target=self._run_worker,
            args=(paths.source, paths.output, self._cancel_event, self._tool_paths()),
            name="ingestion-worker",
            daemon=True,
        )
        self._worker.start()

    def _tool_paths(self) -> dict[str, str]:
        return {
            status.key: status.location
            for status in self._dependency_statuses
            if status.location is not None
        }

    def _run_worker(
        self, source: Path, output: Path, cancel_event: threading.Event, tool_paths: dict[str, str]
    ) -> None:
        try:
            result = run_ingestion(
                source, output, "verify",
                ffprobe=tool_paths["ffprobe"], ffmpeg=tool_paths["ffmpeg"],
                progress_callback=lambda event: self._events.put(("progress", event)),
                cancel_event=cancel_event,
            )
            self._events.put(("success", result))
        except IngestionCancelled as error:
            self._events.put(("cancelled", error))
        except Exception as error:  # Surface failures on the UI thread.
            self._events.put(("error", error))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "progress":
                    self.progress_var.set(payload["progress_percent"])
                    self.status_var.set(progress_text(payload))
                    self._update_stage_status(payload)
                    if payload.get("report_path"):
                        self.detail_var.set(f"Relatório: {payload['report_path']}")
                elif kind == "success":
                    self._finish(payload)
                elif kind == "cancelled":
                    self._set_running(False)
                    if self._active_stage:
                        self._stage_vars[self._active_stage].set("Cancelada")
                    self.status_var.set("Processamento cancelado.")
                    self.detail_var.set("Os artefatos concluídos permanecem disponíveis para uma nova tentativa.")
                elif kind == "error":
                    self._set_running(False)
                    if self._active_stage:
                        self._stage_vars[self._active_stage].set(f"Falhou: {payload}")
                    self.status_var.set("Não foi possível concluir o processamento.")
                    self.detail_var.set(str(payload))
                    messagebox.showerror("Erro no processamento", str(payload), parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _finish(self, result: IngestionRun) -> None:
        self._set_running(False)
        self.progress_var.set(100)
        self._apply_report_statuses(result.report)
        if result.exit_code == 0:
            self.status_var.set("Processamento concluído com sucesso.")
        else:
            self.status_var.set("Processamento concluído com pendências para revisão.")
        details = self._report_issue_details(result.report)
        self.detail_var.set(f"Relatório salvo em: {result.report_path}" + (f" | {details}" if details else ""))
        self.open_button.configure(state="normal")

    def _reset_stage_statuses(self) -> None:
        self._active_stage = None
        for variable in self._stage_vars.values():
            variable.set("Aguardando")

    def _update_stage_status(self, event: dict[str, Any]) -> None:
        stage = event.get("stage")
        if stage not in self._stage_vars:
            return
        self._active_stage = stage
        status = event.get("stage_status")
        if status == "completed":
            self._stage_vars[stage].set("Concluída")
        elif status == "running":
            self._stage_vars[stage].set("Em andamento")

    def _apply_report_statuses(self, report: dict[str, Any]) -> None:
        summaries = {
            "inventory": report.get("summary", {}).get("by_status", {}),
            "prepare": report.get("preparation_summary", {}),
            "session": report.get("session_summary", {}),
            "verify": report.get("verification_summary", {}),
            "extract": report.get("extraction_summary", {}),
        }
        bad_statuses = {
            "inventory": {"invalid", "unsupported", "review"},
            "prepare": {"failed", "not_run"},
            "session": {"failed", "not_run"},
            "verify": {"fail", "review", "not_run"},
            "extract": {"failed", "cancelled", "review", "not_run"},
        }
        for stage, summary in summaries.items():
            if not summary:
                continue
            issues = sum(count for name, count in summary.items() if name in bad_statuses[stage])
            self._stage_vars[stage].set("Concluída" if not issues else f"Concluída com {issues} pendência(s)")

    @staticmethod
    def _report_issue_details(report: dict[str, Any]) -> str:
        issues: list[str] = []
        for entry in report.get("entries", []):
            name = entry.get("relative_path") or entry.get("source_path") or "entrada desconhecida"
            if entry.get("status") not in {None, "valid", "ready"}:
                issues.append(f"{name}: inventário={entry.get('status')} ({entry.get('reason') or 'revisar relatório'})")
            for stage in ("preparation", "session", "verification", "extraction"):
                result = entry.get(stage, {})
                if result.get("status") in {"failed", "not_run", "fail", "review"}:
                    issues.append(f"{name}: {stage}={result['status']} ({result.get('reason') or 'revisar relatório'})")
        if not issues:
            return ""
        suffix = " ..." if len(issues) > 3 else ""
        return "Falhas/pendências: " + "; ".join(issues[:3]) + suffix

    def _cancel(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status_var.set("Cancelamento solicitado; finalizando a operação atual...")

    def _set_running(self, running: bool) -> None:
        entry_state = "disabled" if running else "normal"
        button_state = "disabled" if running else "normal"
        self.source_entry.configure(state=entry_state)
        self.output_entry.configure(state=entry_state)
        self.video_button.configure(state=button_state)
        self.folder_button.configure(state=button_state)
        self.output_button.configure(state=button_state)
        self.start_button.configure(state=button_state)
        self.cancel_button.configure(state="normal" if running else "disabled")
        for button in self._dependency_buttons:
            button.configure(state="disabled" if running else "normal")
        self.refresh_dependencies_button.configure(state="disabled" if running else "normal")
        if not running:
            self.start_button.configure(
                state="normal" if not missing_dependencies(self._dependency_statuses) else "disabled"
            )

    def _open_output(self) -> None:
        output = Path(self.output_var.get()).expanduser().resolve()
        if not output.exists():
            messagebox.showinfo("Pasta de saída", "A pasta de saída ainda não existe.", parent=self.root)
            return
        if os.name == "nt":
            os.startfile(str(output))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(output)])

    def _close(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            messagebox.showinfo(
                "Processamento em andamento",
                "Aguarde a conclusão ou clique em Cancelar antes de fechar a janela.",
                parent=self.root,
            )
            return
        self.root.destroy()

    def run(self) -> None:
        """Start Tkinter's event loop."""
        self.root.mainloop()


def main() -> None:
    """Launch the graphical frontend."""
    IngestionApp().run()
