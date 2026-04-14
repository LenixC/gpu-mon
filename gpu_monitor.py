import subprocess
import asyncio
from collections import deque
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static, DataTable, Sparkline
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual import work
from textual.events import Resize

FIELDS = [
    "timestamp", "name", "index", "uuid",
    "utilization.gpu", "utilization.memory",
    "memory.total", "memory.used", "memory.free",
    "temperature.gpu", "temperature.memory",
    "power.draw", "power.limit",
    "clocks.sm", "clocks.mem", "clocks.gr",
    "fan.speed", "pstate",
    "pcie.link.gen.current", "pcie.link.width.current",
    "driver_version", "vbios_version"
]

query = ",".join(FIELDS)
HISTORY = 120
WIDE_THRESHOLD = 120


def is_wsl() -> bool:
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False

IS_WSL = is_wsl()


def fetch_stats():
    result = subprocess.run(
        ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    lines = result.stdout.strip().split("\n")
    stats = []
    for line in lines:
        values = line.split(", ")
        data = dict(zip(FIELDS, values))
        stats.append(data)
    return stats


def fetch_processes_csv():
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    lines = result.stdout.strip().split("\n")
    processes = []
    for line in lines:
        if not line.strip():
            continue
        values = line.split(", ")
        if len(values) < 3:
            continue
        processes.append({
            "pid":             values[0].strip(),
            "process_name":    values[1].strip(),
            "used_gpu_memory": values[2].strip()
        })
    return processes


def fetch_processes_scrape():
    result = subprocess.run(
        ["nvidia-smi"],
        capture_output=True, text=True
    )
    processes = []
    in_processes = False
    for line in result.stdout.split("\n"):
        if "Processes:" in line:
            in_processes = True
            continue
        if not in_processes:
            continue
        if line.startswith("|=") or line.startswith("+-") or "GPU Memory" in line or "GI   CI" in line:
            continue
        if line.startswith("|") and line.strip() != "|":
            inner = line.strip().strip("|").strip()
            if not inner:
                continue
            parts = inner.split()
            if len(parts) >= 6:
                processes.append({
                    "pid":             parts[3],
                    "process_name":    parts[5],
                    "used_gpu_memory": parts[6] if len(parts) > 6 else "N/A"
                })
    return processes


def fetch_processes():
    if IS_WSL:
        return fetch_processes_scrape()
    return fetch_processes_csv()


def render_htop_bar(label: str, used: float, total: float, width: int = 40) -> str:
    percent = used / total if total > 0 else 0
    filled = int(percent * width)
    empty = width - filled

    if percent < 0.6:
        color = "green"
    elif percent < 0.8:
        color = "yellow"
    else:
        color = "red"

    filled_str = f"[{color}]{'|' * filled}[/{color}]" if filled > 0 else ""
    empty_str = '.' * empty
    used_str = f"{used / 1024:.1f}"
    total_str = f"{total / 1024:.1f}G"

    return f"{label} \[{filled_str}{empty_str}] {used_str}/{total_str}"


class SparkPanel(Vertical):
    DEFAULT_CSS = """
    SparkPanel {
        width: 1fr;
        height: auto;
        padding: 0;
    }
    SparkPanel Static {
        padding: 1 1 0 1;
        color: $text-muted;
    }
    SparkPanel Sparkline {
        height: 4;
        margin: 0 1;
        width: 100%;
    }
    """

    def __init__(self, label: str, spark_id: str, **kwargs):
        super().__init__(**kwargs)
        self._label = label
        self._spark_id = spark_id

    def compose(self) -> ComposeResult:
        yield Static(self._label)
        yield Sparkline([], summary_function=max, id=self._spark_id)


class SMIApp(App):
    CSS = """
    Static {
        padding: 0 1;
    }
    #spark_row {
        height: auto;
    }
    #gpu_sparkline > .sparkline--max-color {
        color: $success;
    }
    #gpu_sparkline > .sparkline--min-color {
        color: $success-darken-3;
    }
    #vram_sparkline > .sparkline--max-color {
        color: $warning;
    }
    #vram_sparkline > .sparkline--min-color {
        color: $warning-darken-3;
    }
    DataTable {
        margin: 1 1;
        height: 12;
    }
    """

    BINDINGS = [("d", "toggle_dark", "Toggle Dark Mode")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static("", id="vram_bar")
            yield Static("", id="gpu_bar")
            yield Static("", id="info_line")
            with Horizontal(id="spark_row"):
                yield SparkPanel("GPU Utilization", "gpu_sparkline")
                yield SparkPanel("VRAM Usage", "vram_sparkline")
            yield DataTable(id="process_table")
        yield Footer()

    def on_mount(self) -> None:
        self.vram_bar = self.query_one("#vram_bar", Static)
        self.gpu_bar = self.query_one("#gpu_bar", Static)
        self.info_line = self.query_one("#info_line", Static)
        self.gpu_sparkline = self.query_one("#gpu_sparkline", Sparkline)
        self.vram_sparkline = self.query_one("#vram_sparkline", Sparkline)

        self.gpu_history: deque[float] = deque(maxlen=HISTORY)
        self.vram_history: deque[float] = deque(maxlen=HISTORY)

        table = self.query_one("#process_table", DataTable)
        table.add_columns("PID", "Process", "VRAM (MiB)")
        table.cursor_type = "row"

        self.set_interval(1, self.get_stats)

    def on_resize(self, event: Resize) -> None:
        spark_row = self.query_one("#spark_row")
        if event.size.width >= WIDE_THRESHOLD:
            spark_row.styles.layout = "horizontal"
            self.query(SparkPanel).set_styles("width: 1fr;")
        else:
            spark_row.styles.layout = "vertical"
            self.query(SparkPanel).set_styles("width: 100%;")

    def action_toggle_dark(self) -> None:
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )

    @work
    async def get_stats(self):
        stats, processes = await asyncio.gather(
            asyncio.to_thread(fetch_stats),
            asyncio.to_thread(fetch_processes)
        )

        if stats:
            gpu = stats[0]
            used = float(gpu['memory.used'])
            total = float(gpu['memory.total'])
            gpu_util = float(gpu['utilization.gpu'])
            temp = gpu['temperature.gpu']
            power_draw = gpu['power.draw']
            power_limit = gpu['power.limit']
            name = gpu['name']

            self.gpu_history.append(gpu_util)
            self.vram_history.append(used / total * 100)

            self.vram_bar.update(render_htop_bar("Mem", used, total, width=40))
            self.gpu_bar.update(render_htop_bar("GPU", gpu_util, 100, width=40))
            self.info_line.update(
                f"[dim]{name}  |  Temp: {temp}°C  |  Power: {power_draw}/{power_limit}W[/dim]"
            )
            self.gpu_sparkline.data = list(self.gpu_history)
            self.vram_sparkline.data = list(self.vram_history)

        table = self.query_one("#process_table", DataTable)
        table.clear()
        for proc in processes:
            table.add_row(proc['pid'], proc['process_name'], proc['used_gpu_memory'])


if __name__ == '__main__':
    app = SMIApp()
    app.run()
