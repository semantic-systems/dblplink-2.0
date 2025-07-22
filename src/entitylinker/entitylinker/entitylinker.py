import reflex as rx
import asyncio
import json
import httpx
from typing import List
from typing import List, Dict, Any, TypedDict, Union

# --- Define TypedDicts for API Response Structures ---
# These TypedDicts are crucial for strongly typing your data,
# preventing issues like 'UntypedVarError' and making the code more readable.

# 1. Spans API Response Structure (from /get_spans)
class APISpan(TypedDict):
    """Represents a single detected span."""
    label: str
    type: str
class Candidate(TypedDict):
    """Represents a candidate entity with its score."""
    span_id: int  # Index of the span this candidate belongs to
    uri: str
    label: str
    type: str

class FinalResultAtom(TypedDict):
    """Represents a single final result with its score."""
    uri: str
    label: str
    type: str
    sentence: str
    score: float 
    span_id: int


# --- Reflex State Definition ---
class State(rx.State):
    """The app state."""
    text: str = "" # The input text from the user
    
    # State variables to store results from each API stage
    spans: List[APISpan] = []
    candidates: List[Candidate] = [] # List to hold candidates for each span
    final_results: List[FinalResultAtom] = [] # Final linked results after processing candidates
    updates: List[str] = [] # To store sequential update messages for the log display
    progress: int = 0  # Progress percentage (0-100)
    
    is_loading: bool = False # Controls the loading spinner and button state
    error_message: str = "" # Stores and displays any errors that occur

    def set_text(self, text: str):
        """
        Updates the input text state.
        This is called when the user types in the text area.
        """
        self.text = text

    async def send_text(self):
        """
        Handles the submission of text, orchestrating sequential API calls
        and updating the UI with intermediate progress.
        """
        # Reset state for a new submission
        self.error_message = ""
        self.is_loading = True
        self.spans = []
        self.candidates = []
        self.final_results = []
        self.updates = ["Starting entity linking process..."]
        yield # Update frontend immediately to show initial status

        # --- Stage 1: Get Spans ---
        try:
            self.progress = 0
            self.updates.append("Requesting detected spans from API...")
            yield # Update log
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:5002/get_spans",
                    json={"question": self.text},
                    timeout=10.0 # Set a timeout for the request
                )
            response.raise_for_status() # Raise an HTTPStatusError for 4xx/5xx responses
            self.spans = response.json() # Parse JSON response
            self.updates.append(f"Spans received ({len(self.spans)} found).")
            self.progress = 33
            yield # Update log and display spans table if ready
        except Exception as e:
            # Catch any other unexpected errors
            self.error_message = f"An unexpected error occurred during span detection: {str(e)}"
            self.updates.append(self.error_message)
            self.is_loading = False
            self.progress = 0
            yield
            return

#       --- Stage 2: Get Candidates ---
#      Only proceed if spans were successfully retrieved
        if self.spans:
            try:
                self.updates.append("Requesting candidates from API...")
                yield # Update log
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:5002/get_candidates",
                        json={"question": self.text, "spans": self.spans}, # Pass spans from previous step
                        timeout=10.0
                    )
                response.raise_for_status()
                candidates = response.json()
                self.updates.append(f"Candidates received ({len(candidates)} found).")
                flat_candidates = [
                    {"span_id":idx, "uri": uri, "label": label, "type": type_}
                    for idx,group in enumerate(candidates)
                    for uri, label, type_ in group]
                self.candidates = flat_candidates # Flatten the nested structure
                self.progress = 66
                yield # Update log and display candidates table if ready
            except Exception as e:
                self.error_message = f"An unexpected error occurred during candidate fetching: {str(e)}"
                self.updates.append(self.error_message)
                self.is_loading = False
                self.progress = 33
                yield
                return
        else:
            self.updates.append("Skipping candidate fetching: No spans were detected.")
            yield # Update log

        # --- Stage 3: Get Final Result ---
        # Only proceed if candidates were successfully retrieved
        if self.candidates:
            try:
                self.updates.append("Requesting final results from API (this may take longer)...")
                yield # Update log
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:5002/get_final_result",
                        json={
                            "question": self.text, 
                            "spans": self.spans, 
                            "entity_candidates": candidates # Pass candidates from previous step, not self.candidates
                        },
                        timeout=30.0 # Increased timeout for potentially longer final processing
                    )
                response.raise_for_status()
                final_results = response.json()
                self.final_results = [
                    FinalResultAtom(
                        uri=atom[1][0],
                        label=atom[1][1],
                        type=atom[1][2],
                        sentence=atom[1][3],  # Include the original question as the sentence
                        score=atom[0],  # Use .get() to avoid KeyError
                        span_id=idx  # Default to -1 if not present
                    ) for idx,result in enumerate(final_results['entitylinkingresults']) for atom in result['result']
                ]
                self.updates.append("Final results received.")
                self.progress = 100
                yield # Update log and display final results table if ready
            except Exception as e:
                self.error_message = f"An unexpected error occurred during final result processing: {str(e)}"
                self.updates.append(self.error_message)
                self.progress = 66
                # Keep traceback print for server-side debugging, not for frontend display usually
                # import traceback
                # self.updates.append(traceback.format_exc()) 
                yield
        else:
            self.updates.append("Skipping final results: No candidates were found.")
            yield # Update log

        # Final state update after all processes are done or an error has stopped them
        self.is_loading = False 
        self.updates.append("Process completed.")
        yield # Ensures all final state changes are pushed to the frontend

# --- UI Components ---

def about() -> rx.Component:
    return rx.container(
        rx.vstack(
            navbar(),
            rx.heading("About DBLPLink 2.0", size="7", mb="4", color="blue.800"),
            rx.text(
                "DBLPLink 2.0 is an advanced entity linker for the DBLP Knowledge Graph, "
                "designed to extract and link entities from natural language questions.",
                color="gray.700",
                mb="3",
                text_align="center"
            ),
            rx.text(
                "This application allows users to input questions and receive linked entities "
                "from the DBLP dataset, enhancing research and information retrieval.",
                color="gray.600",
                mb="3",
                text_align="center"
            ),
        ),
        padding="4",
        max_width="800px",
        margin_x="auto"
    )
def api() -> rx.Component:
    return rx.container(
        rx.vstack(
            navbar(),
            rx.heading("API Documentation", size="7", mb="4", color="blue.800"),
            rx.text(
                "DBLPLink 2.0 provides a RESTful API for entity linking tasks.",
                color="gray.700",
                mb="3",
                text_align="center"
            ),
            rx.text(
                "You can interact with the following endpoints:",
                color="gray.600",
                mb="3",
                text_align="center"
            ),
            rx.unordered_list(
                rx.list_item("POST /get_spans - Detects spans in the input text."),
                rx.list_item("POST /get_candidates - Fetches candidate entities for detected spans."),
                rx.list_item("POST /get_final_result - Reranks candidates and returns final linked results.")
            ),
        ),
        padding="4",
        max_width="800px",
        margin_x="auto"
    )
def contact() -> rx.Component:
    return rx.container(
        rx.vstack(
            navbar(),
            rx.heading("Contact Us", size="7", mb="4", color="blue.800"),
            rx.text(
                "For inquiries or support, please reach out to us at:",
                color="gray.700",
                mb="3",
                text_align="center"
            ),
            rx.text(
                "Email: debayan.banerjee AT leuphana DOT de",
                color="gray.600",
                mb="3",
                text_align="center"
            ),
            rx.text(
                "We welcome feedback and contributions to improve DBLPLink 2.0.",
                color="gray.600",
                mb="3",
                text_align="center"
            ),
        ),
        padding="4",
        max_width="800px",
        margin_x="auto"
    )   


def navbar_link(text: str, url: str) -> rx.Component:
    return rx.link(
        rx.text(text, size="4", weight="medium"), href=url
    )


def navbar() -> rx.Component:
    return rx.box(
        rx.desktop_only(
            rx.hstack(
                rx.hstack(
                    
                    rx.heading(
                        "DBLPLink 2.0", size="7", weight="bold"
                    ),
                    align_items="center",
                ),
                rx.hstack(
                    navbar_link("Home", "/"),
                    navbar_link("About", "/about"),
                    navbar_link("API", "/api"),
                    navbar_link("Contact", "/contact"),
                    justify="end",
                    spacing="5",
                ),
                justify="between",
                align_items="center",
            ),
        ),
        rx.mobile_and_tablet(
            rx.hstack(
                rx.hstack(
                    rx.image(
                        src="/logo.jpg",
                        width="2em",
                        height="auto",
                        border_radius="25%",
                    ),
                    rx.heading(
                        "Reflex", size="6", weight="bold"
                    ),
                    align_items="center",
                ),
                rx.menu.root(
                    rx.menu.trigger(
                        rx.icon("menu", size=30)
                    ),
                    rx.menu.content(
                        rx.menu.item("Home"),
                        rx.menu.item("About"),
                        rx.menu.item("API"),
                        rx.menu.item("Contact"),
                    ),
                    justify="end",
                ),
                justify="between",
                align_items="center",
            ),
        ),
        bg=rx.color("accent", 3),
        padding="1em",
        # position="fixed",
        # top="0px",
        # z_index="5",
        width="100%",
    )


def render_collapsible(title: str, content: rx.Component) -> rx.Component:
    """Renders collapsible sections that are collapsed by default."""
    return rx.accordion.root(
        rx.accordion.item(
            rx.accordion.trigger(rx.text(title, font_weight="bold", color="blue.700")),
            rx.accordion.content(content),
            value=title,
        ),
        type="single",
        collapsible=True,
        default_value="",  # Start collapsed
        width="100%",
        mb="4",
    )

def render_default_questions() -> rx.Component:
    """Provides default example questions as clickable buttons."""
    examples = [
        "Which papers did Ricardo Usbeck publish in ISWC?",
        "What papers did Chris Biemann publish?",
        "Which papers did Debayan Banerjee publish at SIGIR?",
        "When did Tilahun Taffa publish papers at WWW?",
    ]
    return rx.hstack(
        *[
            rx.button(
                q,
                size="1",
                variant="outline",
                # Accept the event as 'e', then call set_text with the question string
                on_click=lambda e, q=q: State.set_text(q),
                color_scheme="gray",
            ) for q in examples
        ],
        spacing="2",
        mb="4",
        wrap="wrap"
    )


def render_spans_table() -> rx.Component:
    """Renders a table for detected spans."""
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Label"),
                rx.table.column_header_cell("Type"),
            )
        ),
        rx.table.body(
            rx.foreach(
                State.spans,
                lambda span: rx.table.row(
                    rx.table.cell(span["label"]),
                    rx.table.cell(span["type"]),
                ),
            )
        ),
        variant="surface", # Add a variant for better styling
        width="100%",
        border="1px solid lightgray",
        margin_top="1em",
    )


def render_candidates_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Span ID"),
                rx.table.column_header_cell("Entity URI"),
                rx.table.column_header_cell("Entity Label"),
                rx.table.column_header_cell("Entity Type"),
            )
        ),
        rx.table.body(
            rx.foreach(
                State.candidates,  # Now a flat list of dicts
                lambda candidate: rx.table.row(
                    rx.table.cell(candidate["span_id"]),  # Display span ID
                    rx.table.cell(candidate["uri"]),
                    rx.table.cell(candidate["label"]),
                    rx.table.cell(candidate["type"]),
                ),
            )
        ),
        variant="surface",
        width="100%",
        border="1px solid lightgray",
        margin_top="1em",
    )



def render_final_results_table() -> rx.Component:
    """Renders a table for final linked results."""
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Span ID"),
                rx.table.column_header_cell("Label"),
                rx.table.column_header_cell("Type"),
                rx.table.column_header_cell("Score"),
                rx.table.column_header_cell("Evidence Sentence"),
                rx.table.column_header_cell("URI"),
            )
        ),
        rx.table.body(
            rx.foreach(
                State.final_results,
                lambda result: rx.table.row(
                    rx.table.cell(result.span_id),
                    rx.table.cell(result.label),
                    rx.table.cell(result.type),
                    rx.table.cell(f"{result.score:.4f}"),
                    rx.table.cell(result.sentence),
                    rx.table.cell(
                        rx.link(
                            result.uri,
                            href=result.uri,
                            is_external=True,
                            color="blue",
                            text_decoration="underline"
                        )
                    ),
                )
            )
        ),
        variant="surface",
        width="100%",
        border="1px solid lightgray",
        margin_top="1em",
    )


def index() -> rx.Component:
    return rx.container(
        rx.vstack(
            navbar(),
            rx.heading("Entity Linker for the DBLP Knowledge Graph", size="7", mb="4", color="blue.800", align_self="center"),
            rx.hstack(
                rx.vstack(
                    rx.text(
                        "Enter a natural language question to extract and link entities.",
                        color="gray.700",
                        mb="3",
                        text_align="center"
                    ),

                    render_default_questions(),

                    rx.text_area(
                        placeholder="e.g., When did Chris Biemann publish a paper in ACL?",
                        on_change=State.set_text,
                        value=State.text,
                        width="100%",
                        height="60px",  # Adjusted for one-line question
                        padding="3",
                        border_radius="10px",
                        box_shadow="sm",
                        font_size="1em",
                        _focus={"border_color": "blue.500", "box_shadow": "outline"}
                    ),
                    rx.button(
                        "Submit", 
                        on_click=State.send_text, 
                        mt="3",
                        is_loading=State.is_loading,
                        loading_text="Processing...",
                        color_scheme="blue",
                        size="2"
                    ),
                    width="50%",
                    padding="4"
                ),
                rx.vstack(
                    rx.heading("Process Log", size="4", mb="2", color="gray.700",font_weight="normal"),
                    rx.box(
                        rx.foreach(State.updates, lambda update: rx.text(update, font_size="0.9em", color="gray.600")),
                        width="100%",
                        min_height="50px",
                        padding="3",
                        border="1px solid #e0e0e0",
                        border_radius="8px",
                        bg="white",
                        overflow_y="auto",
                        max_height="200px",
                        box_shadow="sm"
                    ),

                    width="50%",
                    padding="4"
                ),
                padding="4",
                max_width="800px",
                margin_x="auto"
            ),
            rx.cond(
                State.progress > 0,
                rx.progress(
                    value=State.progress,
                    size="3",
                    color="blue",
                    mb="4",
                    show_value=True
                )
            ),
            rx.cond(
                State.error_message != "",
                rx.box(
                    rx.text(State.error_message, color="red.600", font_weight="bold"),
                    mt="4",
                    px="4",
                    py="2",
                    border="1px solid",
                    border_color="red.300",
                    border_radius="8px",
                    bg="red.50",
                    width="100%"
                )
            ),
            rx.cond(
                State.spans.length() > 0,
                rx.box(
                    render_collapsible("Detected Spans", render_spans_table()),
                    align_self="start",
                    mt="4"
                )
            ),
                rx.cond(
                State.candidates.length() > 0,
                rx.box(
                    render_collapsible("Fetched Candidates", render_candidates_table()),
                    align_self="start",
                    mt="4"
                )
            ),
            rx.cond(
                State.final_results.length() > 0,
                rx.box(
                    render_collapsible("Final Linked Results", render_final_results_table()),
                    
                    mt="4"
                )
            ),
        ),                         
    )


# --- App Initialization ---
app = rx.App(
    theme=rx.theme(
        appearance="light", # Default to light mode
        accent_color="blue", # Set accent color for interactive elements
        radius="small", # Overall border-radius for components
        scaling="95%", # Overall scaling for components
    ),
)
app.add_page(index, title="DBLPLink 2.0 Entity Linker")
app.add_page(about)
app.add_page(api)
app.add_page(contact)
