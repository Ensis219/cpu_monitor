import csv
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import psutil
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

try:
    import wmi
    wmi_obj = wmi.WMI(namespace="root\\wmi")
except Exception:
    wmi_obj = None


def get_cpu_temp():
    """Температура через WMI: ищем реалистичный датчик, тихо игнорируем ошибки."""
    if wmi_obj is None:
        return None
    try:
        temps = list(wmi_obj.MSAcpi_ThermalZoneTemperature())
        if not temps:
            return None
        for t in temps:
            raw = t.CurrentTemperature
            celsius = raw / 10.0 - 273.15
            # Реалистичный диапазон для CPU
            if 20 <= celsius <= 95:
                return round(celsius, 1)
        # Если не нашли — возвращаем первый (прозрачно)
        first_c = temps[0].CurrentTemperature / 10.0 - 273.15
        return round(first_c, 1)
    except Exception:
        # Тихо: в GUI будет «н/д»
        return None


class MonitorApp:
    WINDOW_POINTS = 300  # ~5 минут при шаге 1 сек

    def __init__(self, root):
        self.root = root
        self.root.title("Монитор CPU — частота, загрузка, температура")
        self.root.geometry("750x550")

        self.running = False
        self.times = []
        self.temps = []
        self.freqs = []
        self.loads = []

        # --- Панель показаний ---
        info_frame = tk.Frame(root)
        info_frame.pack(fill="x", padx=10, pady=8)

        self.temp_label = tk.Label(info_frame, text="Температура: --", font=("Arial", 14, "bold"))
        self.temp_label.pack(side="left", expand=True)
        self.freq_label = tk.Label(info_frame, text="Частота: --", font=("Arial", 14, "bold"))
        self.freq_label.pack(side="left", expand=True)
        self.load_label = tk.Label(info_frame, text="Загрузка: --", font=("Arial", 14, "bold"))
        self.load_label.pack(side="left", expand=True)

        # Подсказка про права
        hint = "(Температура может требовать прав администратора)"
        self.hint_label = tk.Label(root, text=hint, fg="gray", font=("Arial", 9))
        self.hint_label.pack(fill="x", padx=10, pady=(0, 4))

        # --- График ---
        self.fig = Figure(figsize=(6.8, 3.6), dpi=95)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Температура (°C), частота (ГГц), загрузка (%)")
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10)

        # Линии графика (создаём один раз)
        self.line_temp, = self.ax.plot([], [], color="red", label="Температура")
        self.line_freq, = self.ax.plot([], [], color="blue", label="Частота")
        self.line_load, = self.ax.plot([], [], color="green", label="Загрузка")
        self.ax.legend(loc="upper left")

        # --- Кнопки ---
        btn_frame = tk.Frame(root)
        btn_frame.pack(fill="x", padx=10, pady=8)

        self.start_btn = tk.Button(btn_frame, text="▶ Старт", width=12,
                                   command=self.start, bg="#4CAF50", fg="white")
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = tk.Button(btn_frame, text="⏹ Стоп", width=12,
                                  command=self.stop, bg="#f44336", fg="white", state=tk.DISABLED)
        self.stop_btn.pack(side="left", padx=(0, 8))

        tk.Button(btn_frame, text="🗑 Сброс", command=self.reset_data).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="💾 Экспорт CSV", command=self.export_csv).pack(side="left")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def start(self):
        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.loop, daemon=True).start()

    def stop(self):
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def reset_data(self):
        if messagebox.askyesno("Сброс данных", "Очистить историю измерений?"):
            self.times.clear()
            self.temps.clear()
            self.freqs.clear()
            self.loads.clear()
            self.redraw()

    def loop(self):
        while self.running:
            # Температура
            temp = get_cpu_temp()

            # Частота: current, если нет — max
            freq_info = psutil.cpu_freq()
            freq = freq_info.current if freq_info and freq_info.current else (freq_info.max if freq_info else None)

            # Загрузка: percpu=False, интервал 1.0 для плавности
            load = psutil.cpu_percent(interval=1.0, percpu=False)

            now = time.strftime("%H:%M:%S")
            self.times.append(now)
            self.temps.append(temp if temp is not None else None)
            self.freqs.append(freq / 1000 if freq else None)  # МГц → ГГц
            self.loads.append(load)

            # Обрезаем до окна
            if len(self.times) > self.WINDOW_POINTS:
                self.times = self.times[-self.WINDOW_POINTS:]
                self.temps = self.temps[-self.WINDOW_POINTS:]
                self.freqs = self.freqs[-self.WINDOW_POINTS:]
                self.loads = self.loads[-self.WINDOW_POINTS:]

            # Отладка в консоль (сразу видно, что берёт программа)
            print(f"[DEBUG] time={now}, temp={temp}, freq={freq} MHz, load={load}%")

            # Обновляем лейблы
            temp_text = f"{temp} °C" if temp is not None else "н/д"
            freq_text = f"{freq / 1000:.2f} ГГц" if freq else "н/д"

            self.root.after(0, lambda: self.temp_label.config(
                text=f"Температура: {temp_text}",
                fg="red" if (temp and temp > 85) else "black"))
            self.root.after(0, lambda: self.freq_label.config(text=f"Частота: {freq_text}"))
            self.root.after(0, lambda: self.load_label.config(text=f"Загрузка: {load}%"))

            self.root.after(0, self.redraw)

    def redraw(self):
        xs = list(range(len(self.temps)))

        # Обновляем линии
        self.line_temp.set_data(xs, self.temps)
        self.line_freq.set_data(xs, self.freqs)
        self.line_load.set_data(xs, self.loads)

        # Автомасштаб
        self.ax.relim()
        self.ax.autoscale_view()

        self.ax.set_xlabel("Время (последние точки)")
        self.ax.grid(True, linestyle="--", alpha=0.3)
        self.canvas.draw()

    def export_csv(self):
        if not self.times:
            messagebox.showinfo("Пусто", "Нет данных. Нажми «Старт» и подожди немного.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Время", "Температура°C", "Частота ГГц", "Загрузка %"])
                for t, temp, fr, load in zip(self.times, self.temps, self.freqs, self.loads):
                    writer.writerow([t,
                                     temp if temp is not None else "",
                                     fr if fr is not None else "",
                                     load])
            messagebox.showinfo("Успех", f"Лог сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить CSV:\n{e}")

    def on_close(self):
        self.running = False
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MonitorApp(root)
    root.mainloop()