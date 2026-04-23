# GA4GH RegBot Chatbot UX Redesign Implementation Plan

Date: 2026-04-23
Project: GA4GH RegBot
Depends on: `docs/superpowers/specs/2026-04-23-chatbot-ux-redesign-design.md`
Status: Ready for implementation

## Goal

Implement the approved chatbot UX redesign so the app feels like a real chat product first, while preserving the current GA4GH retrieval, validation, and source-preview capabilities already in the codebase.

## Delivery Strategy

Ship this in small, testable slices centered on `ui/app.py`, with only minimal backend changes where the UI contract requires better response gating. The safest path is:

1. stabilize response-state semantics
2. refactor the UI into smaller render units
3. introduce the new chat-native layout and composer behavior
4. add the dynamic context rail
5. tighten evidence/review rendering and empty/loading/error states

This order reduces the risk of breaking source preview and conversation rendering while the layout is moving.

## Workstreams

### 1. Response Gating And UI Contract

Objective:
Make the UI able to distinguish plain replies, grounded replies, and review replies without exposing those labels to users.

Files:
- `generation/pipeline.py`
- `ui/app.py`

Tasks:
- Add explicit helper signals on `PipelineResult` or derive them centrally in the UI:
  - whether a response is plain conversational
  - whether a response is grounded by retrieved evidence
  - whether a response is a document review response
- Ensure "sources/evidence available" is based on actual grounded output, not merely on retrieval returning chunks.
- Keep citation visibility contingent on grounded support.
- Preserve the current off-topic path, but render it as normal chat instead of a pseudo-RAG state.

Acceptance criteria:
- Plain conversational turns render with no sources block.
- QA turns only show citations and sources when the answer actually cites grounded material.
- Document review turns still show findings even if there is no source rail interaction yet.

### 2. App State Refactor

Objective:
Replace the current monolithic UI flow with explicit view state that supports a single-column chat layout and a conditional right rail.

Files:
- `ui/app.py`

Tasks:
- Normalize session state into clear buckets:
  - `messages`
  - `uploaded_doc_text`
  - `uploaded_doc_name`
  - `last_result`
  - `rail_open`
  - `rail_mode`
  - `rail_selection`
  - `rail_available`
- Replace ad hoc source-preview state with a structured rail payload.
- Move chat rendering, evidence rendering, upload handling, and rail rendering into smaller helpers.
- Remove any remaining layout logic that assumes the preview is always visible or tied directly to one widget branch.

Acceptance criteria:
- The app can open, update, and close the right rail without losing the message list.
- Source selection persists until replaced or dismissed.
- Closing the rail returns the app to a clean single-column layout.

### 3. Chat-Native Layout

Objective:
Make the screen read as a chatbot immediately.

Files:
- `ui/app.py`

Tasks:
- Replace the current top-of-page layout with a compact header:
  - product name
  - one-line evidence-backed GA4GH value statement
- Keep the main surface focused on the conversation stream.
- Improve message styling so user and assistant turns read as chat bubbles rather than stacked markdown blocks.
- Remove leftover dashboard-style or utility-heavy affordances from the main view.
- Keep the page wide, but prioritize readable chat width and cleaner whitespace.

Acceptance criteria:
- The app looks like a chatbot on first load.
- There is no visible mode selector or dashboard framing.
- The message stream remains the dominant visual element.

### 4. Attachment-Native Composer

Objective:
Make document upload feel like part of chat rather than a separate workflow.

Files:
- `ui/app.py`

Tasks:
- Rework the input area so file attachment is visually grouped with chat input.
- Keep upload status compact and conversational.
- Maintain the current PDF/TXT extraction path, but present it as an attached-file interaction.
- Avoid introducing a separate upload panel that competes with the composer.

Implementation note:
Streamlit does not provide a fully custom chat composer primitive, so this may require a pragmatic approximation:
- keep `st.chat_input` for message entry
- visually colocate upload controls directly above or adjacent to it
- style the attachment state so it reads as part of the compose flow

Acceptance criteria:
- Users can understand upload as an attachment action, not a separate mode.
- Attaching a file does not push the app into a different layout.
- File acknowledgement appears as chat context, not dashboard state.

### 5. Dynamic Context Rail

Objective:
Introduce a right-side context rail that is collapsible, selectively opened, and secondary to the chat.

Files:
- `ui/app.py`
- `ui/pdf_viewer.py`

Tasks:
- Add a closed state with a thin right-edge affordance.
- Add an open state that temporarily shifts chat left into a split layout.
- Add a close action that fully restores the single-column chat view.
- Support two rail modes:
  - source preview
  - review detail / evidence detail
- Route per-source `View Source` actions into the rail instead of inline replacement.
- Preserve existing PDF/OWL preview rendering in the rail.

Acceptance criteria:
- The rail is invisible as a full panel until triggered.
- A subtle edge tab remains available when context exists.
- Opening the rail does not remove or replace the source list under the message.
- The rail can be dismissed at any time.

### 6. Source And Evidence Rendering

Objective:
Keep evidence useful but visually subordinate.

Files:
- `ui/app.py`

Tasks:
- Render evidence blocks only when grounded support exists.
- Keep sources collapsed/lightweight by default.
- Deduplicate cited chunks before rendering source rows.
- Ensure every source row has its own stable `View Source` action.
- Keep structured review findings lighter than the current quasi-report presentation.

Acceptance criteria:
- Unrelated or plain conversational turns do not show a sources block.
- Grounded QA answers show compact source rows with one control per row.
- Review outputs remain conversational first, structured second.

### 7. Smart Rail Opening Rules

Objective:
Keep the rail helpful without becoming noisy.

Files:
- `ui/app.py`

Tasks:
- Auto-open the rail for explicit `View Source`.
- Auto-open for review/evidence interactions where the user is clearly drilling down.
- Support smart auto-open for high-signal review results only.
- Do not auto-open for normal grounded QA by default.
- Add conservative heuristics first; avoid over-automation in the initial pass.

Acceptance criteria:
- Manual source inspection always opens the rail.
- Normal QA does not constantly trigger rail motion.
- Document review can open the rail when it clearly improves the next step.

### 8. Empty, Loading, And Error States

Objective:
Improve perceived speed and trustworthiness.

Files:
- `ui/app.py`

Tasks:
- Redesign the empty state to feel like a usable chat product, not a blank Streamlit page.
- Keep spinners and loading copy concise.
- Improve messaging for:
  - missing corpus/index
  - preview unavailable in cache
  - retrieval/generation failure
  - unsupported upload content
- Ensure errors stay in the chat paradigm instead of abrupt raw exception-looking panels.

Acceptance criteria:
- Empty state invites the first message naturally.
- Errors are understandable and contained.
- Preview failures do not break the surrounding chat UI.

## Sequence Of Implementation

### Phase 1: Contract And State

Files:
- `generation/pipeline.py`
- `ui/app.py`

Steps:
1. Define or centralize response-state helpers.
2. Refactor session state into explicit rail and response state.
3. Break `ui/app.py` into smaller render functions without changing the visible behavior too much yet.

Checkpoint:
The app still works with the current visual design, but state is cleaner and ready for layout changes.

### Phase 2: Layout And Composer

Files:
- `ui/app.py`

Steps:
1. Implement compact header and cleaner chat styling.
2. Rework the main layout into chat-first single-column.
3. Integrate upload into the compose area presentation.

Checkpoint:
The app already looks more like a chatbot, even before the rail is added.

### Phase 3: Context Rail

Files:
- `ui/app.py`
- `ui/pdf_viewer.py`

Steps:
1. Add collapsed rail affordance.
2. Add open split layout and close behavior.
3. Route source preview and review-detail selection into the rail.

Checkpoint:
Source inspection works without hijacking the message body.

### Phase 4: Evidence And Review Polish

Files:
- `ui/app.py`
- optionally `generation/pipeline.py` if gating needs one more backend hint

Steps:
1. Tighten grounded-vs-plain rendering rules.
2. Simplify review presentation so it stays conversational first.
3. Tune rail auto-open heuristics.
4. Improve empty/loading/error states.

Checkpoint:
The app behavior now matches the approved UX model closely.

## Risks And Mitigations

### Risk: Streamlit composer limitations

Problem:
`st.chat_input` is not a fully composable custom widget.

Mitigation:
Keep the native chat input for reliability, and visually group upload controls with it rather than forcing a brittle custom composer.

### Risk: UI logic remains too centralized

Problem:
`ui/app.py` is already carrying too much responsibility.

Mitigation:
Refactor early into smaller helper functions and keep render responsibilities sharply separated before adding more interactions.

### Risk: Over-eager rail opening hurts UX

Problem:
If the rail opens too often, the app stops feeling conversational.

Mitigation:
Start with manual open plus conservative review-trigger heuristics. Bias toward under-opening in the first implementation.

### Risk: Evidence gating becomes inconsistent

Problem:
The UI may still show source scaffolding when retrieval happened but grounding did not.

Mitigation:
Centralize the "grounded response" rule in one place and make rendering consume that single decision.

## Definition Of Done

The redesign is complete when:

- the app reads as a chatbot immediately on first load
- there is no visible mode switcher or dashboard-style framing
- upload feels like an attachment-capable chat action
- plain conversational turns do not show evidence chrome
- grounded answers show compact sources only when justified
- source inspection happens through the dynamic right rail
- the rail is collapsible and secondary to the conversation
- review results remain conversational first, structured second

## Recommended First Implementation Task

Start with Phase 1: response-state and app-state refactor. That is the lowest-risk move and will make the later layout and rail work materially easier to implement without regressions.
