"""Main Gradio UI application for Game Master AI.

Three-column layout:
  Column 1 — Event / Action / Reasoning stream panels (read-only)
  Column 2 — Chat interface (LLM narration + converse)
  Column 3 — State info panel (4 blocks, content varies by game phase)

Each user message triggers one engine step via `step_once`.
The runtime is kept in gr.State so each browser tab gets its own session.
"""

from __future__ import annotations

import logging
from pathlib import Path

import gradio as gr

from ui.gradio_bootstrap import GradioRuntime, bootstrap_gradio_runtime
from ui.gradio_step import StepResult, render_state_blocks, step_once


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Gradio event handlers
# ─────────────────────────────────────────────────────────────────────────────

def _init_runtime(
    data_dir: str,
    schema_dir: str | None,
    persistence_dir: str | None,
    session_id: str | None,
    seed: int,
    live_llm: bool,
    debug: bool,
):
    """Called on page load to create a fresh per-tab runtime."""
    runtime = bootstrap_gradio_runtime(
        data_dir=data_dir,
        schema_dir=schema_dir,
        persistence_dir=persistence_dir,
        session_id=session_id,
        seed=seed,
        live_llm=live_llm,
        debug=debug,
    )
    initial_chat: list[dict[str, str]] = []
    if live_llm and not runtime.live_llm:
        notice = runtime.llm_bootstrap_error or "Live LLM is unavailable; running in deterministic mode."
        initial_chat.append({"role": "assistant", "content": notice})
    b1, b2, b3, b4 = render_state_blocks(runtime.session)
    return runtime, initial_chat, "", "", "", b1, b2, b3, b4


def _append_user_message(
    user_input: str,
    chat_history: list,
):
    """Phase 1: instantly append user message and clear input."""
    text = str(user_input or "").strip()
    if not text:
        return list(chat_history or []), "", ""
    updated_history = list(chat_history or [])
    updated_history.append({"role": "user", "content": text})
    return updated_history, "", text


def _process_pending(
    pending_input: str,
    chat_history: list,
    runtime: GradioRuntime | None,
    event_stream: str,
    action_stream: str,
    reasoning_stream: str,
):
    """Phase 2: run step loop and refresh streams/panels after response arrives."""
    if runtime is None:
        return chat_history, runtime, event_stream, action_stream, reasoning_stream, "", "", "", "", ""

    text = str(pending_input or "").strip()
    if not text:
        b1, b2, b3, b4 = render_state_blocks(runtime.session)
        return chat_history, runtime, event_stream, action_stream, reasoning_stream, b1, b2, b3, b4, ""

    runtime.event_stream_text = event_stream
    runtime.action_stream_text = action_stream
    runtime.reasoning_stream_text = reasoning_stream

    result: StepResult = step_once(runtime, text, chat_history, append_user_message=False)

    return (
        result.chat_history,
        runtime,
        result.event_stream,
        result.action_stream,
        result.reasoning_stream,
        result.block_1,
        result.block_2,
        result.block_3,
        result.block_4,
        "",
    )


# ─────────────────────────────────────────────────────────────────────────────
# UI builder
# ─────────────────────────────────────────────────────────────────────────────

def launch_gradio_ui(
    data_dir: str | Path = "data",
    schema_dir: str | Path | None = None,
    persistence_dir: str | Path | None = None,
    session_id: str | None = None,
    seed: int = 5,
    live_llm: bool = False,
    debug: bool = False,
    server_name: str = "127.0.0.1",
    server_port: int = 7860,
    share: bool = False,
) -> None:

    # Capture launch params for the init closure
    _data_dir = str(data_dir)
    _schema_dir = str(schema_dir) if schema_dir else None
    _persistence_dir = str(persistence_dir) if persistence_dir else None

    # Per-tab state stored in gr.State
    # Order: runtime, chat, event_stream, action_stream, reasoning_stream

    with gr.Blocks(title="Game Master AI") as app:

        # Hidden state containers
        runtime_state = gr.State(None)
        pending_input_state = gr.State("")
        event_stream_state = gr.State("")
        action_stream_state = gr.State("")
        reasoning_stream_state = gr.State("")

        with gr.Row():

            # ── Column 1: Stream panels ───────────────────────────────────────
            with gr.Column(scale=1):

                event_stream_box = gr.Textbox(
                    label="Event Stream",
                    lines=10,
                    interactive=False,
                    autoscroll=True,
                )

                action_stream_box = gr.Textbox(
                    label="Action Stream",
                    lines=10,
                    interactive=False,
                    autoscroll=True,
                )

                reasoning_stream_box = gr.Textbox(
                    label="Reasoning Stream",
                    lines=10,
                    interactive=False,
                    autoscroll=True,
                )

            # ── Column 2: Chat ────────────────────────────────────────────────
            with gr.Column(scale=1):

                chatbot = gr.Chatbot(
                    height=560,
                    label="Game Master AI",
                )

                with gr.Row():
                    chat_input = gr.Textbox(
                        placeholder="Type your message or /command...",
                        show_label=False,
                        scale=4,
                    )
                    send_btn = gr.Button("Send", scale=1, variant="primary")

            # ── Column 3: State info panel ────────────────────────────────────
            with gr.Column(scale=1):

                block_1 = gr.Textbox(label="Game State", lines=5, interactive=False)
                block_2 = gr.Textbox(label="Party / Room", lines=5, interactive=False)
                block_3 = gr.Textbox(label="Encounters / Enemies", lines=5, interactive=False)
                block_4 = gr.Textbox(label="Actions / Info", lines=5, interactive=False)

        send_event_outputs = [
            chatbot,
            chat_input,
            pending_input_state,
        ]
        process_event_outputs = [
            chatbot,
            runtime_state,
            event_stream_box,
            action_stream_box,
            reasoning_stream_box,
            block_1,
            block_2,
            block_3,
            block_4,
            pending_input_state,
        ]

        send_click_event = send_btn.click(
            fn=_append_user_message,
            inputs=[chat_input, chatbot],
            outputs=send_event_outputs,
            show_progress="minimal",
            show_progress_on=[chatbot],
        )
        send_click_event.then(
            fn=_process_pending,
            inputs=[
                pending_input_state,
                chatbot,
                runtime_state,
                event_stream_box,
                action_stream_box,
                reasoning_stream_box,
            ],
            outputs=process_event_outputs,
            show_progress="minimal",
            show_progress_on=[chatbot],
        )

        send_submit_event = chat_input.submit(
            fn=_append_user_message,
            inputs=[chat_input, chatbot],
            outputs=send_event_outputs,
            show_progress="minimal",
            show_progress_on=[chatbot],
        )
        send_submit_event.then(
            fn=_process_pending,
            inputs=[
                pending_input_state,
                chatbot,
                runtime_state,
                event_stream_box,
                action_stream_box,
                reasoning_stream_box,
            ],
            outputs=process_event_outputs,
            show_progress="minimal",
            show_progress_on=[chatbot],
        )

        # ── Bootstrap runtime on page load ────────────────────────────────────
        app.load(
            fn=lambda: _init_runtime(
                _data_dir, _schema_dir, _persistence_dir,
                session_id, seed, live_llm, debug,
            ),
            inputs=[],
            outputs=[
                runtime_state,
                chatbot,
                event_stream_box,
                action_stream_box,
                reasoning_stream_box,
                block_1,
                block_2,
                block_3,
                block_4,
            ],
        )

    logger.info("Launching Gradio UI", extra={"host": server_name, "port": server_port})
    app.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        theme=gr.themes.Monochrome(),
    )


if __name__ == "__main__":
    launch_gradio_ui(live_llm=False, debug=True)
