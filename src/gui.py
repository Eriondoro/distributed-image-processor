import sys
import os
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import *
from src.network import network
from src.image_processor import get_image_dimensions


class RedDetectorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Detector Distribuido de Objetos Vermelhos")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)

        self.image_path = None
        self.image_bytes = None
        self.preview_tk = None
        self.result_tk = None
        self.job_id = None
        self.is_processing = False
        self._gui_node = None
        self._cache = {}

        self._build_ui()
        self._update_node_info()
        self.root.after(2000, self._auto_update_node_info)

    def set_node(self, node):
        self._gui_node = node

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ── Top bar: nodes + leader ──
        top_frame = ttk.LabelFrame(main_frame, text="Estado do Sistema", padding=5)
        top_frame.pack(fill=tk.X, pady=(0, 5))

        self.nodes_label = ttk.Label(top_frame, text="Nos ativos: --")
        self.nodes_label.pack(side=tk.LEFT, padx=10)

        self.leader_label = ttk.Label(top_frame, text="Lider: --")
        self.leader_label.pack(side=tk.LEFT, padx=10)

        self.self_label = ttk.Label(top_frame, text=f"Eu: {NODE_ID}")
        self.self_label.pack(side=tk.LEFT, padx=10)

        # ── Left panel ──
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        img_frame = ttk.LabelFrame(left_frame, text="Imagem Original / Resultado", padding=5)
        img_frame.pack(fill=tk.BOTH, expand=True)

        self.image_canvas = tk.Canvas(img_frame, bg="#f0f0f0", highlightthickness=0)
        self.image_canvas.pack(fill=tk.BOTH, expand=True)

        # ── Right panel ──
        right_frame = ttk.Frame(main_frame, width=350)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        right_frame.pack_propagate(False)

        # Image selector
        sel_frame = ttk.LabelFrame(right_frame, text="Selecao de Imagem", padding=5)
        sel_frame.pack(fill=tk.X, pady=(0, 5))

        self.path_label = ttk.Label(sel_frame, text="Nenhuma imagem selecionada", wraplength=320)
        self.path_label.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(sel_frame, text="Selecionar Imagem...", command=self._select_image).pack(fill=tk.X)

        # Config
        cfg_frame = ttk.LabelFrame(right_frame, text="Configuracao", padding=5)
        cfg_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(cfg_frame, text="Modo de Particionamento:").pack(anchor=tk.W)

        self.mode_var = tk.StringVar(value="1d_horizontal")
        mode_names = {
            "1d_horizontal": "1D - Horizontal",
            "1d_vertical": "1D - Vertical",
            "2d_grid": "2D - Grade (apenas N par)",
        }
        self.mode_combo = ttk.Combobox(
            cfg_frame,
            textvariable=self.mode_var,
            values=list(mode_names.keys()),
            state="readonly",
        )
        self.mode_combo.pack(fill=tk.X, pady=(2, 5))

        mode_text_frame = ttk.Frame(cfg_frame)
        mode_text_frame.pack(fill=tk.X)
        ttk.Label(
            mode_text_frame,
            textvariable=tk.StringVar(value=""),
        )

        def on_mode_change(*args):
            mode_text_frame.children["!label"].configure(
                text=mode_names.get(self.mode_var.get(), "")
            )

        self.mode_var.trace_add("write", on_mode_change)
        on_mode_change()

        ttk.Label(cfg_frame, text="Multiplicador (N partes x ?):").pack(anchor=tk.W, pady=(8, 0))
        mult_frame = ttk.Frame(cfg_frame)
        mult_frame.pack(fill=tk.X, pady=(2, 5))
        self.multiplier_var = tk.IntVar(value=1)
        ttk.Spinbox(mult_frame, from_=1, to=100, textvariable=self.multiplier_var, width=5).pack(side=tk.LEFT, padx=5)
        ttk.Label(mult_frame, text="x").pack(side=tk.LEFT)

        # Process button
        self.process_btn = ttk.Button(cfg_frame, text="Processar Imagem", command=self._start_processing, state=tk.DISABLED)
        self.process_btn.pack(fill=tk.X, pady=(10, 0))

        # Progress
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(cfg_frame, variable=self.progress_var, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))

        self.status_label = ttk.Label(cfg_frame, text="")
        self.status_label.pack(anchor=tk.W, pady=(2, 0))

        # Stats
        stats_frame = ttk.LabelFrame(right_frame, text="Estatisticas", padding=5)
        stats_frame.pack(fill=tk.X, pady=(0, 5))

        self.stats_text = tk.Text(stats_frame, height=8, width=40, state=tk.DISABLED, font=("Consolas", 9))
        self.stats_text.pack(fill=tk.X)

        # Log
        log_frame = ttk.LabelFrame(right_frame, text="Log", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=10, width=40, state=tk.DISABLED, font=("Consolas", 8))
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        # Bottom buttons
        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_frame, text="Gerar Graficos", command=self._generate_graphs).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Limpar Log", command=self._clear_log).pack(side=tk.LEFT, padx=2)

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _update_node_info(self):
        try:
            active = network.get_active_nodes()
            leader = network.get_leader_id()
            count = len(active)
            self.nodes_label.configure(text=f"Nos ativos: {count} ({', '.join(active.keys())})")
            self.leader_label.configure(text=f"Lider: {leader or '--'}")
            self.self_label.configure(text=f"Eu: {NODE_ID}")
        except Exception:
            self.nodes_label.configure(text="Nos ativos: erro de conexao")
            self.leader_label.configure(text="Lider: --")

    def _auto_update_node_info(self):
        if not self.is_processing:
            self._update_node_info()
        self.root.after(3000, self._auto_update_node_info)

    def _select_image(self):
        path = filedialog.askopenfilename(
            title="Selecionar imagem",
            filetypes=[
                ("Imagens", "*.png *.jpg *.jpeg *.bmp *.tiff"),
                ("Todos", "*.*"),
            ],
        )
        if not path:
            return

        try:
            with open(path, "rb") as f:
                self.image_bytes = f.read()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao ler imagem: {e}")
            return

        self.image_path = path
        self.path_label.configure(text=os.path.basename(path))
        self.process_btn.configure(state=tk.NORMAL)

        w, h = get_image_dimensions(self.image_bytes)
        self._log(f"Imagem carregada: {os.path.basename(path)} ({w}x{h})")

        self._show_preview()

    def _show_preview(self):
        if not self.image_bytes:
            return
        self._display_image_on_canvas(self.image_bytes, "preview")

    def _display_image_on_canvas(self, image_bytes, tag):
        canvas = self.image_canvas
        canvas.delete("all")

        try:
            pil_img = Image.open(io.BytesIO(image_bytes))
        except Exception:
            return

        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 50:
            cw = 500
        if ch < 50:
            ch = 400

        iw, ih = pil_img.size
        ratio = min((cw - 20) / iw, (ch - 20) / ih, 1.0)
        new_w, new_h = int(iw * ratio), int(ih * ratio)
        pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        tk_img = ImageTk.PhotoImage(pil_img)
        if tag == "preview":
            self.preview_tk = tk_img
        else:
            self.result_tk = tk_img

        canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=tk_img)
        canvas.configure(scrollregion=(0, 0, new_w, new_h))

    def _start_processing(self):
        if not self.image_bytes:
            return

        active = network.get_active_nodes()
        if not active:
            messagebox.showwarning("Sem nos", "Nenhum no ativo detectado. Certifique-se que ha workers rodando.")
            return

        mode = self.mode_var.get()
        multiplier = self.multiplier_var.get()
        worker_nodes = {k: v for k, v in active.items() if k != NODE_ID}
        n_nodes = len(worker_nodes) if worker_nodes else 1
        total_parts = n_nodes * multiplier

        config = {
            "mode": mode,
            "n_parts": n_nodes,
            "multiplier": multiplier,
            "image_name": os.path.basename(self.image_path) if self.image_path else "unknown",
        }

        try:
            self.job_id = network.submit_job(self.image_bytes, config)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao submeter job: {e}")
            return

        self.is_processing = True
        self.process_btn.configure(state=tk.DISABLED)
        self.progress_var.set(0)
        self.status_label.configure(text="Processando...")
        self.stats_text.configure(state=tk.NORMAL)
        self.stats_text.delete("1.0", tk.END)
        self.stats_text.configure(state=tk.DISABLED)

        self._log(f"Job submetido: {self.job_id}")
        self._log(f"Modo: {mode}, Nos: {n_nodes}, Multiplicador: {multiplier}x, Tarefas: {total_parts}")

        self.root.after(500, self._poll_job_status)

    def _poll_job_status(self):
        if not self.job_id:
            self.is_processing = False
            return

        try:
            status = network.get_job_status(self.job_id)
        except Exception:
            self.root.after(500, self._poll_job_status)
            return

        if status == "completed":
            self._on_job_complete()
        elif status == "pending" or status == "processing":
            total = network.get_job_total_tasks(self.job_id)
            completed = network.get_job_result_count(self.job_id)
            if total > 0:
                pct = min(completed / total * 100, 99)
                self.progress_var.set(pct)
                self.status_label.configure(text=f"Processando... {completed}/{total} tarefas")
            self.root.after(500, self._poll_job_status)
        else:
            self._log(f"Job falhou ou status desconhecido: {status}")
            self.is_processing = False
            self.process_btn.configure(state=tk.NORMAL)

    def _on_job_complete(self):
        self.progress_var.set(100)
        self.status_label.configure(text="Concluido!")
        self.is_processing = False
        self.process_btn.configure(state=tk.NORMAL)

        result_bytes = network.get_job_result_image(self.job_id)
        metrics = network.get_all_metrics()
        job_metric = None
        for m in reversed(metrics):
            if m.get("job_id") == self.job_id:
                job_metric = m
                break

        if result_bytes:
            self._display_image_on_canvas(result_bytes, "result")
            self._log(f"Imagem processada recebida com marcacoes")

        if job_metric:
            self._show_stats(job_metric)
            from src.metrics import save_metrics
            save_metrics(job_metric)
        else:
            self._log("Metricas nao encontradas para este job")

    def _show_stats(self, m):
        text = (
            f"Job: {m.get('job_id', '--')}\n"
            f"Imagem: {m.get('image_size', '--')}\n"
            f"Modo: {m.get('mode', '--')}\n"
            f"Partes base: {m.get('n_parts', '--')}\n"
            f"Multiplicador: {m.get('multiplier', '--')}x\n"
            f"Total tarefas: {m.get('total_tasks', '--')}\n"
            f"Tempo total: {m.get('total_time', '--')}s\n"
            f"Tempo proc. acum: {m.get('total_proc_time', '--')}s\n"
            f"Objetos detectados: {m.get('objects_detected', '--')}\n"
            f"Workers usados: {m.get('worker_names', [])}\n"
            f"Tarefas por worker: {m.get('worker_task_counts', {})}\n"
        )
        self.stats_text.configure(state=tk.NORMAL)
        self.stats_text.delete("1.0", tk.END)
        self.stats_text.insert(tk.END, text)
        self.stats_text.configure(state=tk.DISABLED)

        self._log(f"Tempo total: {m.get('total_time', '--')}s | Objetos: {m.get('objects_detected', '--')}")

    def _generate_graphs(self):
        from src.metrics import generate_summary_table
        path = generate_summary_table()
        if path:
            self._log(f"Graficos salvos em: {path}")
            try:
                os.startfile(path)
            except Exception:
                self._log("Abra o arquivo manualmente para ver os graficos.")
        else:
            messagebox.showinfo("Sem dados", "Nenhuma metrica disponivel. Execute alguns jobs primeiro.")


def run_gui(node=None):
    root = tk.Tk()
    app = RedDetectorGUI(root)
    if node:
        app.set_node(node)
    root.mainloop()
