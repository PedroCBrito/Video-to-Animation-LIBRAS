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

from src.application import IngestionCancelled, IngestionRun, run_ingestion
from src.ingestion.contracts import InputPaths, SUPPORTED_EXTENSIONS, validate_paths


STAGE_LABELS = {
    "inventory": "Inventário",
    "inspect": "Inspeção dos vídeos",
    "prepare": "Preparação dos vídeos",
    "session": "Organização das sessões",
    "verify": "Verificação final",
}


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
    return f"{stage}: {event.get('message', '')}{suffix}{current_suffix}"


class IngestionApp:
    """Tkinter application that runs one verification workflow at a time."""

    def __init__(self, root: tk.Tk | None = None):
        self.root = root or tk.Tk()
        self.root.title("Video-to-Animation LIBRAS")
        self.root.minsize(700, 470)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str((Path.cwd() / "output").resolve()))
        self.status_var = tk.StringVar(value="Escolha um vídeo ou uma pasta para começar.")
        self.detail_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0)
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._build()
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

        input_frame = ttk.LabelFrame(container, text="1. Entrada", padding=14)
        input_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
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
        output_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=14)
        output_frame.columnconfigure(1, weight=1)
        ttk.Label(output_frame, text="Pasta de saída:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_var)
        self.output_entry.grid(row=0, column=1, sticky="ew")
        self.output_button = ttk.Button(output_frame, text="Selecionar pasta", command=self._choose_output)
        self.output_button.grid(row=0, column=2, padx=(8, 0))

        progress_frame = ttk.LabelFrame(container, text="3. Progresso", padding=14)
        progress_frame.grid(row=4, column=0, columnspan=3, sticky="ew")
        progress_frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.status_var).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(progress_frame, textvariable=self.detail_var, foreground="#555555").grid(
            row=2, column=0, sticky="w", pady=(4, 0)
        )

        controls = ttk.Frame(container)
        controls.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(18, 0))
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
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(18, 0))

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
        try:
            paths = validate_selection(self.source_var.get(), self.output_var.get())
        except (OSError, ValueError) as error:
            messagebox.showerror("Entrada inválida", str(error), parent=self.root)
            return

        self._set_running(True)
        self.progress_var.set(0)
        self.status_var.set("Iniciando processamento...")
        self.detail_var.set("A janela continuará disponível enquanto o lote é processado.")
        self._cancel_event = threading.Event()
        self._worker = threading.Thread(
            target=self._run_worker,
            args=(paths.source, paths.output, self._cancel_event),
            name="ingestion-worker",
            daemon=True,
        )
        self._worker.start()

    def _run_worker(self, source: Path, output: Path, cancel_event: threading.Event) -> None:
        try:
            result = run_ingestion(
                source, output, "verify",
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
                    if payload.get("report_path"):
                        self.detail_var.set(f"Relatório: {payload['report_path']}")
                elif kind == "success":
                    self._finish(payload)
                elif kind == "cancelled":
                    self._set_running(False)
                    self.status_var.set("Processamento cancelado.")
                    self.detail_var.set("Os artefatos concluídos permanecem disponíveis para uma nova tentativa.")
                elif kind == "error":
                    self._set_running(False)
                    self.status_var.set("Não foi possível concluir o processamento.")
                    self.detail_var.set(str(payload))
                    messagebox.showerror("Erro no processamento", str(payload), parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _finish(self, result: IngestionRun) -> None:
        self._set_running(False)
        self.progress_var.set(100)
        if result.exit_code == 0:
            self.status_var.set("Processamento concluído com sucesso.")
        else:
            self.status_var.set("Processamento concluído com pendências para revisão.")
        self.detail_var.set(f"Relatório salvo em: {result.report_path}")
        self.open_button.configure(state="normal")

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
