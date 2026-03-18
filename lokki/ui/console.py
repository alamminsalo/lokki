"""Main UI console application."""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, ListItem, ListView, Static


class FlowListPanel(Vertical):
    """Left sidebar showing list of lokki flows."""

    def compose(self) -> ComposeResult:
        yield Static("— Flows —", classes="sidebar-header")
        yield ListView(id="flow-list")


class RunListPanel(Vertical):
    """Main panel showing runs for selected flow."""

    def compose(self) -> ComposeResult:
        yield Static("Runs", id="run-list-header")
        yield ListView(id="run-list")


class RunDetailPanel(Vertical):
    """Bottom panel showing run details and step visualization."""

    def compose(self) -> ComposeResult:
        yield Static("Run Details", id="run-detail-header")
        yield Static("Select a run to view details", id="run-detail-content")


class LogPopover(Vertical):
    """Popover showing logs for selected run."""

    def compose(self) -> ComposeResult:
        yield Static("Logs", id="log-header")
        yield Static("Press Shift+L to fetch logs", id="log-content")


class LokkiConsole(App[Any]):
    """Textual application for lokki UI console."""

    CSS = """
    Screen {
        layout: horizontal;
        background: black;
    }

    #sidebar {
        width: 20;
        border-right: solid white;
    }

    #main {
        width: 80;
        layout: vertical;
    }

    #run-list {
        height: 1;
        border-bottom: solid white;
    }

    #run-detail {
        height: 100%;
    }

    .sidebar-header {
        text-align: center;
        text-style: bold;
        padding: 1;
        background: white;
        color: black;
    }

    #run-list-header, #run-detail-header {
        text-style: bold;
        padding: 1;
        background: white;
        color: black;
    }

    ListView {
        height: 100%;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem:hover {
        background: white;
        color: black;
    }

    ListItem:focus {
        background: white;
        color: black;
    }

    Static {
        color: white;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("?", "toggle_help", "Help"),
    ]

    def __init__(
        self,
        flow_name: str | None = None,
        region: str = "us-east-1",
        endpoint: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.flow_name = flow_name
        self.region = region
        self.endpoint = endpoint
        self.selected_flow: str | None = flow_name
        self.selected_run: str | None = None
        self._flows: list[str] = []
        self._runs: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Container(id="sidebar"):
                yield FlowListPanel()
            with Container(id="main"):
                yield RunListPanel()
                yield RunDetailPanel()
        yield Footer()

    def on_mount(self) -> None:
        """Load flows on startup."""
        self._load_flows()

    def _load_flows(self) -> None:
        """Load list of lokki flows from DynamoDB."""
        list_view = self.query_one("#flow-list", ListView)
        list_view.clear()

        from lokki.ui.api import list_flows

        try:
            flows = list_flows(
                region=self.region,
                endpoint=self.endpoint,
            )

            flows.sort()
            self._flows = flows

            if not flows:
                list_view.append(ListItem(Static("No flows found")))
                return

            for flow_name in flows:
                list_view.append(ListItem(Static(flow_name)))

            # Auto-select first flow if provided via --flow
            if self.flow_name and self.flow_name in flows:
                idx = flows.index(self.flow_name)
                list_view.index = idx
                self.selected_flow = self.flow_name
            elif flows:
                # Auto-select first flow and load runs
                list_view.index = 0
                self.selected_flow = flows[0]
                self._load_runs()

        except Exception as e:
            list_view.append(ListItem(Static(f"Error: {e}")))

    def _is_lokki_flow(self, state_machine: dict[str, Any]) -> bool:
        """Check if state machine is a lokki flow (by tag)."""
        tags = state_machine.get("tags", {})
        if tags.get("lokki:managed") == "true":
            return True

        name = state_machine.get("name", "")
        if name.startswith("lokki-"):
            return True

        return False

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle flow or run selection."""
        list_id = event.list_view.id

        if list_id == "flow-list":
            # Use index to get flow name from stored flows
            list_view = event.list_view
            idx = list_view.index
            if idx is not None and idx < len(self._flows):
                self.selected_flow = self._flows[idx]
            self._load_runs()
        elif list_id == "run-list":
            list_view = event.list_view
            idx = list_view.index
            if idx is not None and idx < len(self._runs):
                self.selected_run = self._runs[idx]["run_id"]
            self._load_run_detail()

    def _load_runs(self) -> None:
        """Load runs for selected flow."""
        if not self.selected_flow:
            return

        list_view = self.query_one("#run-list", ListView)
        list_view.clear()

        from lokki.cli.show import show_executions

        try:
            executions = show_executions(
                flow_name=self.selected_flow,
                region=self.region,
                endpoint=self.endpoint,
                max_count=20,
            )

            if not executions:
                list_view.append(ListItem(Static("No runs found")))
                return

            executions.sort(
                key=lambda x: x.get("start_time", ""),
                reverse=True,
            )

            self._runs = executions

            for exec_info in executions:
                run_id = exec_info.get("run_id", "unknown")
                status = exec_info.get("status", "UNKNOWN")
                duration = exec_info.get("duration", "-")
                start_time = exec_info.get("start_time", "-")

                label = (
                    f"{run_id[:12]:<14} | {status:<12} | {duration:<8} | {start_time}"
                )
                list_view.append(ListItem(Static(label)))

        except Exception as e:
            list_view.append(ListItem(Static(f"Error: {e}")))

    def _load_run_detail(self) -> None:
        """Load and display run details."""
        if not self.selected_flow or not self.selected_run:
            return

        content = self.query_one("#run-detail-content", Static)
        content.update(f"Run: {self.selected_run}\n\nStep visualization coming soon...")


def run_ui(
    flow_name: str | None = None,
    region: str = "us-east-1",
    endpoint: str | None = None,
) -> int:
    """Run the UI console."""
    app = LokkiConsole(
        flow_name=flow_name,
        region=region,
        endpoint=endpoint,
    )
    app.run()
    return 0
