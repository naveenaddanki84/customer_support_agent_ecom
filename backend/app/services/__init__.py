"""Service layer: business logic that orchestrates repositories, the LLM, and
real-time delivery. Routers stay thin and delegate here; services never speak
HTTP and never issue SQL directly (they use repositories)."""
