import reflex as rx
import asyncio
import sys,os,json
import httpx


class State(rx.State):
    text: str = ""
    updates: list[str] = []
    
    async def send_text(self):
        self.updates = ["Sending request to API..."]
        yield

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:5001/get_spans",
                    json={"question": self.text},
                    timeout=10.0
                )
            if response.status_code == 200:
                spans = response.json()
                self.updates.append("Spans received.")
                self.updates.append(json.dumps(spans, indent=2))  # Pretty print
                yield
            else:
                self.updates.append(f"Error {response.status_code}: {response.text}")
                yield
        except Exception as e:
            self.updates.append(f"Request failed: {str(e)}")
            yield
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:5001/get_candidates",
                    json={"question": self.text, "spans":spans},
                    timeout=10.0
                )
            if response.status_code == 200:
                candidates = response.json()
                self.updates.append("Candidates received.")
                self.updates.append(json.dumps(candidates, indent=2))  # Pretty print
                yield
            else:
                self.updates.append(f"Error {response.status_code}: {response.text}")
                yield
        except Exception as e:
            self.updates.append(f"Request failed: {str(e)}")
            yield
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:5001/get_final_result",
                    json={"question": self.text, "spans":spans, "entity_candidates":candidates},
                    timeout=30.0
                )
            if response.status_code == 200:
                final_results = response.json()
                self.updates.append("Final results received.")
                self.updates.append(json.dumps(final_results, indent=2))  # Pretty print
                yield
            else:
                self.updates.append(f"Error {response.status_code}: {response.text}")
                yield
        except Exception as e:
            import traceback
            self.updates.append(f"Request failed: {str(e)}")
            self.updates.append(traceback.format_exc())
            yield
        yield

def index():
    return rx.container(
        rx.heading("Real-Time Text Streamer", size="4"),
        rx.text_area(
            placeholder="When did Chris Biemann publish a paper in ACL?",
            on_change=State.set_text,
            width="100%",
            height="100px"
        ),
        rx.button("Submit", on_click=State.send_text, mt="2"),
        rx.box(
            rx.foreach(State.updates, lambda msg: rx.text(msg)),
            border="1px solid #ccc",
            padding="2",
            mt="4",
            height="200px",
            overflow_y="scroll"
        ),
        spacing="4",
        padding="4",
        max_width="600px",
        margin="auto"
    )

app = rx.App()
app.add_page(index)
