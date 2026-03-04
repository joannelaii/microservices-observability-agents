The purpose of this SOP agent is to:
- Retrieve relevant SOP rulebooks
- Apply those SOPs to the error context provided by the telemetry
- Recommend a step-by-step debugging checklist for investigation

The SOP agent follows a RAG workflow:
Telemetry input -> Retrieve relevant SOP rulebook -> Provide context to LLM -> Generate SOP-based debugging steps

LangGraph nodes:
1. retrieve_sops: semantic search over SOP rulebooks for most relevant SOP
2. apply_sops: generate checklist using retrieved SOP