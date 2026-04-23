# GA4GH RegBot Chatbot UX Redesign

Date: 2026-04-23
Project: GA4GH RegBot
Status: Approved for planning

## Objective

Redesign the current Streamlit app so it behaves like a credible, high-performance chatbot first, while staying within the scope of the GSOC proposal. The redesign should improve clarity, conversational flow, evidence inspection, and document review usability without expanding the backend product surface.

## Product Direction

The app should present as a minimal chat workspace rather than a document dashboard or a tool launcher. A user should understand the product within a few seconds:

- it is a conversational assistant for GA4GH guidance
- it can ground answers in GA4GH source material when relevant
- it can review an uploaded document without switching the user into a separate workflow

The product should not expose internal modes like `corpus_qa` or `document_review` in the interface. Those distinctions remain internal implementation details. To the user, the system is one assistant whose response format adapts to the task.

## Core UX Principles

1. Chat-first by default.
2. Minimal header and minimal non-chat chrome.
3. Retrieval-augmented evidence only appears when the answer is actually grounded in GA4GH corpus material.
4. Unrelated or lightweight conversational turns should not trigger visible RAG scaffolding.
5. Source inspection should be available but secondary to the answer itself.
6. Document upload should feel like an attachment inside chat, not a separate product mode.

## Target Experience

### Default Layout

The default state is a wide, single-column chat interface with:

- a compact header
- a one-line trust-oriented value statement
- a conversation stream with clearer message styling
- an attachment-capable composer at the bottom

The initial screen should feel immediately usable. It should not lead with a landing page, dashboard cards, or onboarding clutter.

### Header

The top area should be intentionally compact:

- product name
- one short sentence describing the assistant as evidence-backed GA4GH guidance

It should avoid a hero section, long instructions, suggestion galleries, or status panels.

### Composer

The composer is the main control surface. It should combine:

- free-text input
- file attachment
- send action

Uploaded documents should feel like chat attachments. After attachment, the app may acknowledge the file in conversation, but it should not visually switch into a separate review workspace.

## Response Model

The system should support three internal response patterns while keeping the UI unified.

### Plain Response

Used for lightweight conversational replies, clarification turns, and user inputs that do not warrant retrieval grounding.

Behavior:

- normal assistant chat response
- no sources block
- no evidence rail behavior
- no retrieval-framed UI

### Grounded Response

Used when retrieved GA4GH material directly supports the answer.

Behavior:

- conversational answer first
- citations only when there is real retrieved support
- compact collapsible sources block under the answer
- per-source `View Source` controls

The answer remains the primary artifact. Sources exist as optional inspection UI.

### Review Response

Used when an uploaded document is being analyzed.

Behavior:

- conversational summary first
- lightweight structured findings beneath the summary
- optional evidence/source affordances beneath the answer
- context rail may auto-open if the review has strong evidence the user is likely to inspect

The review output should still read like the assistant responding in chat, not like a separate analyst dashboard.

## Evidence And Sources

Evidence UI must be conditional. If the assistant has nothing grounded to cite, the answer should remain plain chat.

When evidence exists:

- show a compact collapsible block below the assistant answer
- include one `View Source` control per source row
- keep the block secondary in visual weight
- do not auto-render source containers for casual or unsupported turns

This keeps trust features visible when earned, but avoids fake precision and unnecessary clutter.

## Dynamic Context Rail

The redesign uses a dynamic right-side context rail instead of a permanent split-screen source pane.

### Closed State

When closed:

- the app remains a single-column chat-first layout
- chat owns the page width
- a thin tab on the right edge hints that context is available

The closed state should be subtle and non-disruptive.

### Open State

When open:

- the layout temporarily becomes a split view
- the chat column shifts left slightly
- the context rail occupies the right side
- the rail is closable at all times

This is intentionally not an overlay. The user chose a temporary split layout that visibly opens when needed and disappears cleanly when dismissed.

### Rail Triggers

The rail may open in three cases:

1. explicit `View Source`
2. evidence or review interactions
3. smart auto-open for strong document-review moments where inspecting evidence is a likely next action

Normal conversational QA should not auto-open the rail.

### Rail Content

The rail can host:

- source preview for cached PDF or OWL material
- review-detail context tied to a selected finding
- links to original source URLs when available

It is a transient inspection surface, not a second navigation system.

## Conversation And State Model

The UI should maintain a small number of clear state buckets:

- `conversation state`: messages and attached document context
- `response state`: whether a response has grounded evidence or review findings
- `rail state`: closed, open-to-source, or open-to-review-detail
- `selection state`: currently active source or finding shown in the rail

The key rule is that support UI is downstream of the answer. The user reads the assistant response first, then optionally inspects evidence.

## Interaction Rules

### Citation Rule

Only cite when there is something to cite. If the assistant is answering a plain conversational question without grounded retrieval support, do not show citations or source UI.

### Source Interaction Rule

Each source row must own its own `View Source` action. Clicking one source should not remove the source list or replace the message body. It should update the context rail.

### Review Interaction Rule

Structured findings in document review should remain lightweight. The app should avoid defaulting to heavy analyst tables or dashboard cards unless the user explicitly drills deeper.

### Empty And Loading States

The redesign should make the app feel responsive and credible:

- clean empty chat state
- concise upload acknowledgement
- lightweight loading behavior
- clearer error states for missing corpus, retrieval failure, or preview failure

## Visual Direction

The visual tone should be product-grade but restrained:

- minimal header
- stronger chat identity
- cleaner typography hierarchy
- better spacing and bubble treatment
- low-noise controls
- evidence UI that feels precise rather than bulky

The app should look like a serious research/compliance assistant, not a demo dashboard.

## Scope Boundaries

### In Scope

- redesigning the Streamlit UI into a chat-native experience
- integrating upload into the composer interaction model
- conditional evidence display
- dynamic right context rail
- improved answer and review rendering
- better empty, loading, and error states

### Out of Scope

- new retrieval architecture
- new agent orchestration
- multi-document project workspaces
- persistent user projects or collaboration
- dashboard-first compliance product features
- expansion beyond the current GSOC assistant framing

## Implications For Existing Code

The redesign should primarily reshape `ui/app.py` and reuse existing backend capabilities:

- keep the current pipeline, retrieval, validation, and source preview logic as the backend substrate
- revise UI gating so visible evidence only appears when grounded retrieval is actually used
- preserve cached source preview behavior through `ui/pdf_viewer.py`
- avoid introducing new backend subsystems unless required by the UI contract

The implementation should prefer smaller view helpers and explicit UI state transitions over continuing to grow one large render flow.

## Success Criteria

The redesign is successful if:

- the app reads as a chatbot immediately
- users can ask a question or attach a document without choosing a mode
- plain conversational turns do not show unnecessary evidence chrome
- grounded answers show citations and sources clearly but unobtrusively
- source inspection feels available and useful without dominating layout
- document review feels like a chat capability, not a separate tool

## Recommended Implementation Direction

Implement the redesign as a chat-first layout with a dynamic right context rail, invisible internal mode switching, conditional evidence rendering, and attachment-native document review. This preserves the GSOC proposal scope while materially improving perceived chatbot quality and UX coherence.
