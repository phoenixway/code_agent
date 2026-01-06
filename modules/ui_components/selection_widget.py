from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import ListView, ListItem, Label
from textual.reactive import reactive
import asyncio

class SelectionWidget(Container):
    """
    Універсальний віджет вибору, що з'являється над полем вводу.
    """
    
    # Make it focusable
    can_focus = True
    
    def __init__(self, options: list[str], prompt: str = "Select an option", callback=None, **kwargs):
        super().__init__(**kwargs)
        self.options = options
        self.prompt = prompt
        self.callback = callback
        self.future = None

    def compose(self) -> ComposeResult:
        yield Label(self.prompt, id="selection-prompt")
        yield ListView(
            *[ListItem(Label(opt), id=f"opt_{i}") for i, opt in enumerate(self.options)],
            id="selection-list"
        )

    async def wait_for_selection(self) -> str | None:
        """
        Метод для асинхронного очікування вибору.
        """
        self.future = asyncio.get_running_loop().create_future()
        self.display = True
        
        # Force UI refresh and focus
        self.refresh(layout=True)
        await asyncio.sleep(0.1)  # Give more time for layout
        
        list_view = self.query_one("#selection-list", ListView)
        list_view.can_focus = True
        
        # Force focus multiple times to ensure it works
        self.focus()
        await asyncio.sleep(0.05)
        list_view.focus()
        
        self.app.log(f"SelectionWidget: ListView focused? {list_view.has_focus}")
        self.app.log(f"SelectionWidget: Widget visible? {self.display}")
        self.app.log(f"SelectionWidget: Focused widget: {self.app.focused}")
        
        try:
            return await self.future
        finally:
            self.display = False
            self.future = None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list selection"""
        if self.future and not self.future.done():
            # Отримуємо текст з Label всередині ListItem
            label = event.item.query_one(Label)
            selection = str(label.renderable)
            self.future.set_result(selection)
            event.stop()

    def on_key(self, event) -> None:
        """Handle keyboard input"""
        self.app.log(f"SelectionWidget.on_key: {event.key}")
        
        if event.key == "escape":
            if self.future and not self.future.done():
                self.future.set_result(None)
                event.stop()
                event.prevent_default()
        elif event.key == "enter":
            # Get the highlighted item and select it
            list_view = self.query_one("#selection-list", ListView)
            if list_view.highlighted_child:
                label = list_view.highlighted_child.query_one(Label)
                selection = str(label.renderable)
                if self.future and not self.future.done():
                    self.future.set_result(selection)
                    event.stop()
                    event.prevent_default()
        # Don't stop up/down to let ListView handle them
